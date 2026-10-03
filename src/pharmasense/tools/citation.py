"""Citation Formatter Tool.
Resolves claim -> evidence IDs -> citation object.
"""
from typing import List, Dict, Any
from pydantic import BaseModel
from sqlalchemy.orm import Session
from pharmasense.retrieval.references import resolve_reference, ReferenceNotFoundError

class CitationInput(BaseModel):
    claim: str
    evidence_chunk_ids: List[str]

class CitationOutput(BaseModel):
    claim: str
    citations: List[Dict[str, Any]]
    invalid_chunk_ids: List[str]

def citation_formatter_tool(session: Session, input_data: CitationInput) -> CitationOutput:
    """Format evidence into valid citations."""
    citations = []
    invalid = []
    
    for chunk_id in input_data.evidence_chunk_ids:
        try:
            ref = resolve_reference(session, chunk_id)
            citations.append({
                "chunk_id": ref.chunk_id,
                "doc_id": ref.doc_id,
                "title": ref.title,
                "author": ref.author,
                "valid": ref.source_document_exists
            })
        except ReferenceNotFoundError:
            invalid.append(chunk_id)
            
    return CitationOutput(
        claim=input_data.claim,
        citations=citations,
        invalid_chunk_ids=invalid
    )
