import os
import sys
import time
import json
from pharmasense.llm.groq_adapter import GroqAdapter
from pharmasense.config import GroqAdapterConfig
from pharmasense.llm.contracts import LLMRequest, Message
import pytest

def main():
    # Step 1: Environment Setup & Check
    os.environ["LLM_PROVIDER"] = "groq"
    os.environ["LLM_MODEL"] = "qwen/qwen3.8-27b"
    os.environ["EVAL_DATABASE_URL"] = "postgresql+psycopg2://pharmasense:pharmasense_test_pw@localhost:5432/pharmasense_test"
    os.environ["PHARMASENSE_TEST_DATABASE_URL"] = os.environ["EVAL_DATABASE_URL"]
    
    print("STEP 1: ENVIRONMENT CHECK")
    print(f"GROQ_API_KEY set: {'True' if os.environ.get('GROQ_API_KEY') else 'False'}")
    print(f"LLM_PROVIDER: {os.environ.get('LLM_PROVIDER')}")
    print(f"LLM_MODEL: {os.environ.get('LLM_MODEL')}")
    print(f"EVAL_DATABASE_URL set: {'True' if os.environ.get('EVAL_DATABASE_URL') else 'False'}")
    print()

    # Step 2: Smoke Test
    print("STEP 2: SMOKE TEST")
    try:
        config = GroqAdapterConfig(model=os.environ["LLM_MODEL"])
        adapter = GroqAdapter(config)
        request = LLMRequest(
            model=os.environ["LLM_MODEL"],
            messages=[Message(role="user", content="Reply with exactly: OK")],
            temperature=0.0,
            max_tokens=10
        )
        response = adapter.complete(request)
        print("SUCCESS")
        print(f"Response: {response.content}")
    except Exception as e:
        print("FAILURE")
        print(f"Exception: {type(e).__name__}: {str(e)}")
        sys.exit(1)
        
if __name__ == "__main__":
    main()
