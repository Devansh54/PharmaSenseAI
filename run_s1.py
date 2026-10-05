import os
import sys
import time
import json
from pathlib import Path

from sqlalchemy import create_engine, text
from pharmasense.config import GroqAdapterConfig, CSV_FILES
from pharmasense.llm.groq_adapter import GroqAdapter
from pharmasense.llm.gateway import LLMGateway
from pharmasense.llm.tracing import InMemoryTracer
from pharmasense.orchestration.graph import build_orchestration_graph
from pharmasense.db.source_schema import Base
from pharmasense.data.ingest.import_csvs import import_all_csvs

def setup_eval_db():
    base_url = "postgresql+psycopg2://pharmasense:pharmasense@localhost:5432/pharmasense"
    db_name = "pharmasense_test"
    
    # Ensure DB exists
    eng = create_engine(base_url, isolation_level="AUTOCOMMIT")
    try:
        with eng.connect() as conn:
            conn.execute(text(f"CREATE DATABASE {db_name}"))
    except Exception:
        pass
    
    url = f"postgresql+psycopg2://pharmasense:pharmasense@localhost:5432/{db_name}"
    engine = create_engine(url)
    
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(engine)
    
    count = 0
    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM clinical_trials")).scalar()
    
    if count == 0:
        print("Seeding database...")
        import_all_csvs(engine=engine)
        print("Seeding complete.")
            
    return engine

def main():
    os.environ["LLM_PROVIDER"] = "groq"
    os.environ["LLM_MODEL"] = "qwen/qwen3.8-27b"
    os.environ["EVAL_DATABASE_URL"] = "postgresql+psycopg2://pharmasense:pharmasense@localhost:5432/pharmasense_test"
    
    engine = setup_eval_db()
    
    config = GroqAdapterConfig(model=os.environ["LLM_MODEL"])
    adapter = GroqAdapter(config)
    tracer = InMemoryTracer()
    gateway = LLMGateway(adapter, tracer=tracer)
    
    prompt = "Which Phase II oncology trials are below 60% enrollment right now?"
    case_id = "S1"
    
    print("\n--- RUNNING S1 ---")
    start_time = time.time()
    
    try:
        with engine.connect() as conn:
            graph = build_orchestration_graph(conn, gateway)
            state = graph.invoke({"request_id": case_id, "user_prompt": prompt})
    except Exception as e:
        print(f"FAILED with {type(e).__name__}: {e}")
        sys.exit(1)
        
    latency = (time.time() - start_time) * 1000
    
    errors = state.get("errors", [])
    status = "FAIL" if errors else "PASS"
    
    calls = len(tracer.events)
    in_toks = sum(e.prompt_tokens or 0 for e in tracer.events)
    out_toks = sum(e.completion_tokens or 0 for e in tracer.events)
    retries = len([e for e in tracer.events if e.error])
    
    final_report = state.get("final_report", {})
    specialist_results = state.get("specialist_results", {})
    actual_tools = state.get("actual_tools", [])
    
    print(f"Status: {status}")
    print(f"Errors: {errors}")
    print(f"Calls: {calls} (In: {in_toks}, Out: {out_toks})")
    print(f"Latency: {latency:.1f}ms")
    print(f"Retries: {retries}")
    print(f"Report Content: {final_report.get('report_content')}")
    print(f"Specialists Run: {list(specialist_results.keys())}")
    
    if actual_tools:
        for t in actual_tools:
            print(f"Tool Used: {t.get('tool_name')}")
            print(f"Tool Args: {t.get('arguments')}")
            print(f"Tool Result: {str(t.get('result'))[:500]}...")
            
if __name__ == "__main__":
    main()
