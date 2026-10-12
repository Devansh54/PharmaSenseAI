export interface AnalysisRequest {
  user_prompt: string;
  request_id?: string;
  session_id?: string;
}

export interface CitationOut {
  claim: string;
  citations: string[];
  invalid_chunk_ids: string[];
}

export type BackendAnalysisStatus = 'success' | 'partial_success' | 'no_evidence' | 'failed';

export interface AnalysisResponse {
  status: BackendAnalysisStatus;
  findings: string;
  citations: CitationOut[];
  limitations: string[];
  branch_outcomes: Record<string, string | Record<string, unknown>>;
  escalation_reference: string | null;
  timing_sec: number | null;
  total_tokens: number | null;
  error_message: string | null;
}

export type RequestLifecycleState =
  | 'idle'
  | 'loading'
  | 'success'
  | 'partial_success'
  | 'no_evidence'
  | 'guardrail_refusal'
  | 'failed';

export type ApiErrorCategory =
  | 'validation'
  | 'timeout'
  | 'unavailable'
  | 'network'
  | 'malformed'
  | 'not_found'
  | 'conflict'
  | 'unknown';

export interface ApiClientError {
  isError: true;
  category: ApiErrorCategory;
  statusCode?: number;
  message: string;
}

export interface HealthCheckResponse {
  status: string;
}

export interface EvidenceMetadata {
  doc_id?: string | null;
  compound_id?: string | null;
  trial_id?: string | null;
  doc_type?: string | null;
  title?: string | null;
  [key: string]: unknown;
}

export interface EvidenceResponse {
  evidence_id: string;
  content: string;
  metadata: EvidenceMetadata;
}

export type ReviewStatus = 'PENDING' | 'ACKNOWLEDGED' | 'RESOLVED' | string;

export interface ReviewTask {
  task_id: string;
  event_id: string;
  status: ReviewStatus;
  reason: string;
  created_at: string;
}

export type ReviewDecisionType = 'acknowledged' | 'resolved';

export interface ReviewDecisionPayload {
  reviewer_id: string;
  decision: ReviewDecisionType | string;
  comments?: string;
}

export interface ReviewDecisionResponse {
  status: string;
}
