import pytest
from pharmasense.llm.contracts import LLMProvider, LLMRequest, LLMResponse, ToolCall
from pharmasense.agents.report import create_report_writer_agent, ReportWriterOutput
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from pharmasense.llm.gateway import LLMGateway
import json

class MockNoEvidenceLLM(LLMProvider):
    def __init__(self):
        self.call_count = 0

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.call_count += 1

        if self.call_count == 1:
            # Emulate the LLM formatting 'limitations_noted' as a string instead of a list,
            # and inventing a citation because it wasn't told not to.
            out_args = {
                "report_text": "No evidence was found for the compound ZXQ-9999.",
                "limitations_noted": "No matching structured records were found.",
                "citations_resolved": [{"doc_id": "invented", "title": "Invented Paper"}]
            }
            tc = ToolCall(id='1', name='ReportWriterOutput', arguments=out_args)
            return LLMResponse(content='', tool_calls=[tc], parsed=None)

        raise RuntimeError("Agent looped!")

def test_report_writer_no_evidence_handling():
    engine = create_engine('sqlite://')
    with Session(engine) as session:
        gateway = LLMGateway(MockNoEvidenceLLM())
        agent = create_report_writer_agent(session, gateway)

        prompt = "Trial Analyst: No matching structured records were found."
        res, tools = agent.run(prompt)

        assert isinstance(res, ReportWriterOutput)
        assert "No evidence" in res.report_text
        # Ensure limitation was preserved and coerced to a list
        assert "No matching structured records" in res.limitations_noted[0]
        # Ensure hallucinated citation was stripped
        assert res.citations_resolved == []


def test_report_writer_conversational_json_rescue():
    from pharmasense.llm.groq_adapter import GroqAdapter
    from pharmasense.config import GroqAdapterConfig
    from unittest.mock import MagicMock

    class MockGroqClient:
        def __init__(self):
            self.chat = MagicMock()
            self.chat.completions.create.side_effect = self.create_completion
            self.call_count = 0

        def create_completion(self, **kwargs):
            self.call_count += 1
            mock_choice = MagicMock()

            if self.call_count == 1:
                mock_choice.message.content = "Here is the final report since no data was found:\n```json\n{\n  \"report_text\": \"No evidence found.\",\n  \"limitations_noted\": [\"No records\"],\n  \"citations_resolved\": []\n}\n```"
                mock_choice.message.tool_calls = None
            else:
                raise RuntimeError("Agent looped unexpectedly")

            mock_choice.finish_reason = "stop"
            mock_completion = MagicMock()
            mock_completion.choices = [mock_choice]
            mock_completion.usage.prompt_tokens = 10
            mock_completion.usage.completion_tokens = 20
            return mock_completion

    engine = create_engine('sqlite://')
    with Session(engine) as session:
        mock_client = MockGroqClient()
        adapter = GroqAdapter(config=GroqAdapterConfig(api_key='fake', model='llama'), client=mock_client)
        gateway = LLMGateway(adapter)

        agent = create_report_writer_agent(session, gateway)
        res, tools = agent.run('Write a report based on empty findings.')

        assert "No evidence found." in res.report_text
        assert mock_client.call_count == 1


def test_report_writer_no_evidence_pure_text():
    from pharmasense.llm.groq_adapter import GroqAdapter
    from pharmasense.config import GroqAdapterConfig
    from unittest.mock import MagicMock

    class MockGroqClient:
        def __init__(self):
            self.chat = MagicMock()
            self.chat.completions.create.side_effect = self.create_completion
            self.call_count = 0

        def create_completion(self, **kwargs):
            self.call_count += 1
            mock_choice = MagicMock()

            mock_choice.message.content = "No cited evidence was available to resolve because both upstream specialists reported no results."
            mock_choice.message.tool_calls = None

            mock_choice.finish_reason = "stop"
            mock_completion = MagicMock()
            mock_completion.choices = [mock_choice]
            mock_completion.usage.prompt_tokens = 10
            mock_completion.usage.completion_tokens = 20
            return mock_completion

    engine = create_engine('sqlite://')
    with Session(engine) as session:
        mock_client = MockGroqClient()
        adapter = GroqAdapter(config=GroqAdapterConfig(api_key='fake', model='llama'), client=mock_client)
        gateway = LLMGateway(adapter)

        agent = create_report_writer_agent(session, gateway)
        prompt = "Trial Analyst:\nSummary: No matching structured records found.\nLimitations: ['No results found for ZXQ-9999.']\nLiterature Research:\nSummary: No relevant literature found."

        res, tools = agent.run(prompt)
        assert "No cited evidence" in res.report_text
        assert "No results found for ZXQ-9999." in res.limitations_noted


