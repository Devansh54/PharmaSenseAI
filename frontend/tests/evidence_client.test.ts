import assert from 'node:assert';
import test from 'node:test';
import { getEvidence, AnalysisApiError } from '../src/services/api.ts';
import { getStatusDisplay } from '../src/services/responseFormatter.ts';
import type { EvidenceResponse } from '../src/types/api.ts';

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

test('1. Correct evidence route construction and path encoding for IDs with colons', async () => {
  let capturedUrl = '';
  let capturedInit: RequestInit | undefined;

  const mockFetcher: typeof fetch = async (input, init) => {
    capturedUrl = String(input);
    capturedInit = init;
    return createMockResponse({
      evidence_id: 'DOC-00160::chunk::0',
      content: 'Synthetic trial protocol document excerpt.',
      metadata: {
        doc_id: 'DOC-00160',
        title: 'Phase II Oncology Protocol'
      }
    });
  };

  const rawChunkId = 'DOC-00160::chunk::0';
  const result = await getEvidence(rawChunkId, mockFetcher);

  assert.strictEqual(
    capturedUrl,
    '/v1/evidence/DOC-00160%3A%3Achunk%3A%3A0',
    'Evidence ID with colons must be safely URL-encoded as path segment'
  );
  assert.strictEqual(capturedInit?.method, 'GET', 'Method must be GET');
  const headers = capturedInit?.headers as Record<string, string>;
  assert.strictEqual(headers.Accept, 'application/json');
  assert.strictEqual(result.evidence_id, rawChunkId);
  assert.strictEqual(result.content, 'Synthetic trial protocol document excerpt.');
});

test('2. Successful evidence response parsing with full metadata attributes', async () => {
  const mockPayload: EvidenceResponse = {
    evidence_id: 'DOC-00042::chunk::3',
    content: 'Primary endpoint was progression-free survival (PFS) assessed at 12 months.',
    metadata: {
      doc_id: 'DOC-00042',
      compound_id: 'DKU-1042',
      trial_id: 'TRL-0034',
      doc_type: 'Clinical Study Protocol',
      title: 'A Phase 2 Evaluation of DKU-1042 in Solid Tumors'
    }
  };

  const mockFetcher: typeof fetch = async () => createMockResponse(mockPayload);

  const evidence = await getEvidence('DOC-00042::chunk::3', mockFetcher);

  assert.strictEqual(evidence.evidence_id, 'DOC-00042::chunk::3');
  assert.strictEqual(evidence.content, mockPayload.content);
  assert.strictEqual(evidence.metadata.doc_id, 'DOC-00042');
  assert.strictEqual(evidence.metadata.compound_id, 'DKU-1042');
  assert.strictEqual(evidence.metadata.trial_id, 'TRL-0034');
  assert.strictEqual(evidence.metadata.doc_type, 'Clinical Study Protocol');
  assert.strictEqual(evidence.metadata.title, 'A Phase 2 Evaluation of DKU-1042 in Solid Tumors');
});

test('3. HTTP 404 behavior maps to not_found category with descriptive message', async () => {
  const mock404Fetcher: typeof fetch = async () =>
    createMockResponse({ detail: 'Evidence not found' }, { status: 404, ok: false });

  await assert.rejects(
    async () => getEvidence('DOC-99999::chunk::9', mock404Fetcher),
    (err: AnalysisApiError) => {
      assert.strictEqual(err.statusCode, 404);
      assert.strictEqual(err.category, 'not_found');
      assert.match(err.message, /DOC-99999::chunk::9/);
      assert.match(err.message, /404 Not Found/);
      return true;
    }
  );
});

