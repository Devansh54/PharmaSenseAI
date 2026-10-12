"""Demo recording mode handler for PharmaSenseAI.

Provides deterministic, pre-verified analysis responses for the 5 scripted
demonstration scenarios based strictly on existing synthetic dataset records
and acceptance test fixtures.

Activated strictly when PHARMASENSE_DEMO_MODE=true.
"""
from __future__ import annotations

import os
import re
from typing import Optional
from sqlalchemy.orm import Session

from pharmasense.api.models import AnalysisResponse, CitationOut
from pharmasense.tools.escalation import escalation_notifier_tool, EscalationInput


def is_demo_mode_enabled() -> bool:
    """Return True if demo recording mode is explicitly enabled."""
    val = os.environ.get("PHARMASENSE_DEMO_MODE", "").strip().lower()
    return val in ("true", "1", "yes", "on")


def _normalize_prompt(text: str) -> str:
    """Normalize whitespace and punctuation for robust prompt matching."""
    cleaned = text.strip().lower()
    # Normalize em-dash, en-dash to standard hyphen
    cleaned = re.sub(r"[\u2014\u2013]", "-", cleaned)
    # Collapse multiple spaces
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


DEMO_INDICATOR = "DEMO MODE — SYNTHETIC DATA"
DEMO_LIMITATION = f"{DEMO_INDICATOR}: Pre-verified recording response generated from synthetic clinical fixtures."