def test_report_writer_content_none_tool_call_loop():
    from pharmasense.llm.groq_adapter import GroqAdapter
    from pharmasense.config import GroqAdapterConfig
    from unittest.mock import MagicMock

    class MockGroqClientContentNone:
        def __init__(self):
            self.chat = MagicMock()
            self.chat.completions.create.side_effect = self.create_completion
            self.call_count = 0

        def create_completion(self, **kwargs):
            self.call_count += 1
            mock_choice = MagicMock()
            tc = MagicMock()
            tc.id = f"call_{self.call_count}"
            tc.function.name = "citation_formatter_tool"
            tc.function.arguments = '{"chunk_ids": []}'
            mock_choice.message.content = None
            mock_choice.message.tool_calls = [tc]
            mock_choice.finish_reason = "tool_calls"
            mock_completion = MagicMock()
            mock_completion.choices = [mock_choice]
            mock_completion.usage.prompt_tokens = 10
            mock_completion.usage.completion_tokens = 5
            return mock_completion

    engine = create_engine("sqlite://")
    with Session(engine) as session:
        mock_client = MockGroqClientContentNone()
        adapter = GroqAdapter(
            config=GroqAdapterConfig(api_key="fake", model="llama"), client=mock_client
        )
        gateway = LLMGateway(adapter)
        agent = create_report_writer_agent(session, gateway)

        prompt = (
            "Trial Analyst:\n"
            "Summary: No matching structured records found.\n"
            "Limitations: ['No results found for ZXQ-9999.']\n"
            "Literature Research:\n"
            "Summary: No relevant literature found."
        )

        res, tools = agent.run(prompt)

        assert isinstance(res, ReportWriterOutput)
        assert "No citable evidence" in res.report_text
        assert "No results found for ZXQ-9999." in res.limitations_noted
        assert res.citations_resolved == []
        assert mock_client.call_count == 2


def test_report_writer_iteration_failure_when_evidence_ambiguous_or_unestablished():
    from pharmasense.llm.groq_adapter import GroqAdapter
    from pharmasense.config import GroqAdapterConfig
    from unittest.mock import MagicMock

    class MockGroqClientLoop:
        def __init__(self):
            self.chat = MagicMock()
            self.chat.completions.create.side_effect = self.create_completion
            self.call_count = 0

        def create_completion(self, **kwargs):
            self.call_count += 1
            mock_choice = MagicMock()
            tc = MagicMock()
            tc.id = f"call_{self.call_count}"
            tc.function.name = "citation_formatter_tool"
            tc.function.arguments = '{"chunk_ids": []}'
            mock_choice.message.content = None
            mock_choice.message.tool_calls = [tc]
            mock_choice.finish_reason = "tool_calls"
            mock_completion = MagicMock()
            mock_completion.choices = [mock_choice]
            mock_completion.usage.prompt_tokens = 10
            mock_completion.usage.completion_tokens = 5
            return mock_completion

    engine = create_engine("sqlite://")
    with Session(engine) as session:
        mock_client = MockGroqClientLoop()
        adapter = GroqAdapter(
            config=GroqAdapterConfig(api_key="fake", model="llama"), client=mock_client
        )
        gateway = LLMGateway(adapter)
        agent = create_report_writer_agent(session, gateway)

        # Upstream results contain positive evidence, not an established absence of evidence
        prompt = (
            "--- Trial Data Analyst Findings ---\n"
            "Summary: Found 3 clinical trials for compound ABC.\n"
            "Limitations: ['Phase 2 data preliminary.']\n\n"
            "--- Literature Research Findings ---\n"
            "Findings: Document DOC-101 indicates positive receptor binding.\n"
        )

        res, tools = agent.run(prompt)

        assert isinstance(res, ReportWriterOutput)
        assert "Report synthesis could not be completed" in res.report_text
        assert "No citable evidence" not in res.report_text
        assert "Report Writer exceeded maximum iterations before producing valid output." in res.limitations_noted
        assert "Phase 2 data preliminary." in res.limitations_noted
        assert res.citations_resolved == []
        assert mock_client.call_count == 2