test('4. Network failure and malformed response behavior', async () => {
  // A. Network failure
  const mockFailFetcher: typeof fetch = async () => {
    throw new Error('Connection refused by host');
  };

  await assert.rejects(
    async () => getEvidence('DOC-00010::chunk::1', mockFailFetcher),
    (err: AnalysisApiError) => {
      assert.strictEqual(err.category, 'network');
      assert.match(err.message, /Connection refused/);
      return true;
    }
  );

  // B. Malformed response missing content
  const mockMissingContentFetcher: typeof fetch = async () =>
    createMockResponse({ evidence_id: 'DOC-00010::chunk::1' }); // missing 'content'

  await assert.rejects(
    async () => getEvidence('DOC-00010::chunk::1', mockMissingContentFetcher),
    (err: AnalysisApiError) => {
      assert.strictEqual(err.category, 'malformed');
      assert.match(err.message, /missing mandatory evidence_id or content/);
      return true;
    }
  );
});

test('5. Empty or whitespace-only evidence ID rejected with validation error', async () => {
  await assert.rejects(
    async () => getEvidence('   '),
    (err: AnalysisApiError) => {
      assert.strictEqual(err.category, 'validation');
      assert.strictEqual(err.statusCode, 400);
      assert.match(err.message, /cannot be empty/);
      return true;
    }
  );
});

test('6. Session caching simulation: cached items avoid repeat fetch; failures not cached', async () => {
  let fetchCount = 0;
  const mockFetcher: typeof fetch = async () => {
    fetchCount++;
    return createMockResponse({
      evidence_id: 'DOC-00100::chunk::1',
      content: 'Cached excerpt test content',
      metadata: {}
    });
  };

  // Simulated React component session cache
  const cache: Record<string, EvidenceResponse> = {};

  const retrieveWithCache = async (id: string): Promise<EvidenceResponse> => {
    if (cache[id]) {
      return cache[id];
    }
    const res = await getEvidence(id, mockFetcher);
    cache[id] = res;
    return res;
  };

  // First fetch (cache miss)
  const item1 = await retrieveWithCache('DOC-00100::chunk::1');
  assert.strictEqual(fetchCount, 1);
  assert.strictEqual(item1.evidence_id, 'DOC-00100::chunk::1');

  // Second fetch for same ID (cache hit)
  const item2 = await retrieveWithCache('DOC-00100::chunk::1');
  assert.strictEqual(fetchCount, 1, 'Cache hit must NOT make a second network call');
  assert.strictEqual(item2.content, 'Cached excerpt test content');

  // Verify failure is not stored in cache
  let failCount = 0;
  const mockFailFetcher: typeof fetch = async () => {
    failCount++;
    return createMockResponse({ detail: 'Not found' }, { status: 404, ok: false });
  };

  try {
    const res = await getEvidence('DOC-FAIL::chunk::0', mockFailFetcher);
    cache['DOC-FAIL::chunk::0'] = res;
  } catch {
    // Expected failure
  }

  assert.strictEqual(cache['DOC-FAIL::chunk::0'], undefined, 'Failed response must NOT be stored in cache');
  assert.strictEqual(failCount, 1);
});

test('7. Optional metadata handling safely renders missing fields without placeholders', async () => {
  // Evidence with sparse metadata
  const sparsePayload: EvidenceResponse = {
    evidence_id: 'DOC-SPARSE::chunk::0',
    content: 'Excerpt text without extra document metadata.',
    metadata: {} // empty metadata
  };

  const mockFetcher: typeof fetch = async () => createMockResponse(sparsePayload);

  const result = await getEvidence('DOC-SPARSE::chunk::0', mockFetcher);
  assert.strictEqual(result.evidence_id, 'DOC-SPARSE::chunk::0');
  assert.strictEqual(result.metadata.title, undefined);
  assert.strictEqual(result.metadata.trial_id, undefined);
  assert.strictEqual(result.metadata.compound_id, undefined);
});

test('8. Success status label correctness check: does not claim clinical validation', () => {
  const display = getStatusDisplay('success');
  assert.strictEqual(
    display.label,
    'Analysis Completed',
    'Status label must be "Analysis Completed" to avoid implying clinical validation'
  );
  assert.notStrictEqual(
    display.label,
    'Verified Analysis',
    'Label "Verified Analysis" must NOT be used'
  );
});
