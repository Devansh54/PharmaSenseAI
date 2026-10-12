import type { AnalysisResponse, CitationOut, RequestLifecycleState } from '../types/api.ts';

const SPECIALIST_LABELS: Record<string, string> = {
  trial_data_analyst: 'Trial Data Analyst',
  literature_research: 'Literature Research (RAG)',
  compound_similarity: 'Compound Similarity',
  similarity_agent: 'Compound Similarity',
  adverse_event_triage: 'Adverse Event Triage',
  report_writer: 'Report Writer'
};

/**
 * Formats specialist agent identifiers into human-friendly display titles.
 */
export function formatSpecialistName(key: string): string {
  if (SPECIALIST_LABELS[key]) {
    return SPECIALIST_LABELS[key];
  }
  return key
    .replace(/[_-]/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

/**
 * Splits raw findings into readable paragraphs while preserving structure.
 */
export function parseFindingsParagraphs(findings: string | null | undefined): string[] {
  const trimmed = (findings || '').trim();
  if (!trimmed) {
    return [];
  }
  return trimmed.split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean);
}

/**
 * Extracts and deduplicates unverified citation chunk IDs from citations.
 */
export function extractInvalidChunkIds(citations: CitationOut[] | null | undefined): string[] {
  if (!Array.isArray(citations)) {
    return [];
  }
  const invalid = citations.flatMap((c) => (Array.isArray(c.invalid_chunk_ids) ? c.invalid_chunk_ids : []));
  return Array.from(new Set(invalid)).filter(Boolean);
}

export interface StatusDisplayInfo {
  label: string;
  badgeClass: string;
  isRefusal: boolean;
  isPartial: boolean;
  isNoEvidence: boolean;
  isSuccess: boolean;
  isFailed: boolean;
}

/**
 * Maps lifecycle states to truthful UI labels, classes, and boolean flags.
 */
export function getStatusDisplay(state: RequestLifecycleState): StatusDisplayInfo {
  switch (state) {
    case 'guardrail_refusal':
      return {
        label: 'Guardrail Safety Refusal',
        badgeClass: 'guardrail_refusal',
        isRefusal: true,
        isPartial: false,
        isNoEvidence: false,
        isSuccess: false,
        isFailed: false
      };
    case 'no_evidence':
      return {
        label: 'No Evidence Identified',
        badgeClass: 'no_evidence',
        isRefusal: false,
        isPartial: false,
        isNoEvidence: true,
        isSuccess: false,
        isFailed: false
      };
    case 'partial_success':
      return {
        label: 'Partial Success',
        badgeClass: 'partial_success',
        isRefusal: false,
        isPartial: true,
        isNoEvidence: false,
        isSuccess: false,
        isFailed: false
      };
    case 'failed':
      return {
        label: 'Analysis Failed',
        badgeClass: 'failed',
        isRefusal: false,
        isPartial: false,
        isNoEvidence: false,
        isSuccess: false,
        isFailed: true
      };
    case 'success':
    default:
      return {
        label: 'Analysis Completed',
        badgeClass: 'success',
        isRefusal: false,
        isPartial: false,
        isNoEvidence: false,
        isSuccess: true,
        isFailed: false
      };
  }
}

export interface TelemetryDisplayInfo {
  latencyStr: string | null;
  tokensStr: string | null;
  escalationRef: string | null;
  hasTelemetry: boolean;
}

/**
 * Formats metadata only when genuinely provided by the backend (never fabricating 0s or missing values).
 */
export function formatTelemetryData(response: AnalysisResponse | null | undefined): TelemetryDisplayInfo {
  if (!response) {
    return { latencyStr: null, tokensStr: null, escalationRef: null, hasTelemetry: false };
  }

  const latencyStr =
    typeof response.timing_sec === 'number' && response.timing_sec !== null
      ? `${response.timing_sec.toFixed(2)}s`
      : null;

  // Distinguish missing tokens from genuine positive count; do not fabricate "0"
  const tokensStr =
    typeof response.total_tokens === 'number' && response.total_tokens !== null && response.total_tokens > 0
      ? response.total_tokens.toLocaleString()
      : null;

  const escalationRef =
    response.escalation_reference && typeof response.escalation_reference === 'string'
      ? response.escalation_reference.trim() || null
      : null;

  const hasTelemetry = Boolean(latencyStr || tokensStr || escalationRef);

  return { latencyStr, tokensStr, escalationRef, hasTelemetry };
}

export interface FormattedOutcome {
  leadSummary: string | null;
  text: string | null;
  attributes: { key: string; value: string }[] | null;
  listItems: string[] | null;
  isEmpty: boolean;
}

/**
 * Parses and formats specialist outcome payload into structured display elements.
 */
export function formatSpecialistOutcome(outcome: unknown): FormattedOutcome {
  if (outcome === null || outcome === undefined || outcome === '') {
    return { leadSummary: null, text: null, attributes: null, listItems: null, isEmpty: true };
  }

  if (typeof outcome === 'string') {
    const trimmed = outcome.trim();
    if (trimmed.startsWith('{') && trimmed.endsWith('}')) {
      try {
        const parsed = JSON.parse(trimmed) as Record<string, unknown>;
        return formatSpecialistOutcome(parsed);
      } catch {
        // Fall back to plain text
      }
    }
    return { leadSummary: null, text: trimmed, attributes: null, listItems: null, isEmpty: !trimmed };
  }

  if (Array.isArray(outcome)) {
    if (outcome.length === 0) {
      return { leadSummary: null, text: null, attributes: null, listItems: null, isEmpty: true };
    }
    const listItems = outcome.map((item) =>
      typeof item === 'object' && item !== null ? JSON.stringify(item) : String(item)
    );
    return { leadSummary: null, text: null, attributes: null, listItems, isEmpty: false };
  }

  if (typeof outcome === 'object') {
    const record = outcome as Record<string, unknown>;
    const keys = Object.keys(record);

    if (keys.length === 0) {
      return { leadSummary: null, text: null, attributes: null, listItems: null, isEmpty: true };
    }

    const summaryField = record.summary || record.findings || record.explanation;
    const leadSummary = summaryField && typeof summaryField === 'string' ? summaryField : null;

    const remainingKeys = keys.filter(
      (k) => k !== 'summary' && k !== 'findings' && k !== 'explanation'
    );

    const attributes = remainingKeys.map((key) => {
      const val = record[key];
      const displayVal =
        val === null || val === undefined
          ? 'none'
          : typeof val === 'object'
          ? JSON.stringify(val)
          : String(val);

      return {
        key: key.replace(/_/g, ' '),
        value: displayVal
      };
    });

    return {
      leadSummary,
      text: null,
      attributes: attributes.length > 0 ? attributes : null,
      listItems: null,
      isEmpty: false
    };
  }

  return { leadSummary: null, text: String(outcome), attributes: null, listItems: null, isEmpty: false };
}

/**
 * Returns available specialist branch entries from response, preserving order without inventing absent agents.
 */
export function extractSpecialistEntries(
  branchOutcomes: Record<string, unknown> | null | undefined
): { name: string; label: string; outcome: unknown }[] {
  if (!branchOutcomes || typeof branchOutcomes !== 'object') {
    return [];
  }
  return Object.entries(branchOutcomes).map(([name, outcome]) => ({
    name,
    label: formatSpecialistName(name),
    outcome
  }));
}
