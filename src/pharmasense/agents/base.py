import inspect
import json
from typing import Any, Callable, Dict, List, Type, Optional

from pydantic import BaseModel
from sqlalchemy.orm import Session
from pharmasense.utils.formatters import compact_tool_result

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
        max_iterations: int = 2,
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

    def validate_finalization(self, output_obj: BaseModel, executed_tools: List[dict]) -> None:
        """Hook for subclasses to enforce runtime invariants before accepting a final output."""
        pass

    def _build_tool_specs(self) -> List[ToolSpec]:
        specs = []
        for name, func in self.tools.items():
            sig = inspect.signature(func)
            if "input_data" not in sig.parameters:
                raise ValueError(f"Tool {name} must have an 'input_data' parameter")

            input_model = sig.parameters["input_data"].annotation
            schema = input_model.model_json_schema()

            # 5. TOOL-SCHEMA MINIFICATION
            def minify_schema(s: dict) -> dict:
                minified = {}
                for k, v in s.items():
                    # Preserve types, enums, items, properties, and anyOf
                    if k in ("type", "enum", "items", "properties", "required", "$defs", "anyOf"):
                        if isinstance(v, dict) and k in ("properties", "$defs"):
                            minified[k] = {pk: minify_schema(pv) for pk, pv in v.items()}
                        elif isinstance(v, dict) and k == "items":
                            minified[k] = minify_schema(v)
                        else:
                            minified[k] = v
                    elif k == "description":
                        # Keep description but trim it if it's too verbose
                        # or just keep it entirely to be safe, but the instruction says "remove redundant descriptions"
                        # We will remove property-level descriptions to save tokens, they are usually self-evident from the name
                        pass
                return minified

            parameters = minify_schema(schema)

            # Ensure type is object at root
            parameters["type"] = "object"

            specs.append(
                ToolSpec(
                    name=name,
                    description=func.__doc__.split('\n')[0] if func.__doc__ else f"Tool {name}",
                    parameters=parameters,
                )
            )
        return specs

    def run(self, prompt: str, single_tool_mode: bool = False) -> tuple[BaseModel, List[dict]]:
        messages = [
            Message(role="system", content=self.system_instruction),
            Message(role="user", content=prompt),
        ]

        self.executed_tools = []
        active_tools = self._tool_specs if self._tool_specs else None

        for _ in range(self.max_iterations):
            # 1. Prepare Request
            req = LLMRequest(
                messages=messages,
                model=self.model_name,
                tools=active_tools,
                tool_choice="auto" if active_tools else "none",
                response_schema=self.output_model.model_json_schema()
            )

            # 2. Invoke LLM Gateway
            from pharmasense.llm.contracts import LLMGatewayError

            try:
                res = self.llm.complete(req)

                # 3. Check for final parsed output
                if res.parsed:
                    parsed_obj = self.output_model.model_validate(res.parsed)
                    self.validate_finalization(parsed_obj, self.executed_tools)
                    return parsed_obj, self.executed_tools

                if not res.tool_calls:
                    raise RuntimeError("LLM returned no tool calls and no valid parsed output.")

            except (LLMGatewayError, RuntimeError, ValueError) as e:
                error_str = str(e)
                if "Structured output parsing failed" in error_str or "Structured output is not valid JSON" in error_str or "Structured output failed schema validation" in error_str or "no valid parsed output" in error_str or "Finalization rejected" in error_str:
                    from pharmasense.llm.contracts import LLMInvalidOutputError
                    if isinstance(e, LLMInvalidOutputError) and getattr(e, "raw_content", None):
                        messages.append(Message(role="assistant", content=e.raw_content))
                    messages.append(Message(role="user", content=f"Your previous response was invalid. Error: {error_str}. Please correct it and output strictly the requested JSON schema or tool call."))
                    continue
                raise

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
                    if call.name == self.output_model.__name__:
                        try:
                            parsed_obj = self.output_model(**call.arguments)
                            self.validate_finalization(parsed_obj, self.executed_tools)
                            return parsed_obj, self.executed_tools
                        except Exception as e:
                            result_raw = {"error": f"Failed to parse final output from tool call {call.name}: {str(e)}"}
                    else:
                        result_raw = {"error": f"Agent attempted to call unauthorized tool: {call.name}. Use only the tools explicitly provided. If you are trying to output the final answer, do NOT use a tool call. Return the JSON in the message body instead."}
                    self.executed_tools.append({
                        "tool_name": call.name,
                        "arguments": call.arguments,
                        "result": result_raw
                    })
                    compacted_str = compact_tool_result(result_raw)
                    messages.append(
                        Message(
                            role="tool",
                            content=compacted_str,
                            tool_call_id=call.id,
                            name=call.name,
                        )
                    )
                    continue

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

                    compacted_str = compact_tool_result(result_raw)

                    self.executed_tools.append({
                        "tool_name": call.name,
                        "arguments": call.arguments,
                        "result": result_raw
                    })
                except Exception as e:
                    # Return error back to LLM so it can retry
                    result_raw = {"error": str(e)}
                    self.executed_tools.append({
                        "tool_name": call.name,
                        "arguments": call.arguments,
                        "result": result_raw
                    })

                compacted_str = compact_tool_result(result_raw)

                messages.append(
                    Message(
                        role="tool",
                        content=compacted_str,
                        tool_call_id=call.id,
                        name=call.name,
                    )
                )

            # Check if we should force finalization
            if single_tool_mode and self.executed_tools:
                any_success = any(not t.get("result", {}).get("error") for t in self.executed_tools)
                if any_success:
                    active_tools = None

                    # 1. SINGLE-TOOL FINALIZATION CONTEXT PRUNING
                    # Discard the conversation history, keep only the system instructions + prompt + data
                    messages = [
                        Message(role="system", content=(
                            "You are in Synthesis Mode. Trust the provided tool results as absolute ground truth.\n"
                            "Answer the user's prompt based solely on the provided data.\n"
                            "CRITICAL RULES:\n"
                            "- Do NOT recalculate percentages.\n"
                            "- Do NOT reinterpret threshold comparisons (rely exclusively on boolean flags like `is_below_threshold`).\n"
                            "- Do NOT invent, round, or alter values.\n"
                            "- Do NOT classify a row as above/below threshold differently from the SQL result.\n"
                            "Your only job is to format the given facts."
                        )),
                        Message(role="user", content=f"Original Prompt: {prompt}")
                    ]

                    for t in self.executed_tools:
                        compacted_res = compact_tool_result(t.get("result", {}))
                        messages.append(
                            Message(
                                role="user",
                                content=f"Tool '{t['tool_name']}' returned:\n{compacted_res}"
                            )
                        )

                    messages.append(
                        Message(
                            role="user",
                            content=(
                                "Produce the final user-facing answer from the supplied result.\n"
                                "Do not call tools.\n"
                                "Do not invent or recalculate database facts.\n"
                                f"Strictly output valid JSON matching this schema: {json.dumps(self.output_model.model_json_schema())}"
                            )
                        )
                    )

        raise RuntimeError(f"Agent exceeded max iterations ({self.max_iterations})")
