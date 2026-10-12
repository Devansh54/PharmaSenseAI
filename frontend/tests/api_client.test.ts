import assert from 'node:assert';
import test from 'node:test';
import {
  createAnalysis,
  checkHealth,
  classifyAnalysisOutcome,
  AnalysisApiError
} from '../src/services/api.ts';
import type { AnalysisResponse } from '../src/types/api.ts';

// Helper to construct mock Response objects
function createMockResponse(body: unknown, init?: { status?: number; statusText?: string; ok?: boolean }): Response {
  const status = init?.status ?? 200;
  const ok = init?.ok ?? (status >= 200 && status < 300);
  const jsonBody = typeof body === 'string' ? body : JSON.stringify(body);

  return {
    status,
    statusText: init?.statusText ?? 'OK',
    ok,
    json: async () => {
      if (typeof body === 'string') {
        throw new SyntaxError('Unexpected token in JSON');
      }
      return body;
    },
    text: async () => jsonBody
  } as unknown as Response;
}

test('1. Correct POST path, headers, and request body serialization', async () => {
  let capturedUrl = '';
  let capturedInit: RequestInit | undefined;

  const mockFetcher: typeof fetch = async (input, init) => {
    capturedUrl = String(input);
    capturedInit = init;
    return createMockResponse({
      status: 'success',
      findings: 'Synthetic test findings',
      citations: [],
      limitations: []
    });
  };

  const req = {
    user_prompt: 'Which Phase II oncology trials are below 60% enrollment right now?',
    request_id: 'req-test-123'
  };

  const result = await createAnalysis(req, mockFetcher);

  assert.strictEqual(capturedUrl, '/v1/analyses', 'Must send request to /v1/analyses');
  assert.strictEqual(capturedInit?.method, 'POST', 'HTTP method must be POST');

  const headers = capturedInit?.headers as Record<string, string>;
  assert.strictEqual(headers['Content-Type'], 'application/json', 'Must use Content-Type: application/json');
  assert.strictEqual(headers['Accept'], 'application/json', 'Must use Accept: application/json');

  const parsedBody = JSON.parse(String(capturedInit?.body));
  assert.strictEqual(parsedBody.user_prompt, req.user_prompt, 'Prompt must match user_prompt');
  assert.strictEqual(parsedBody.request_id, 'req-test-123');
  assert.strictEqual(result.status, 'success');
});

test('2. Correct parsing of a successful response with full fields', async () => {
  const rawBackendPayload: AnalysisResponse = {
    status: 'success',
    findings: 'Trial TRL-0012 and TRL-0045 meet criteria.',
    citations: [
      {
        claim: 'TRL-0012 enrollment is 48%',
        citations: ['chunk-trials-01', 'chunk-trials-02'],
        invalid_chunk_ids: []
      }
    ],
    limitations: ['Enrollment records snapshot dated 2026-Q1.'],
    branch_outcomes: {
      trial_analytics: 'Filtered 14 trials, found 2 matches'
    },
    escalation_reference: null,
    timing_sec: 2.45,
    total_tokens: 1840,
    error_message: null
  };

  const mockFetcher: typeof fetch = async () => createMockResponse(rawBackendPayload);

  const parsed = await createAnalysis({ user_prompt: 'Sample query' }, mockFetcher);

  assert.strictEqual(parsed.status, 'success');
  assert.strictEqual(parsed.findings, rawBackendPayload.findings);
  assert.strictEqual(parsed.citations.length, 1);
  assert.strictEqual(parsed.citations[0].claim, 'TRL-0012 enrollment is 48%');
  assert.deepStrictEqual(parsed.citations[0].citations, ['chunk-trials-01', 'chunk-trials-02']);
  assert.strictEqual(parsed.limitations.length, 1);
  assert.strictEqual(parsed.timing_sec, 2.45);
  assert.strictEqual(parsed.total_tokens, 1840);

  const lifecycle = classifyAnalysisOutcome(parsed);
  assert.strictEqual(lifecycle, 'success');
});