def test_report_writer_iteration_failure_when_upstream_specialist_failed():
    from pharmasense.llm.groq_adapter import GroqAdapter
    from pharmasense.config import GroqAdapterConfig
    from unittest.mock import MagicMock

    class MockGroqClientLoop:
        def __init__(self):
            self.chat = MagicMock()
            self.chat.completions.create.side_effect = self.create_completion
            self.call_count = 0

        def create_completion(self, **kwargs):
            self.call_count += 1
            mock_choice = MagicMock()
            tc = MagicMock()
            tc.id = f"call_{self.call_count}"
            tc.function.name = "citation_formatter_tool"
            tc.function.arguments = '{"chunk_ids": []}'
            mock_choice.message.content = None
            mock_choice.message.tool_calls = [tc]
            mock_choice.finish_reason = "tool_calls"
            mock_completion = MagicMock()
            mock_completion.choices = [mock_choice]
            mock_completion.usage.prompt_tokens = 10
            mock_completion.usage.completion_tokens = 5
            return mock_completion

    engine = create_engine("sqlite://")
    with Session(engine) as session:
        mock_client = MockGroqClientLoop()
        adapter = GroqAdapter(
            config=GroqAdapterConfig(api_key="fake", model="llama"), client=mock_client
        )
        gateway = LLMGateway(adapter)
        agent = create_report_writer_agent(session, gateway)

        # One specialist reports no records, but the other had an execution failure
        prompt = (
            "--- Trial Data Analyst Findings ---\n"
            "Summary: No matching structured records found.\n"
            "Limitations: ['No results found for ZXQ-9999.']\n\n"
            "--- Literature Research Findings ---\n"
            "Findings: Search execution failed due to database connection lost.\n"
        )

        res, tools = agent.run(prompt)

        assert isinstance(res, ReportWriterOutput)
        assert "Report synthesis could not be completed" in res.report_text
        assert "No citable evidence" not in res.report_text
        assert "Report Writer exceeded maximum iterations before producing valid output." in res.limitations_noted
        assert "No results found for ZXQ-9999." in res.limitations_noted
        assert res.citations_resolved == []
        assert mock_client.call_count == 2


