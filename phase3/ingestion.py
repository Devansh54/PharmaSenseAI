"""Executable Phase 3 ingestion: chunk + embed research_documents into
document_chunks.

Usage:
    python -m phase3.ingestion

Mirrors Phase 1's ingestion pattern (phase1.ingestion.import_csvs):
truncates and reloads document_chunks inside a single transaction from
the current contents of research_documents. research_documents itself
is read-only here; nothing is ever deleted from it.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import date as date_type
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from phase1.db.models import ResearchDocument
from phase3.chunking import chunk_document
from phase3.config import INDEX_VERSION
from phase3.db.models import DocumentChunk
from phase3.embeddings import EmbeddingProvider

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SourceDocument:
    """The subset of research_documents columns chunking/ingestion needs."""

    doc_id: str
    compound_id: Optional[str]
    trial_id: Optional[str]
    doc_type: Optional[str]
    title: Optional[str]
    date: Optional[date_type]
    tags: Optional[str]
    full_text: str

    @classmethod
    def from_orm(cls, row: ResearchDocument) -> "SourceDocument":
        return cls(
            doc_id=row.doc_id,
            compound_id=row.compound_id,
            trial_id=row.trial_id,
            doc_type=row.doc_type,
            title=row.title,
            date=row.date,
            tags=row.tags,
            full_text=row.full_text or "",
        )


def content_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def build_chunk_rows(
    doc: SourceDocument,
    embedder: EmbeddingProvider,
    seen_hashes: Dict[str, str],
    index_version: str = INDEX_VERSION,
) -> List[DocumentChunk]:
    """Build (unsaved) DocumentChunk rows for one document.

    seen_hashes maps a chunk's content hash to the chunk_id that first
    produced it across the whole ingestion run, so exact repeats of
    the same body text - e.g. boilerplate paragraphs reused verbatim
    across documents - are flagged is_duplicate and linked to that
    canonical chunk instead of being treated as new content. The
    source document/chunk is still stored, never dropped.
    """
    chunks = chunk_document(doc.full_text)
    vectors = embedder.embed([c.text for c in chunks])

    rows: List[DocumentChunk] = []
    now = datetime.now(timezone.utc)
    for chunk, vector in zip(chunks, vectors):
        chunk_id = f"{doc.doc_id}::chunk::{chunk.index}"
        h = content_hash(chunk.text)
        canonical_id = seen_hashes.get(h)
        is_duplicate = canonical_id is not None
        if not is_duplicate:
            seen_hashes[h] = chunk_id

        rows.append(
            DocumentChunk(
                chunk_id=chunk_id,
                doc_id=doc.doc_id,
                compound_id=doc.compound_id,
                trial_id=doc.trial_id,
                doc_type=doc.doc_type,
                title=doc.title,
                date=doc.date,
                tags=doc.tags,
                chunk_index=chunk.index,
                chunk_count=len(chunks),
                chunk_text=chunk.text,
                token_count=chunk.token_count,
                content_hash=h,
                is_duplicate=is_duplicate,
                duplicate_of_chunk_id=canonical_id,
                embedding=vector,
                embedding_model=embedder.model_name,
                index_version=index_version,
                created_at=now,
            )
        )
    return rows


def run_ingestion(
    session: Session,
    embedder: EmbeddingProvider,
    index_version: str = INDEX_VERSION,
) -> Dict:
    """Truncate and reload document_chunks from research_documents.

    Runs inside the caller's transaction and commits on success.
    Never modifies research_documents. Returns a small summary dict
    (documents processed, chunks written, duplicate chunks found) so
    callers/CI logs can report what was actually ingested.
    """
    docs = [SourceDocument.from_orm(r) for r in session.query(ResearchDocument).all()]
    session.query(DocumentChunk).delete()

    seen_hashes: Dict[str, str] = {}
    total_chunks = 0
    duplicate_chunks = 0
    for doc in docs:
        for row in build_chunk_rows(doc, embedder, seen_hashes, index_version=index_version):
            session.add(row)
            total_chunks += 1
            if row.is_duplicate:
                duplicate_chunks += 1
    session.commit()

    summary = {
        "documents_processed": len(docs),
        "chunks_written": total_chunks,
        "duplicate_chunks": duplicate_chunks,
        "embedding_model": embedder.model_name,
        "index_version": index_version,
    }
    logger.info("Phase 3 ingestion summary: %s", summary)
    return summary


def main() -> None:  # pragma: no cover - thin CLI wrapper
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from phase1.config import DATABASE_URL
    from phase3.embeddings import BGEEmbedder

    engine = create_engine(DATABASE_URL)
    session_local = sessionmaker(bind=engine)
    with session_local() as session:
        embedder = BGEEmbedder()
        summary = run_ingestion(session, embedder)
        print(summary)


if __name__ == "__main__":  # pragma: no cover
    main()
