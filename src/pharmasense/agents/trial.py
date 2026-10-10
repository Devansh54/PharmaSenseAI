from pathlib import Path
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from pharmasense.llm.contracts import LLMProvider
from pharmasense.tools.sql_query import sql_query_tool
from pharmasense.agents.base import BaseAgent

class TrialDataAnalystOutput(BaseModel):
    summary: str = Field(..., description="The summary of the trial/site/lab data findings.")
    limitations: list[str] = Field(default_factory=list, description="Any data limitations encountered.")

class TrialDataAnalystAgent(BaseAgent):
    def run(self, prompt: str, single_tool_mode: bool = False) -> tuple[BaseModel, list[dict]]:
        try:
            return super().run(prompt, single_tool_mode)
        except RuntimeError as e:
            if "Agent exceeded max iterations" in str(e):
                return TrialDataAnalystOutput(
                    summary="No data found or search could not be executed.",
                    limitations=["Agent exceeded max iterations before producing valid output."]
                ), getattr(self, "executed_tools", [])
            raise

def create_trial_data_analyst(session: Session, llm: LLMProvider, task_desc: str = "") -> BaseAgent:
    instruction_path = Path("agent_specs/trial_data_analyst/instructions.md")
    full_instruction = instruction_path.read_text(encoding="utf-8")

    # 3. DYNAMIC TOOL CONTEXT
    # Only keep the query definition that is mentioned in the task_desc
    if task_desc and "query_id" in task_desc:
        import re
        # Find all query IDs in the prompt
        # We look at the list of queries in instructions.md
        # Keep only the lines starting with "- **`" that match the requested query.
        lines = full_instruction.splitlines()
        filtered_lines = []
        in_query_list = False
        for line in lines:
            if line.startswith("### Valid Query Families"):
                in_query_list = True
                filtered_lines.append(line)
                continue

            if in_query_list and line.startswith("- **`"):
                # Extract query ID
                match = re.search(r'- \*\*`([^`]+)`\*\*', line)
                if match:
                    qid = match.group(1)
                    if qid in task_desc:
                        filtered_lines.append(line)
                continue

            if in_query_list and line.startswith("## "):
                in_query_list = False

            filtered_lines.append(line)

        full_instruction = "\n".join(filtered_lines)

    # Remove Examples section
    if "## Examples" in full_instruction:
        full_instruction = full_instruction.split("## Examples")[0].strip()

    return TrialDataAnalystAgent(
        session=session,
        llm=llm,
        system_instruction=full_instruction,
        tools={"sql_query_tool": sql_query_tool},
        output_model=TrialDataAnalystOutput,
        max_iterations=4,
    )