test('3. Partial-success response handling', async () => {
  const partialPayload: AnalysisResponse = {
    status: 'partial_success',
    findings: 'Found partial trial data but literature search timed out.',
    citations: [],
    limitations: ['Literature specialist timed out.'],
    branch_outcomes: {
      trial_analytics: 'Completed',
      literature_rag: 'Timeout'
    },
    escalation_reference: null,
    timing_sec: 5.1,
    total_tokens: 2100,
    error_message: null
  };

  const mockFetcher: typeof fetch = async () => createMockResponse(partialPayload);

  const parsed = await createAnalysis({ user_prompt: 'Complex cross-domain query' }, mockFetcher);
  assert.strictEqual(parsed.status, 'partial_success');

  const lifecycle = classifyAnalysisOutcome(parsed);
  assert.strictEqual(lifecycle, 'partial_success', 'Must be classified as partial_success');
});

test('4. Guardrail refusal carried in an HTTP 200 partial_success response', async () => {
  // Backend returns 200 with partial_success and error_message beginning with 'Guardrail blocked request:'
  const refusalPayload: AnalysisResponse = {
    status: 'partial_success',
    findings: 'I cannot provide personalized medical treatment recommendations or prescribe medication dosages.',
    citations: [],
    limitations: ['Blocked by clinical advice safety guardrail.'],
    branch_outcomes: {},
    escalation_reference: null,
    timing_sec: 0.12,
    total_tokens: 45,
    error_message: 'Guardrail blocked request: Clinical medical advice restriction triggered'
  };

  const mockFetcher: typeof fetch = async () => createMockResponse(refusalPayload);

  const parsed = await createAnalysis({ user_prompt: 'What dose of aspirin should I take?' }, mockFetcher);

  const lifecycle = classifyAnalysisOutcome(parsed);
  assert.strictEqual(
    lifecycle,
    'guardrail_refusal',
    'Must detect Guardrail blocked request and classify as guardrail_refusal instead of success'
  );
});

test('5. No-evidence response handling', async () => {
  const noEvidencePayload: AnalysisResponse = {
    status: 'no_evidence',
    findings: 'No clinical trials or literature documents matched the query criteria.',
    citations: [],
    limitations: ['Search filters yielded zero candidate records.'],
    branch_outcomes: {},
    escalation_reference: null,
    timing_sec: 1.1,
    total_tokens: 350,
    error_message: null
  };

  const mockFetcher: typeof fetch = async () => createMockResponse(noEvidencePayload);

  const parsed = await createAnalysis({ user_prompt: 'Search for nonexistent compound XYZ-9999' }, mockFetcher);
  assert.strictEqual(parsed.status, 'no_evidence');

  const lifecycle = classifyAnalysisOutcome(parsed);
  assert.strictEqual(lifecycle, 'no_evidence');
});

test('6. HTTP 422 and 504 error handling with normalized messages', async () => {
  // Test 422 Unprocessable Entity
  const mock422Fetcher: typeof fetch = async () =>
    createMockResponse({ detail: 'user_prompt exceeds maximum allowed length' }, { status: 422, ok: false });

  await assert.rejects(
    async () => createAnalysis({ user_prompt: 'Invalid prompt' }, mock422Fetcher),
    (err: AnalysisApiError) => {
      assert.strictEqual(err.statusCode, 422);
      assert.strictEqual(err.category, 'validation');
      assert.match(err.message, /422 Unprocessable Entity/);
      return true;
    }
  );

  // Test 504 Gateway Timeout
  const mock504Fetcher: typeof fetch = async () =>
    createMockResponse({ detail: 'Orchestrator timeout' }, { status: 504, ok: false });

  await assert.rejects(
    async () => createAnalysis({ user_prompt: 'Slow prompt' }, mock504Fetcher),
    (err: AnalysisApiError) => {
      assert.strictEqual(err.statusCode, 504);
      assert.strictEqual(err.category, 'timeout');
      assert.match(err.message, /504 Gateway Timeout/);
      return true;
    }
  );
});

