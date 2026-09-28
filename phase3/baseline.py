"""Initial labeled retrieval baseline for the Phase 3 RAG index.

Loads a small hand-labeled "golden set" of (query, expected doc_id(s))
pairs from golden_set.json, runs retrieval for each, and reports hit@k
plus per-query hits, mirroring the audit-report pattern from Phase 1
(phase1.audit.run_audit).

This baseline is only as meaningful as the embedder it runs with: run
it with the real BGEEmbedder (`python -m phase3.baseline`) for a
production-meaningful number. Unit tests exercise the scoring/report
logic itself against a DeterministicFakeEmbedder and synthetic
fixtures, which validates the pipeline but is not a claim about real
retrieval quality.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from phase3.config import GOLDEN_SET_PATH, REPORTS_DIR
from phase3.embeddings import EmbeddingProvider
from phase3.retrieval import RetrievalFilters, search


@dataclass(frozen=True)
class GoldenQuery:
    query: str
    expected_doc_ids: List[str] = field(default_factory=list)
    top_k: int = 5
    expect_empty: bool = False
    filters: Dict[str, str] = field(default_factory=dict)


def load_golden_set(path: Path = GOLDEN_SET_PATH) -> List[GoldenQuery]:
    with open(path) as fh:
        raw = json.load(fh)
    return [
        GoldenQuery(
            query=r["query"],
            expected_doc_ids=r.get("expected_doc_ids", []),
            top_k=r.get("top_k", 5),
            expect_empty=r.get("expect_empty", False),
            filters=r.get("filters", {}),
        )
        for r in raw
    ]


def run_baseline(
    session: Session,
    embedder: EmbeddingProvider,
    golden_set: Optional[List[GoldenQuery]] = None,
) -> Dict:
    golden_set = golden_set if golden_set is not None else load_golden_set()
    per_query = []
    hits = 0
    for gq in golden_set:
        filters = RetrievalFilters(**gq.filters) if gq.filters else None
        results = search(session, gq.query, embedder, top_k=gq.top_k, filters=filters)
        retrieved_doc_ids = [r.reference.doc_id for r in results]

        if gq.expect_empty:
            hit = len(retrieved_doc_ids) == 0
        else:
            hit = any(doc_id in retrieved_doc_ids for doc_id in gq.expected_doc_ids)
        if hit:
            hits += 1

        per_query.append(
            {
                "query": gq.query,
                "expected_doc_ids": gq.expected_doc_ids,
                "expect_empty": gq.expect_empty,
                "retrieved_doc_ids": retrieved_doc_ids,
                "hit": hit,
            }
        )

    total = len(golden_set)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "embedding_model": embedder.model_name,
        "total_queries": total,
        "hits": hits,
        "hit_rate_at_k": (hits / total) if total else None,
        "per_query": per_query,
    }


def write_report(report: Dict, out_dir: Path = REPORTS_DIR) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = out_dir / f"retrieval_baseline_{timestamp}.json"
    with open(json_path, "w") as fh:
        json.dump(report, fh, indent=2, default=str)
    latest = out_dir / "retrieval_baseline_latest.json"
    with open(latest, "w") as fh:
        json.dump(report, fh, indent=2, default=str)
    return json_path


def main() -> None:  # pragma: no cover - thin CLI wrapper
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from phase1.config import DATABASE_URL
    from phase3.embeddings import BGEEmbedder

    engine = create_engine(DATABASE_URL)
    session_local = sessionmaker(bind=engine)
    with session_local() as session:
        embedder = BGEEmbedder()
        report = run_baseline(session, embedder)
        path = write_report(report)
        print(f"Baseline report written to {path}")
        print(f"Hit rate @k: {report['hit_rate_at_k']} ({report['hits']}/{report['total_queries']})")


if __name__ == "__main__":  # pragma: no cover
    main()
