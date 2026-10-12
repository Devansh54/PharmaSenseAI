import type {
  AnalysisRequest,
  AnalysisResponse,
  ApiClientError,
  EvidenceMetadata,
  EvidenceResponse,
  HealthCheckResponse,
  RequestLifecycleState,
  ReviewDecisionPayload,
  ReviewDecisionResponse,
  ReviewTask
} from '../types/api';

export const PRODUCTION_API_URL = 'https://pharmasense-api.onrender.com';

export const getBaseUrl = (): string => {
  // Support both Vite (import.meta.env) and Node.js test runners (process.env)
  const envProcess = (globalThis as unknown as { process?: { env?: Record<string, string | undefined> } }).process;
  if (envProcess?.env?.VITE_API_BASE_URL) {
    return envProcess.env.VITE_API_BASE_URL;
  }
  // In Node.js test contexts without explicit VITE_API_BASE_URL, default to ''
  if (envProcess?.env && typeof window === 'undefined') {
    return '';
  }

  const metaEnv = (import.meta as unknown as { env?: Record<string, string | boolean | undefined> })?.env;
  const configured = metaEnv?.VITE_API_BASE_URL;
  if (typeof configured === 'string' && configured.trim()) {
    return configured.trim();
  }

  // In production builds, always default to the live Render backend
  if (metaEnv?.PROD) {
    return PRODUCTION_API_URL;
  }

  // Local development defaults to empty string (proxied by Vite to http://127.0.0.1:8000)
  return '';
};

const getServerHint = (): string => {
  const base = getBaseUrl();
  return base
    ? `Please verify that the API server at ${base} is reachable.`
    : 'Please verify that the API server is running on port 8000.';
};

export class AnalysisApiError extends Error {
  category: ApiClientError['category'];
  statusCode?: number;

  constructor(message: string, category: ApiClientError['category'], statusCode?: number) {
    super(message);
    this.name = 'AnalysisApiError';
    this.category = category;
    this.statusCode = statusCode;
  }
}

/**
 * Classifies an AnalysisResponse into a high-level UI lifecycle state.
 * Detects guardrail refusals (even when carried in HTTP 200 partial_success),
 * no_evidence, partial_success, failed, or full success.
 */
export function classifyAnalysisOutcome(res: AnalysisResponse): RequestLifecycleState {
  if (
    res.error_message &&
    res.error_message.toLowerCase().includes('guardrail blocked request')
  ) {
    return 'guardrail_refusal';
  }

  if (res.status === 'no_evidence') {
    return 'no_evidence';
  }

  if (res.status === 'partial_success') {
    return 'partial_success';
  }

  if (res.status === 'failed') {
    return 'failed';
  }

  return 'success';
}

/**
 * Submits an analysis prompt to the PharmaSenseAI backend (/v1/analyses).
 * Accepts an optional fetcher function for zero-cost offline testing.
 */