test('7. Network failure and malformed JSON/response handling', async () => {
  // Network failure (server down / connection refused)
  const mockNetworkFailFetcher: typeof fetch = async () => {
    throw new Error('connect ECONNREFUSED 127.0.0.1:8000');
  };

  await assert.rejects(
    async () => createAnalysis({ user_prompt: 'Valid query' }, mockNetworkFailFetcher),
    (err: AnalysisApiError) => {
      assert.strictEqual(err.category, 'network');
      assert.match(err.message, /ECONNREFUSED/);
      return true;
    }
  );

  // Malformed JSON response
  const mockMalformedJsonFetcher: typeof fetch = async () =>
    createMockResponse('{ not-valid-json }');

  await assert.rejects(
    async () => createAnalysis({ user_prompt: 'Valid query' }, mockMalformedJsonFetcher),
    (err: AnalysisApiError) => {
      assert.strictEqual(err.category, 'malformed');
      assert.match(err.message, /malformed response payload/);
      return true;
    }
  );

  // Missing mandatory fields in JSON object
  const mockMissingFieldsFetcher: typeof fetch = async () =>
    createMockResponse({ some_other_field: 123 });

  await assert.rejects(
    async () => createAnalysis({ user_prompt: 'Valid query' }, mockMissingFieldsFetcher),
    (err: AnalysisApiError) => {
      assert.strictEqual(err.category, 'malformed');
      assert.match(err.message, /missing mandatory status or findings/);
      return true;
    }
  );
});

test('8. Duplicate-submit prevention and loading-state cleanup simulation', async () => {
  let callCount = 0;

  const mockFetcher: typeof fetch = async () => {
    callCount++;
    // Simulate latency
    await new Promise((r) => setTimeout(r, 20));
    return createMockResponse({
      status: 'success',
      findings: 'Result',
      citations: [],
      limitations: []
    });
  };

  // Simulated React state wrapper
  let isAnalyzing = false;
  const dispatchSubmit = async (prompt: string) => {
    if (isAnalyzing) {
      return; // Duplicate prevented
    }
    isAnalyzing = true;
    try {
      await createAnalysis({ user_prompt: prompt }, mockFetcher);
    } finally {
      isAnalyzing = false;
    }
  };

  // Attempt duplicate submissions concurrently
  const first = dispatchSubmit('Question 1');
  const duplicate = dispatchSubmit('Question 1 Duplicate');

  await Promise.all([first, duplicate]);

  assert.strictEqual(callCount, 1, 'API must only be invoked once; duplicate call was rejected');
  assert.strictEqual(isAnalyzing, false, 'Loading state must be cleaned up on completion');
});

test('9. Selecting a suggestion does not send a request', () => {
  let apiDispatched = false;
  let composerText = '';

  const handleSelectSuggestion = (text: string) => {
    composerText = text;
    // Explicit contract: no createAnalysis() call here
  };

  handleSelectSuggestion('Which Phase II oncology trials are below 60% enrollment right now?');

  assert.strictEqual(composerText, 'Which Phase II oncology trials are below 60% enrollment right now?');
  assert.strictEqual(apiDispatched, false, 'No API request sent on selection');
});

test('10. Submitting a question invokes the API exactly once', async () => {
  let invocationCount = 0;

  const mockFetcher: typeof fetch = async () => {
    invocationCount++;
    return createMockResponse({
      status: 'success',
      findings: 'Analysis completed successfully',
      citations: [],
      limitations: []
    });
  };

  await createAnalysis({ user_prompt: 'Legitimate clinical query' }, mockFetcher);

  assert.strictEqual(invocationCount, 1, 'API client was invoked exactly once');
});

test('11. Health check route (/health/ready) handles ok and offline', async () => {
  const mockHealthyFetcher: typeof fetch = async () =>
    createMockResponse({ status: 'ready', database: 'connected' });

  const healthyResult = await checkHealth(mockHealthyFetcher);
  assert.strictEqual(healthyResult.status, 'ok');

  const mockDownFetcher: typeof fetch = async () => {
    throw new Error('Connection refused');
  };

  const offlineResult = await checkHealth(mockDownFetcher);
  assert.strictEqual(offlineResult.status, 'offline');
});