def test_report_writer_evidence_attribution_q9_distinction():
    """Verify Q9 evidence attribution:
    - Literature claims (superior efficacy, manageable safety) remain explicitly attributed to their source (DOC-00160).
    - Trial registry metadata (TRL-0001: Phase III, completed, 450 enrollment) is not presented as independent confirmation of outcomes.
    - Citation validation preserves verified literature citations and strips unverified ones.
    """
    from datetime import datetime, timezone, date
    from pharmasense.db.source_schema import ResearchDocument, Compound, ClinicalTrial
    from pharmasense.db.models import DocumentChunk, Base

    class MockQ9AttributionLLM(LLMProvider):
        def __init__(self):
            self.call_count = 0

        def complete(self, request: LLMRequest) -> LLMResponse:
            self.call_count += 1
            if self.call_count == 1:
                tc = ToolCall(
                    id="call_cite",
                    name="citation_formatter_tool",
                    arguments={
                        "claim": "DKU-1001 demonstrated superior efficacy and manageable safety in Metabolic Disease according to conference abstract DOC-00160.",
                        "evidence_chunk_ids": ["DOC-00160::chunk::0"]
                    }
                )
                return LLMResponse(content="", tool_calls=[tc], parsed=None)

            if self.call_count == 2:
                out_args = {
                    "report_text": (
                        "Structured clinical trial records establish that DKU-1001 was investigated in "
                        "completed Phase III trial TRL-0001 with a target enrollment of 450 and primary endpoint "
                        "of overall response rate. In scientific research literature, conference abstract "
                        "DOC-00160 reports that DKU-1001 demonstrated superior efficacy over standard care with "
                        "a manageable safety profile characterized by mild pyrexia [DOC-00160::chunk::0]. "
                        "The structured trial record documents trial design, enrollment, and completion status, "
                        "but does not independently verify clinical efficacy or safety outcomes."
                    ),
                    "limitations_noted": [
                        "Preliminary conference abstract findings; long-term safety monitoring ongoing."
                    ],
                    "citations_resolved": [
                        {
                            "chunk_id": "DOC-00160::chunk::0",
                            "doc_id": "DOC-00160",
                            "title": "Efficacy and Safety of DKU-1001 in Metabolic Disease",
                            "valid": True
                        },
                        {
                            "chunk_id": "DOC-99999::chunk::0",
                            "doc_id": "DOC-99999",
                            "title": "Unverified Paper",
                            "valid": False
                        }
                    ]
                }
                tc = ToolCall(id="call_out", name="ReportWriterOutput", arguments=out_args)
                return LLMResponse(content="", tool_calls=[tc], parsed=None)

            raise RuntimeError(f"Unexpected LLM call count: {self.call_count}")

    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    with Session(engine) as session:
        cmp = Compound(compound_id="DKU-1001", compound_name="DKU-1001")
        session.add(cmp)
        trial = ClinicalTrial(
            trial_id="TRL-0001",
            compound_id="DKU-1001",
            trial_phase="Phase III",
            status="Completed",
            target_enrollment=450,
            primary_endpoint="Overall response rate",
        )
        session.add(trial)
        doc = ResearchDocument(
            doc_id="DOC-00160",
            compound_id="DKU-1001",
            trial_id="TRL-0001",
            doc_type="Conference Abstract",
            title="Efficacy and Safety of DKU-1001 in Metabolic Disease",
            author="Lead Investigator",
            date=date(2025, 6, 1),
            full_text="DKU-1001 demonstrated superior efficacy with manageable pyrexia.",
        )
        session.add(doc)
        chunk = DocumentChunk(
            chunk_id="DOC-00160::chunk::0",
            doc_id="DOC-00160",
            compound_id="DKU-1001",
            trial_id="TRL-0001",
            doc_type="Conference Abstract",
            title="Efficacy and Safety of DKU-1001 in Metabolic Disease",
            date=date(2025, 6, 1),
            chunk_index=0,
            chunk_count=1,
            chunk_text="In Phase III trials, DKU-1001 demonstrated superior efficacy with manageable pyrexia.",
            token_count=15,
            content_hash="hash160",
            embedding=[0.0] * 384,
            embedding_model="test",
            index_version="v1",
            created_at=datetime.now(timezone.utc),
        )
        session.add(chunk)
        session.commit()

        mock_llm = MockQ9AttributionLLM()
        gateway = LLMGateway(mock_llm)
        agent = create_report_writer_agent(session, gateway)

        # Verify instructions enforce attribution and distinction
        assert "Evidence Attribution Rules" in agent.system_instruction
        assert "Distinguish between facts established by structured trial records" in agent.system_instruction
        assert "Do NOT present trial registry metadata as independent clinical confirmation or verification of efficacy or safety outcomes." in agent.system_instruction

        prompt = (
            "--- Trial Data Analyst Findings ---\n"
            "Summary: Found clinical trial TRL-0001 for DKU-1001. Phase: Phase III, Status: Completed, Target Enrollment: 450, Primary Endpoint: Overall response rate.\n"
            "Limitations: ['Structured trial records establish trial design and status, not clinical verification of outcomes.']\n\n"
            "--- Literature Research Findings ---\n"
            "Findings: Retrieved conference abstract DOC-00160 (chunk DOC-00160::chunk::0) reporting DKU-1001 demonstrated superior efficacy over standard care with manageable pyrexia adverse events in Metabolic Disease.\n"
            "Limitations: ['Preliminary conference abstract findings; long-term safety monitoring ongoing.']"
        )

        res, tools = agent.run(prompt)

        assert isinstance(res, ReportWriterOutput)
        # Literature claims remain explicitly attributed to their source
        assert "DOC-00160" in res.report_text
        assert "superior efficacy" in res.report_text
        assert "DOC-00160::chunk::0" in res.report_text

        # Trial metadata is presented as trial registry metadata, not confirmation of outcomes
        assert "TRL-0001" in res.report_text
        assert "Phase III" in res.report_text
        assert "does not independently verify clinical efficacy" in res.report_text

        # Citation validation preserves verified chunk and strips unverified chunk
        assert len(res.citations_resolved) == 1
        assert res.citations_resolved[0]["chunk_id"] == "DOC-00160::chunk::0"

        # Specialist limitations are preserved
        assert any("long-term safety monitoring ongoing" in lim for lim in res.limitations_noted)
        assert mock_llm.call_count == 2