export async function createAnalysis(
  req: AnalysisRequest,
  fetcher: typeof fetch = fetch
): Promise<AnalysisResponse> {
  const trimmed = req.user_prompt.trim();
  if (!trimmed) {
    throw new AnalysisApiError('Analysis question cannot be empty.', 'validation', 400);
  }
  if (trimmed.length > 2000) {
    throw new AnalysisApiError(
      `Analysis question exceeds 2,000 character limit (${trimmed.length} chars).`,
      'validation',
      422
    );
  }

  const endpoint = `${getBaseUrl()}/v1/analyses`;
  const bodyPayload: AnalysisRequest = {
    user_prompt: trimmed,
    ...(req.request_id ? { request_id: req.request_id } : {}),
    ...(req.session_id ? { session_id: req.session_id } : {})
  };

  let response: Response;
  try {
    response = await fetcher(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json'
      },
      body: JSON.stringify(bodyPayload)
    });
  } catch (err) {
    const errorMsg = err instanceof Error ? err.message : 'Unknown network failure';
    throw new AnalysisApiError(
      `Unable to connect to PharmaSenseAI backend (${errorMsg}). ${getServerHint()}`,
      'network'
    );
  }

  // Handle HTTP errors
  if (!response.ok) {
    let errorDetail = '';
    try {
      const errJson = (await response.json()) as { detail?: string };
      errorDetail = errJson.detail ? `: ${errJson.detail}` : '';
    } catch {
      // Body not JSON
    }

    if (response.status === 422) {
      throw new AnalysisApiError(
        `Request rejected by backend validation (422 Unprocessable Entity)${errorDetail}`,
        'validation',
        422
      );
    }

    if (response.status === 504) {
      throw new AnalysisApiError(
        'Analysis exceeded the server processing deadline (504 Gateway Timeout).',
        'timeout',
        504
      );
    }

    if (response.status === 500 || response.status === 503) {
      throw new AnalysisApiError(
        `Backend service encountered an error (${response.status})${errorDetail}`,
        'unavailable',
        response.status
      );
    }

    throw new AnalysisApiError(
      `Analysis request failed with HTTP ${response.status}${errorDetail}`,
      'unknown',
      response.status
    );
  }

  // Parse JSON response
  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new AnalysisApiError(
      'Received malformed response payload from backend (invalid JSON).',
      'malformed',
      response.status
    );
  }

  // Minimal schema shape validation to avoid crashing UI on unexpected objects
  const parsed = data as Partial<AnalysisResponse>;
  if (!parsed || typeof parsed !== 'object' || typeof parsed.status !== 'string' || typeof parsed.findings !== 'string') {
    throw new AnalysisApiError(
      'Received response structure missing mandatory status or findings fields.',
      'malformed',
      response.status
    );
  }

  return {
    status: parsed.status,
    findings: parsed.findings,
    citations: Array.isArray(parsed.citations) ? parsed.citations : [],
    limitations: Array.isArray(parsed.limitations) ? parsed.limitations : [],
    branch_outcomes:
      parsed.branch_outcomes && typeof parsed.branch_outcomes === 'object'
        ? parsed.branch_outcomes
        : {},
    escalation_reference: parsed.escalation_reference ?? null,
    timing_sec: typeof parsed.timing_sec === 'number' ? parsed.timing_sec : null,
    total_tokens: typeof parsed.total_tokens === 'number' ? parsed.total_tokens : null,
    error_message: parsed.error_message ?? null
  };
}

/**
 * Bounded health check verifying API and PostgreSQL connectivity.
 */
export async function checkHealth(fetcher: typeof fetch = fetch): Promise<HealthCheckResponse> {
  const endpoint = `${getBaseUrl()}/health/ready`;
  try {
    const res = await fetcher(endpoint, {
      method: 'GET',
      headers: { Accept: 'application/json' }
    });
    if (res.ok) {
      return { status: 'ok' };
    }
    return { status: `unavailable (${res.status})` };
  } catch {
    return { status: 'offline' };
  }
}

/**
 * Retrieves a verified evidence chunk excerpt and metadata by ID (GET /v1/evidence/{evidence_id}).
 * Safely URL-encodes the evidence ID segment (e.g. for IDs with colons like DOC-00160::chunk::0).
 * Accepts an optional fetcher function for zero-cost offline testing.
 */
export async function getEvidence(
  evidenceId: string,
  fetcher: typeof fetch = fetch
): Promise<EvidenceResponse> {
  const trimmed = evidenceId ? evidenceId.trim() : '';
  if (!trimmed) {
    throw new AnalysisApiError('Evidence ID cannot be empty.', 'validation', 400);
  }

  const encodedId = encodeURIComponent(trimmed);
  const endpoint = `${getBaseUrl()}/v1/evidence/${encodedId}`;

  let response: Response;
  try {
    response = await fetcher(endpoint, {
      method: 'GET',
      headers: {
        Accept: 'application/json'
      }
    });
  } catch (err) {
    const errorMsg = err instanceof Error ? err.message : 'Unknown network failure';
    throw new AnalysisApiError(
      `Unable to connect to evidence service (${errorMsg}). ${getServerHint()}`,
      'network'
    );
  }

  if (!response.ok) {
    let errorDetail = '';
    try {
      const errJson = (await response.json()) as { detail?: string };
      errorDetail = errJson.detail ? `: ${errJson.detail}` : '';
    } catch {
      // Body not JSON
    }

    if (response.status === 404) {
      throw new AnalysisApiError(
        `Evidence chunk "${trimmed}" was not found in the evidence repository (404 Not Found)${errorDetail}`,
        'not_found',
        404
      );
    }

    if (response.status === 500 || response.status === 503) {
      throw new AnalysisApiError(
        `Evidence service encountered a backend error (${response.status})${errorDetail}`,
        'unavailable',
        response.status
      );
    }

    throw new AnalysisApiError(
      `Failed to retrieve evidence chunk (${response.status})${errorDetail}`,
      'unknown',
      response.status
    );
  }

  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new AnalysisApiError(
      'Received malformed evidence response payload from backend (invalid JSON).',
      'malformed',
      response.status
    );
  }

  const parsed = data as Partial<EvidenceResponse>;
  if (
    !parsed ||
    typeof parsed !== 'object' ||
    typeof parsed.evidence_id !== 'string' ||
    typeof parsed.content !== 'string'
  ) {
    throw new AnalysisApiError(
      'Received evidence structure missing mandatory evidence_id or content fields.',
      'malformed',
      response.status
    );
  }

  return {
    evidence_id: parsed.evidence_id,
    content: parsed.content,
    metadata:
      parsed.metadata && typeof parsed.metadata === 'object'
        ? (parsed.metadata as EvidenceMetadata)
        : {}
  };
}

