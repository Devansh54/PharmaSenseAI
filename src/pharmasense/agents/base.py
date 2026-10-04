import inspect
import json
from typing import Any, Callable, Dict, List, Type, Optional

from pydantic import BaseModel
from sqlalchemy.orm import Session

from pharmasense.llm.contracts import (
    LLMProvider,
    LLMRequest,
    Message,
    ToolSpec,
)


class BaseAgent:
    """Bounded, stateful agent execution loop."""

    def __init__(
        self,
        session: Session,
        llm: LLMProvider,
        system_instruction: str,
        tools: Dict[str, Callable],
        output_model: Type[BaseModel],
        max_iterations: int = 5,
        model_name: Optional[str] = None
    ):
        self.session = session
        self.llm = llm
        self.system_instruction = system_instruction
        self.tools = tools
        self.output_model = output_model
        self.max_iterations = max_iterations
        self.model_name = model_name
        self._tool_specs = self._build_tool_specs()

    def _build_tool_specs(self) -> List[ToolSpec]:
        specs = []
        for name, func in self.tools.items():
            sig = inspect.signature(func)
            if "input_data" not in sig.parameters:
                raise ValueError(f"Tool {name} must have an 'input_data' parameter")

            input_model = sig.parameters["input_data"].annotation
            schema = input_model.model_json_schema()

            parameters = {
                "type": "object",
                "properties": schema.get("properties", {}),
            }
            if "required" in schema:
                parameters["required"] = schema["required"]

            # Pydantic may put defs in $defs; we must copy them so OpenAI doesn't choke on missing references
            if "$defs" in schema:
                parameters["$defs"] = schema["$defs"]

            specs.append(
                ToolSpec(
                    name=name,
                    description=func.__doc__ or f"Tool {name}",
                    parameters=parameters,
                )
            )
        return specs

    def run(self, prompt: str) -> tuple[BaseModel, List[dict]]:
        messages = [
            Message(role="system", content=self.system_instruction),
            Message(role="user", content=prompt),
        ]

        self.executed_tools = []

        for _ in range(self.max_iterations):
            # 1. Prepare Request
            req = LLMRequest(
                messages=messages,
                model=self.model_name,
                tools=self._tool_specs if self._tool_specs else None,
                tool_choice="auto" if self._tool_specs else "none",
                response_schema=self.output_model.model_json_schema()
            )

            # 2. Invoke LLM Gateway
            res = self.llm.complete(req)

            # 3. Check for final parsed output
            if res.parsed:
                return self.output_model.model_validate(res.parsed), self.executed_tools

            if not res.tool_calls:
                raise RuntimeError("LLM returned no tool calls and no valid parsed output.")

            # 4. Append Assistant's tool request
            messages.append(
                Message(
                    role="assistant",
                    content=res.content,
                    tool_calls=res.tool_calls,
                    provider_metadata=res.provider_metadata
                )
            )

            # 5. Execute each tool and append results
            for call in res.tool_calls:
                if call.name not in self.tools:
                    raise RuntimeError(f"Agent attempted to call unauthorized tool: {call.name}")

                tool_func = self.tools[call.name]
                sig = inspect.signature(tool_func)
                input_model_cls = sig.parameters["input_data"].annotation

                try:
                    # Map the raw arguments dict to the expected Pydantic model
                    input_obj = input_model_cls(**call.arguments)

                    kwargs = {"input_data": input_obj}
                    if "session" in sig.parameters:
                        kwargs["session"] = self.session

                    result_obj = tool_func(**kwargs)

                    if isinstance(result_obj, BaseModel):
                        result_str = result_obj.model_dump_json()
                        result_raw = json.loads(result_str)
                    else:
                        result_str = json.dumps(result_obj)
                        result_raw = result_obj

                    self.executed_tools.append({
                        "tool_name": call.name,
                        "arguments": call.arguments,
                        "result": result_raw
                    })
                except Exception as e:
                    # Return error back to LLM so it can retry
                    result_str = json.dumps({"error": str(e)})
                    self.executed_tools.append({
                        "tool_name": call.name,
                        "arguments": call.arguments,
                        "result": {"error": str(e)}
                    })

                messages.append(
                    Message(
                        role="tool",
                        content=result_str,
                        tool_call_id=call.id,
                        name=call.name,
                    )
                )

        raise RuntimeError(f"Agent exceeded max iterations ({self.max_iterations})")
