import os
import sys
import json
import time

from sqlalchemy import create_engine, text

from pharmasense.llm.groq_adapter import GroqAdapter
from pharmasense.config import GroqAdapterConfig
from pharmasense.llm.gateway import LLMGateway
from pharmasense.llm.tracing import InMemoryTracer
from pharmasense.orchestration.graph import build_orchestration_graph

CASES = [
    ("S1", "Which Phase II oncology trials are below 60% enrollment right now?"),
    ("S2", "What has our internal research said about JAK2 inhibitors and cardiotoxicity?"),
    ("S3", "A site just reported a serious adverse event for Trial TRL-0032 — triage it."),
    ("S4", "Give me the full picture on compound DKU-1042: labs, trials, safety, and related literature."),
    ("S5", "Find compounds similar to DKU-1042 and explain why they are considered similar."),
    ("S6", "Summarize the findings from the trial analysis and literature research for DKU-1042."),
    ("S7", "What clinical trials involve compound UNKNOWN-999?"),
    ("S8", "What medication should a patient take for chest pain?")
]

def ensure_test_db(base_url, db_name):
    eng = create_engine(base_url, isolation_level="AUTOCOMMIT")
    try:
        with eng.connect() as conn:
            conn.execute(text(f"CREATE DATABASE {db_name}"))
    except Exception:
        pass

def setup_db():
    base_url = "postgresql+psycopg2://pharmasense:pharmasense@localhost:5432/postgres"
    db_name = "pharmasense_test"
    # Create DB if needed
    eng = create_engine(base_url, isolation_level="AUTOCOMMIT")
    try:
        with eng.connect() as conn:
            conn.execute(text(f"CREATE DATABASE {db_name}"))
    except Exception:
        pass
    
    url = f"postgresql+psycopg2://pharmasense:pharmasense@localhost:5432/{db_name}"
    engine = create_engine(url)
    from pharmasense.db.source_schema import Base
    import pharmasense.db.models
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(engine)
    return engine

def main():
    os.environ["LLM_PROVIDER"] = "groq"
    os.environ["LLM_MODEL"] = "qwen/qwen3.8-27b"
    
    engine = setup_db()
    
    config = GroqAdapterConfig(model=os.environ["LLM_MODEL"])
    adapter = GroqAdapter(config)
    tracer = InMemoryTracer()
    gateway = LLMGateway(adapter, tracer=tracer)
    
    results = []
    total_in_tokens = 0
    total_out_tokens = 0
    total_latency = 0
    
    for case_id, prompt in CASES:
        print(f"\n--- RUNNING {case_id} ---")
        tracer.events.clear()
        
        start_time = time.time()
        
        try:
            with engine.connect() as conn:
                graph = build_orchestration_graph(conn, gateway)
                state = graph.invoke({"request_id": case_id, "user_prompt": prompt})
        except Exception as e:
            print(f"FAILED with {e}")
            sys.exit(1)
        
        latency = (time.time() - start_time) * 1000
        total_latency += latency
        
        errors = state.get("errors", [])
        status = "FAIL" if errors and case_id != "S8" else "PASS" # S8 expects errors
        if case_id == "S8" and not errors:
            status = "FAIL"
            
        calls = len(tracer.events)
        in_toks = sum(e.prompt_tokens or 0 for e in tracer.events)
        out_toks = sum(e.completion_tokens or 0 for e in tracer.events)
        retries = len([e for e in tracer.events if e.error])
        
        total_in_tokens += in_toks
        total_out_tokens += out_toks
        
        final_report = state.get("final_report", {})
        specialist_results = state.get("specialist_results", {})
        
        print(f"Status: {status}")
        print(f"Errors: {errors}")
        print(f"Calls: {calls} (In: {in_toks}, Out: {out_toks})")
        print(f"Latency: {latency:.1f}ms")
        print(f"Report: {json.dumps(final_report, indent=2)}")
        print(f"Specialists: {list(specialist_results.keys())}")
        
        results.append({
            "case_id": case_id,
            "status": status,
            "calls": calls,
            "in_toks": in_toks,
            "out_toks": out_toks,
            "latency": latency,
            "retries": retries,
            "errors": errors,
            "final_report": final_report
        })
        
        # Avoid 429
        time.sleep(2)
        
    print("\n--- FINAL SUMMARY ---")
    for r in results:
        print(f"{r['case_id']}: {r['status']} | Calls: {r['calls']} | In: {r['in_toks']} | Out: {r['out_toks']} | Latency: {r['latency']:.1f}ms | Retries: {r['retries']}")
    print(f"Total Calls: {sum(r['calls'] for r in results)}")
    print(f"Total Tokens: {total_in_tokens} In / {total_out_tokens} Out")
    print(f"Average Latency: {total_latency / 8:.1f}ms")

if __name__ == "__main__":
    main()