/**
 * Retrieves the list of human review tasks (GET /v1/reviews).
 * Accepts an optional fetcher function for offline testing.
 */
export async function listReviews(
  fetcher: typeof fetch = fetch
): Promise<ReviewTask[]> {
  const endpoint = `${getBaseUrl()}/v1/reviews`;

  let response: Response;
  try {
    response = await fetcher(endpoint, {
      method: 'GET',
      headers: {
        Accept: 'application/json'
      }
    });
  } catch (err) {
    const errorMsg = err instanceof Error ? err.message : 'Unknown network failure';
    throw new AnalysisApiError(
      `Unable to connect to review service (${errorMsg}). ${getServerHint()}`,
      'network'
    );
  }

  if (!response.ok) {
    let errorDetail = '';
    try {
      const errJson = (await response.json()) as { detail?: string };
      errorDetail = errJson.detail ? `: ${errJson.detail}` : '';
    } catch {
      // Body not JSON
    }

    if (response.status === 500 || response.status === 503) {
      throw new AnalysisApiError(
        `Review service encountered a backend error (${response.status})${errorDetail}`,
        'unavailable',
        response.status
      );
    }

    throw new AnalysisApiError(
      `Failed to list review tasks (${response.status})${errorDetail}`,
      'unknown',
      response.status
    );
  }

  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new AnalysisApiError(
      'Received malformed review list response payload from backend (invalid JSON).',
      'malformed',
      response.status
    );
  }

  if (!Array.isArray(data)) {
    throw new AnalysisApiError(
      'Received review list response that is not an array.',
      'malformed',
      response.status
    );
  }

  return data.map((item: Partial<ReviewTask>) => ({
    task_id: String(item.task_id || ''),
    event_id: String(item.event_id || ''),
    status: String(item.status || 'PENDING'),
    reason: String(item.reason || ''),
    created_at: String(item.created_at || new Date().toISOString())
  }));
}

/**
 * Retrieves a single review task by ID (GET /v1/reviews/{review_id}).
 * Accepts an optional fetcher function for offline testing.
 */
export async function getReview(
  reviewId: string,
  fetcher: typeof fetch = fetch
): Promise<ReviewTask> {
  const trimmed = reviewId ? reviewId.trim() : '';
  if (!trimmed) {
    throw new AnalysisApiError('Review Task ID cannot be empty.', 'validation', 400);
  }

  const encodedId = encodeURIComponent(trimmed);
  const endpoint = `${getBaseUrl()}/v1/reviews/${encodedId}`;

  let response: Response;
  try {
    response = await fetcher(endpoint, {
      method: 'GET',
      headers: {
        Accept: 'application/json'
      }
    });
  } catch (err) {
    const errorMsg = err instanceof Error ? err.message : 'Unknown network failure';
    throw new AnalysisApiError(
      `Unable to connect to review service (${errorMsg}). ${getServerHint()}`,
      'network'
    );
  }

  if (!response.ok) {
    let errorDetail = '';
    try {
      const errJson = (await response.json()) as { detail?: string };
      errorDetail = errJson.detail ? `: ${errJson.detail}` : '';
    } catch {
      // Body not JSON
    }

    if (response.status === 404) {
      throw new AnalysisApiError(
        `Review task "${trimmed}" was not found (404 Not Found)${errorDetail}`,
        'not_found',
        404
      );
    }

    if (response.status === 500 || response.status === 503) {
      throw new AnalysisApiError(
        `Review service encountered a backend error (${response.status})${errorDetail}`,
        'unavailable',
        response.status
      );
    }

    throw new AnalysisApiError(
      `Failed to retrieve review task (${response.status})${errorDetail}`,
      'unknown',
      response.status
    );
  }

  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new AnalysisApiError(
      'Received malformed review response payload from backend (invalid JSON).',
      'malformed',
      response.status
    );
  }

  const parsed = data as Partial<ReviewTask>;
  if (!parsed || typeof parsed !== 'object' || typeof parsed.task_id !== 'string') {
    throw new AnalysisApiError(
      'Received review task missing mandatory task_id field.',
      'malformed',
      response.status
    );
  }

  return {
    task_id: parsed.task_id,
    event_id: String(parsed.event_id || ''),
    status: String(parsed.status || 'PENDING'),
    reason: String(parsed.reason || ''),
    created_at: String(parsed.created_at || '')
  };
}

