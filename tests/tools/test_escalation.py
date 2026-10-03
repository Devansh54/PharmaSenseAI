"""Tests for Escalation tool."""
from sqlalchemy.orm import Session
from pharmasense.tools.escalation import escalation_notifier_tool, EscalationInput
from pharmasense.db.source_schema import AdverseEvent, ClinicalTrial, Compound, TrialSite

def test_escalation_notifier(pgvector_engine):
    with Session(pgvector_engine) as session:
        # Create dependencies for AdverseEvent
        cmp = Compound(compound_id="CMP-99")
        session.add(cmp)
        session.flush()
        trial = ClinicalTrial(trial_id="TRIAL-99", compound_id="CMP-99")
        session.add(trial)
        session.flush()
        site = TrialSite(site_id="SITE-99", trial_id="TRIAL-99")
        session.add(site)
        session.flush()
        ae = AdverseEvent(event_id="AE-01", trial_id="TRIAL-99", site_id="SITE-99")
        session.add(ae)
        session.commit()
        
        result1 = escalation_notifier_tool(session, EscalationInput(
            event_id="AE-01",
            reason="Serious AE"
        ))
        assert result1.persisted is True
        assert "REV-" in result1.task_id
        
        # Test Idempotency
        result2 = escalation_notifier_tool(session, EscalationInput(
            event_id="AE-01",
            reason="Serious AE duplicate"
        ))
        assert result2.task_id == result1.task_id
        assert "Skipped" in result2.delivery_status
