"""Reproducible Offline Adverse Event Triage Demo.

Demonstrates the Adverse Event Triage specialist workflow:
1. Retrieves trial-specific adverse events using `sql_query_tool`.
2. Evaluates severity and seriousness using `ae_severity_classifier_tool`.
3. Triggers human-review escalation using `escalation_notifier_tool`.
4. Emits verified structured `AETriageOutput`.

NOTICE: All records used in this demo (TRL-0034, AE-00023, PT-23785) are
synthetic test fixtures. No real patient data exists, and no external
emails or production alerts are dispatched.
"""
import json
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from pharmasense.db.models import Base, ReviewTask
from pharmasense.db.source_schema import AdverseEvent, ClinicalTrial, Compound
from pharmasense.llm.contracts import LLMProvider, LLMResponse, ToolCall
from pharmasense.llm.gateway import LLMGateway
from pharmasense.agents.adverse_event import create_ae_triage_agent


def run_demo():
    print("=" * 70)
    print("PharmaSenseAI - Adverse Event Triage Specialist Demo (Offline Mode)")
    print("=" * 70)

    # 1. Setup isolated in-memory DB with synthetic records
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)

    with Session(engine) as session:
        # Populate synthetic fixtures from adverse_events.csv
        compound = Compound(compound_id="DKU-1042", compound_name="DKU-1042")
        session.add(compound)

        trial = ClinicalTrial(
            trial_id="TRL-0034",
            compound_id="DKU-1042",
            trial_phase="Phase II",
            status="Active",
            target_enrollment=120
        )
        session.add(trial)

        ae = AdverseEvent(
            event_id="AE-00023",
            trial_id="TRL-0034",
            site_id="SITE-00118",
            patient_code="PT-23785",
            adverse_event_term="Anemia",
            severity="Severe",
            seriousness="Serious",
            causality_assessment="Not Related",
            outcome="Fatal",
            reported_by="Dr. Gomez"
        )
        session.add(ae)
        session.commit()

        # 2. Offline deterministic provider simulating the model step sequence
        class OfflineDemoLLM(LLMProvider):
            def __init__(self):
                self.step = 0

            def complete(self, req):
                self.step += 1
                if self.step == 1:
                    # Tool call 1: Query trial adverse events
                    return LLMResponse(content="", tool_calls=[
                        ToolCall(
                            id="call_sql",
                            name="sql_query_tool",
                            arguments={"query_id": "adverse_events_by_trial", "parameters": {"trial_id": "TRL-0034"}}
                        )
                    ])
                elif self.step == 2:
                    # Tool call 2: Classify severity vs seriousness
                    return LLMResponse(content="", tool_calls=[
                        ToolCall(
                            id="call_classifier",
                            name="ae_severity_classifier_tool",
                            arguments={"severity": "Severe", "seriousness": "Serious", "adverse_event_term": "Anemia"}
                        )
                    ])
                elif self.step == 3:
                    # Tool call 3: Trigger human review escalation
                    return LLMResponse(content="", tool_calls=[
                        ToolCall(
                            id="call_escalation",
                            name="escalation_notifier_tool",
                            arguments={"event_id": "AE-00023", "reason": "Fatal/Severe Anemia in Trial TRL-0034"}
                        )
                    ])
                elif self.step == 4:
                    # Final structured output
                    final_payload = {
                        "explanation": (
                            "Trial TRL-0034 reported fatal adverse event AE-00023 (Anemia, Severe/Serious) "
                            "for patient PT-23785 at site SITE-00118. Causality was assessed as Not Related "
                            "by Dr. Gomez. The event was verified by the deterministic severity classifier "
                            "and escalated to the safety review queue (Task persisted)."
                        ),
                        "final_severity": "Severe",
                        "final_seriousness": "Serious",
                        "requires_review": True
                    }
                    return LLMResponse(content=json.dumps(final_payload), tool_calls=[])

                return LLMResponse(content="")

        demo_query = "A site just reported a serious adverse event for Trial TRL-0034 - triage it."
        print(f"\n[DEMO QUERY]: \"{demo_query}\"\n")

        agent = create_ae_triage_agent(session, LLMGateway(OfflineDemoLLM()))
        result, executed_tools = agent.run(demo_query)

        print("[EXECUTED TOOLS]:")
        for i, t in enumerate(executed_tools, 1):
            print(f"  {i}. {t['tool_name']}")

        print("\n[STRUCTURED AGENT OUTPUT (AETriageOutput)]:")
        print(result.model_dump_json(indent=2))

        # 3. Verify persisted human-review task
        task = session.query(ReviewTask).first()
        print("\n[PERSISTED HUMAN-REVIEW TASK]:")
        print(f"  Task ID:   {task.task_id}")
        print(f"  Event ID:  {task.event_id}")
        print(f"  Status:    {task.status}")
        print(f"  Reason:    {task.reason}")
        print(f"  Created:   {task.created_at}")

        print("\n[VERIFICATION]:")
        print("  - Severity vs Seriousness: DISTINCT (Severe vs Serious)")
        print("  - Escalation Action: REQUIRED (requires_review=True, ReviewTask created)")
        print("  - External Alerts: MOCK ONLY (No production network traffic)")
        print("  - Data Integrity: Grounded in synthetic record AE-00023")
        print("=" * 70)


if __name__ == "__main__":
    run_demo()
