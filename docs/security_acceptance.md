# Security and Acceptance Guardrails

PharmaSense AI implements a robust set of security and acceptance guardrails to ensure that all interactions and generated reports are safe, appropriate, and firmly grounded in factual evidence.

## Guardrail Architecture

The guardrails are enforced as discrete boundaries within the LangGraph orchestration framework, ensuring that validation happens independently of the core generation logic.

1. **Input Guardrail (Pre-execution)**
   - **Medical Advice Detection**: Uses a lightweight LLM classifier (`gpt-4.1-mini`) to semantically detect requests for personalized medical advice or diagnoses. If detected, the request is blocked and a canned refusal message is returned immediately.
   - **Prompt Injection Screening**: Uses heuristic/deterministic rules (and integrated LLM screening via vector retrieval filtering) to prevent adversarial prompt injection.

2. **Specialist Execution Guardrails**
   - **Tool-Level Screening**: Tools such as vector search implement localized deterministic checks to prevent injection vectors from poisoning context retrieval.

3. **Output Guardrail (Post-execution)**
   - **Evidence Validation**: The `OutputGuardrailNode` uses a lightweight LLM classifier to verify that all claims within the draft final report are supported by cited evidence.
   - **Automatic Repair**: If unsupported claims (hallucinations) are detected, the guardrail provides validation feedback to the Report Writer, which is given exactly one attempt to repair the response.
   - **Failure Blocking**: If the report fails evidence validation a second time, the output is blocked entirely and a safe fallback message is returned to the user.
   - **PII Scrubbing**: Before any payload leaves the system (or hits the LLM), the LLM Gateway (`OpenAIAdapter`) automatically scrubs deterministic PII (SSNs, Phone Numbers, Email Addresses).

## Enforcement and Testing
All guardrails are tested via `tests/test_security_acceptance.py` and `tests/validation/` to guarantee that legitimate research requests proceed while unsafe requests are deterministically blocked.