/**
 * Submits a human review decision (POST /v1/reviews/{review_id}/decisions).
 * Strictly requires reviewer_id and decision ('acknowledged' or 'resolved').
 * Does not retry automatically.
 * Accepts an optional fetcher function for offline testing.
 */
export async function createReviewDecision(
  reviewId: string,
  payload: ReviewDecisionPayload,
  fetcher: typeof fetch = fetch
): Promise<ReviewDecisionResponse> {
  const trimmedId = reviewId ? reviewId.trim() : '';
  if (!trimmedId) {
    throw new AnalysisApiError('Review Task ID cannot be empty.', 'validation', 400);
  }

  const trimmedReviewer = payload.reviewer_id ? payload.reviewer_id.trim() : '';
  if (!trimmedReviewer) {
    throw new AnalysisApiError('Reviewer ID is required to record a decision.', 'validation', 400);
  }

  const trimmedDecision = payload.decision ? payload.decision.trim().toLowerCase() : '';
  if (!trimmedDecision) {
    throw new AnalysisApiError('Decision is required.', 'validation', 400);
  }

  if (trimmedDecision !== 'acknowledged' && trimmedDecision !== 'resolved') {
    throw new AnalysisApiError(
      `Unsupported decision "${trimmedDecision}". Valid decisions are "acknowledged" or "resolved".`,
      'validation',
      400
    );
  }

  const encodedId = encodeURIComponent(trimmedId);
  const endpoint = `${getBaseUrl()}/v1/reviews/${encodedId}/decisions`;
  const bodyPayload: { reviewer_id: string; decision: string; comments?: string } = {
    reviewer_id: trimmedReviewer,
    decision: trimmedDecision,
    ...(payload.comments?.trim() ? { comments: payload.comments.trim() } : {})
  };

  let response: Response;
  try {
    response = await fetcher(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json'
      },
      body: JSON.stringify(bodyPayload)
    });
  } catch (err) {
    const errorMsg = err instanceof Error ? err.message : 'Unknown network failure';
    throw new AnalysisApiError(
      `Unable to connect to review service (${errorMsg}). ${getServerHint()}`,
      'network'
    );
  }

  if (!response.ok) {
    let errorDetail = '';
    try {
      const errJson = (await response.json()) as { detail?: string };
      errorDetail = errJson.detail ? `: ${errJson.detail}` : '';
    } catch {
      // Body not JSON
    }

    if (response.status === 404) {
      throw new AnalysisApiError(
        `Review task "${trimmedId}" was not found (404 Not Found)${errorDetail}`,
        'not_found',
        404
      );
    }

    if (response.status === 409) {
      throw new AnalysisApiError(
        `Invalid review transition (409 Conflict)${errorDetail}`,
        'conflict',
        409
      );
    }

    if (response.status === 422) {
      throw new AnalysisApiError(
        `Decision rejected by backend validation (422 Unprocessable Entity)${errorDetail}`,
        'validation',
        422
      );
    }

    if (response.status === 500 || response.status === 503) {
      throw new AnalysisApiError(
        `Review service encountered a backend error (${response.status})${errorDetail}`,
        'unavailable',
        response.status
      );
    }

    throw new AnalysisApiError(
      `Failed to submit review decision (${response.status})${errorDetail}`,
      'unknown',
      response.status
    );
  }

  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new AnalysisApiError(
      'Received malformed decision response payload from backend (invalid JSON).',
      'malformed',
      response.status
    );
  }

  const parsed = data as { status?: string };
  return {
    status: parsed.status || 'success'
  };
}
