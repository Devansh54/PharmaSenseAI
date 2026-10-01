"""Shared helpers for Phase 3 RAG tests.

Not a test module itself - inserts the minimal parent rows a
document_chunks row's foreign keys require.
"""
from __future__ import annotations

from datetime import date as date_type
from typing import Optional

from sqlalchemy.orm import Session

from pharmasense.db.source_schema import ClinicalTrial, Compound, ResearchDocument


def make_compound(session: Session, compound_id: str = "CMP-0001") -> Compound:
    compound = Compound(compound_id=compound_id, compound_name=f"Compound {compound_id}")
    session.add(compound)
    session.flush()
    return compound


def make_clinical_trial(session: Session, trial_id: str, compound_id: str) -> ClinicalTrial:
    trial = ClinicalTrial(trial_id=trial_id, compound_id=compound_id, trial_phase="Phase I")
    session.add(trial)
    session.flush()
    return trial


def make_research_document(
    session: Session,
    doc_id: str,
    full_text: str,
    compound_id: Optional[str] = None,
    trial_id: Optional[str] = None,
    doc_type: str = "Lab Notebook Entry",
    title: Optional[str] = None,
    date: Optional[date_type] = None,
    tags: Optional[str] = None,
    author: str = "Test Author",
) -> ResearchDocument:
    doc = ResearchDocument(
        doc_id=doc_id,
        compound_id=compound_id,
        trial_id=trial_id,
        doc_type=doc_type,
        title=title or f"Doc {doc_id}",
        author=author,
        date=date or date_type(2024, 1, 1),
        full_text=full_text,
        tags=tags or "",
    )
    session.add(doc)
    session.flush()
    return doc