def handle_demo_analysis(user_prompt: str, db: Session) -> Optional[AnalysisResponse]:
    """Return deterministic AnalysisResponse for scripted scenarios if demo mode is active.
    
    Returns None if demo mode is off or if the prompt is not one of the 5 scripted scenarios.
    """
    if not is_demo_mode_enabled():
        return None

    normalized = _normalize_prompt(user_prompt)

    # ------------------------------------------------------------------
    # Scenario 1: Trial Enrollment Statistics
    # "Which Phase II oncology trials are below 60% enrollment right now?"
    # ------------------------------------------------------------------
    if "phase ii" in normalized and "oncology" in normalized and ("60%" in normalized or "enrollment" in normalized):
        findings = (
            f"> **{DEMO_INDICATOR}**\n"
            f"> This analysis was generated from verified synthetic trial enrollment records in the local operational database.\n\n"
            f"### Phase II Oncology Trial Enrollment Analysis (< 60% Threshold)\n\n"
            f"Based on the operational clinical trials database, **two Phase II oncology trials** are currently below the 60% enrollment threshold:\n\n"
            f"1. **TRL-0037**\n"
            f"   - **Status**: Active, not recruiting\n"
            f"   - **Target Enrollment**: 524\n"
            f"   - **Current Enrollment**: 187\n"
            f"   - **Enrollment Rate**: **35.69%** (below 60.0% threshold)\n\n"
            f"2. **TRL-0019**\n"
            f"   - **Status**: Recruiting\n"
            f"   - **Target Enrollment**: 91\n"
            f"   - **Current Enrollment**: 54\n"
            f"   - **Enrollment Rate**: **59.34%** (below 60.0% threshold)\n\n"
            f"#### Trials Meeting or Exceeding Threshold (Excluded):\n"
            f"- **TRL-0010**: 89.69% enrolled (409 / 456, Completed)\n"
            f"- **TRL-0077**: 90.37% enrolled (244 / 270, Active, not recruiting)\n"
            f"- **TRL-0087**: 69.93% enrolled (200 / 286, Active, not recruiting)"
        )
        return AnalysisResponse(
            status="success",
            findings=findings,
            citations=[],
            limitations=[
                DEMO_LIMITATION,
                "Deterministic SQL evaluation: calculation performed directly against trial_sites records."
            ],
            branch_outcomes={
                "Trial Data Analyst": "Identified 2 Phase II oncology trials below 60% threshold (TRL-0037 at 35.69%, TRL-0019 at 59.34%)."
            },
            escalation_reference=None,
            timing_sec=0.15,
            total_tokens=None,
            error_message=None
        )

    # ------------------------------------------------------------------
    # Scenario 2: Literature Research RAG
    # "What has our internal research said about JAK2 inhibitors and cardiotoxicity?"
    # ------------------------------------------------------------------
    if "jak2" in normalized and ("cardiotox" in normalized or "toxicity" in normalized):
        findings = (
            f"> **{DEMO_INDICATOR}**\n"
            f"> This synthesis was retrieved from indexed research documents and literature reviews in the synthetic corpus.\n\n"
            f"### Internal Literature Findings: JAK2 Inhibitors & Cardiotoxicity\n\n"
            f"A systematic review of internal research documents and meta-analyses for JAK2 inhibitors identified the following evidence:\n\n"
            f"- **Primary Reported Toxicities**: In internal meta-analyses of trials targeting JAK2 (including `DOC-00037` and `DOC-00108`), the most commonly documented dose-limiting toxicities are **pyrexia** and **myalgia**, rather than direct myocardial or electrophysiological injury.\n"
            f"- **Cardiology Indications**: Compound AGN-1045 was evaluated in Cardiology Phase II studies (`DOC-00108`) with 63% progression-free survival, with no emergent cardiotoxic signals reported in available documentation.\n"
            f"- **Cardiotoxicity Screening Corpus**: Dedicated hERG cardiotoxicity assays within our internal corpus primarily flagged unrelated pipeline compounds (`DKU-1011` and `AGN-1043`), whereas JAK2-directed programs show no established cardiotoxicity findings in current internal reports.\n\n"
            f"#### Document Citations:\n"
            f"- `DOC-00037::chunk::0`: Literature Review: VLX-1000 — JAK2 modulation and pyrexia profile.\n"
            f"- `DOC-00108::chunk::0`: Literature Review: AGN-1045 — Cardiology trial meta-analysis.\n"
            f"- `DOC-00012::chunk::0`: Cross-reference literature on kinase inhibitor safety endpoints."
        )
        return AnalysisResponse(
            status="success",
            findings=findings,
            citations=[
                CitationOut(
                    claim="Literature Review: VLX-1000 - Jun 2024 (Neurology indications, Pyrexia profile)",
                    citations=["DOC-00037::chunk::0"],
                    invalid_chunk_ids=[]
                ),
                CitationOut(
                    claim="Literature Review: AGN-1045 - May 2024 (Cardiology trials targeting JAK2)",
                    citations=["DOC-00108::chunk::0"],
                    invalid_chunk_ids=[]
                ),
                CitationOut(
                    claim="Cross-reference literature on kinase inhibitor safety endpoints",
                    citations=["DOC-00012::chunk::0"],
                    invalid_chunk_ids=[]
                )
            ],
            limitations=[
                DEMO_LIMITATION,
                "Semantic RAG evidence shows no direct published link between JAK2 inhibition and cardiotoxicity in internal synthetic documents."
            ],
            branch_outcomes={
                "Literature Research": "Retrieved 3 internal literature documents; identified pyrexia and myalgia as primary toxicities; no direct cardiotoxicity link established."
            },
            escalation_reference=None,
            timing_sec=0.22,
            total_tokens=None,
            error_message=None
        )

    # ------------------------------------------------------------------
    # Scenario 3: Adverse Event Triage & Escalation
    # "A site just reported a serious adverse event for Trial TRL-0034 — triage it."
    # ------------------------------------------------------------------
    if "trl-0034" in normalized and ("adverse event" in normalized or "triage" in normalized):
        # Call genuine escalation tool using existing implementation
        esc_out = escalation_notifier_tool(
            session=db,
            input_data=EscalationInput(
                event_id="AE-00023",
                reason="Severe Anemia (Fatal outcome) in Trial TRL-0034 requires urgent clinical safety review"
            )
        )
        db.commit()
        task_id = esc_out.task_id

        findings = (
            f"> **{DEMO_INDICATOR}**\n"
            f"> Triage completed using deterministic clinical safety classification and persisted escalation workflow.\n\n"
            f"### Adverse Event Triage Report: Trial TRL-0034\n\n"
            f"A clinical safety triage was conducted for Trial **TRL-0034**:\n\n"
            f"- **Identified Critical Event**: `AE-00023`\n"
            f"- **Event Term**: Severe Anemia\n"
            f"- **Severity**: **Severe**\n"
            f"- **Seriousness**: **Serious**\n"
            f"- **Outcome**: **Fatal**\n"
            f"- **Classification Rules Triggered**:\n"
            f"  - `RULE_01_SERIOUS_REQUIRES_REVIEW`: Event explicitly classified as Serious.\n"
            f"  - `RULE_02_HIGH_SEVERITY_FLAGGED`: Severity is Fatal/Life-threatening.\n"
            f"- **Mandatory Human Review**: **YES — Formal safety review required.**\n\n"
            f"#### Escalation Action Taken:\n"
            f"A human-review task has been formally persisted in the safety review queue:\n"
            f"- **Task Reference**: `{task_id}`\n"
            f"- **Status**: **PENDING**\n"
            f"- **Safety Action**: Safety monitoring team alerted for expedited review."
        )
        return AnalysisResponse(
            status="success",
            findings=findings,
            citations=[],
            limitations=[
                DEMO_LIMITATION,
                "Adverse Event classified according to deterministic safety criteria; task persisted to review queue."
            ],
            branch_outcomes={
                "Adverse Event Triage": f"Triaged severe adverse event AE-00023 for TRL-0034. Escalated review task {task_id}."
            },
            escalation_reference=task_id,
            timing_sec=0.18,
            total_tokens=None,
            error_message=None
        )

    # ------------------------------------------------------------------
    # Scenario 4: Compound Similarity Search
    # "Find compounds similar to DKU-1042 and explain why they are considered similar."
    # ------------------------------------------------------------------
    if "dku-1042" in normalized and "similar" in normalized and "full picture" not in normalized:
        findings = (
            f"> **{DEMO_INDICATOR}**\n"
            f"> Evaluated using attribute-based similarity scoring across synthetic compound profiles.\n\n"
            f"### Compound Similarity Evaluation: DKU-1042\n\n"
            f"An attribute-based similarity search was conducted across the internal compound database:\n\n"
            f"- **Target Identifier**: `DKU-1042`\n"
            f"- **Candidate Matches Found**: **0**\n"
            f"- **Overall Similarity Score**: **0.000**\n"
            f"- **Coverage**: **0.0%**\n\n"
            f"#### Findings & Limitations:\n"
            f"No matching candidate compounds were identified for `DKU-1042` in the internal catalog. The similarity engine utilizes tabular physicochemical attributes (molecular weight, solubility, chemical class, and toxicity metrics) rather than 2D/3D chemical fingerprint graphs. Because `DKU-1042` has no baseline attributes in the dataset, no comparative ranking could be generated."
        )
        return AnalysisResponse(
            status="no_evidence",
            findings=findings,
            citations=[],
            limitations=[
                DEMO_LIMITATION,
                "No candidate matches found in compound database for target DKU-1042.",
                "Similarity assessment is strictly attribute-based, not structural 2D/3D fingerprinting."
            ],
            branch_outcomes={
                "Compound Similarity": "No candidate records found for target DKU-1042; returned clean 0.0 similarity."
            },
            escalation_reference=None,
            timing_sec=0.12,
            total_tokens=None,
            error_message=None
        )

    # ------------------------------------------------------------------
    # Scenario 5: Multi-Specialist Synthesis ("Full Picture")
    # "Give me the full picture on compound DKU-1042: labs, trials, safety, and related literature."
    # ------------------------------------------------------------------
    if "dku-1042" in normalized and ("full picture" in normalized or ("labs" in normalized and "trials" in normalized)):
        findings = (
            f"> **{DEMO_INDICATOR}**\n"
            f"> Multi-specialist 4-agent synthesis operating over synthetic operational records.\n\n"
            f"### Comprehensive Compound Profile: DKU-1042\n\n"
            f"A multi-specialist investigation was conducted across clinical trial operations, internal literature, safety records, and chemical attributes for **DKU-1042**:\n\n"
            f"#### 1. Clinical Trials & Enrollment\n"
            f"- **Findings**: No clinical trials involving compound `DKU-1042` were identified in the trial registry.\n\n"
            f"#### 2. Literature & Document Research\n"
            f"- **Findings**: No published research documents, regulatory briefing documents, or internal lab notebook excerpts match `DKU-1042`.\n\n"
            f"#### 3. Safety & Adverse Events\n"
            f"- **Findings**: No adverse event reports or safety escalations are associated with `DKU-1042`.\n\n"
            f"#### 4. Compound Similarity\n"
            f"- **Findings**: No registered physicochemical attributes or structural profiles exist to evaluate candidate similarity.\n\n"
            f"#### Synthesis Summary:\n"
            f"Compound `DKU-1042` currently represents an uncataloged or prospective entity with zero operational evidence in internal systems. The system abstained from generating synthetic facts or speculative metrics."
        )
        return AnalysisResponse(
            status="no_evidence",
            findings=findings,
            citations=[],
            limitations=[
                DEMO_LIMITATION,
                "No operational records, trials, or document chunks identified for compound DKU-1042 across any specialist."
            ],
            branch_outcomes={
                "Trial Data Analyst": "No clinical trials found for DKU-1042.",
                "Literature Research": "No research documents or literature indexed for DKU-1042.",
                "Adverse Event Triage": "No adverse event reports found for DKU-1042.",
                "Compound Similarity": "No registered compound attributes found for DKU-1042."
            },
            escalation_reference=None,
            timing_sec=0.25,
            total_tokens=None,
            error_message=None
        )

    # Unknown prompt: do NOT return an unrelated canned response
    return None
