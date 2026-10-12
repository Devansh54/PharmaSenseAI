import React, { useState } from 'react';
import type { AnalysisResponse, EvidenceResponse, RequestLifecycleState } from '../../types/api';
import {
  ShieldCheckIcon,
  AlertTriangleIcon,
  CheckCircleIcon,
  XCircleIcon,
  LibraryIcon,
  CopyIcon,
  CheckIcon,
  ChevronDownIcon,
  FileTextIcon
} from '../common/Icons';
import { getEvidence, AnalysisApiError } from '../../services/api';
import {
  parseFindingsParagraphs,
  extractInvalidChunkIds,
  getStatusDisplay,
  formatTelemetryData,
  formatSpecialistOutcome,
  extractSpecialistEntries
} from '../../services/responseFormatter';
import './ResponseCard.css';

interface ResponseCardProps {
  lifecycleState: RequestLifecycleState;
  question: string;
  response: AnalysisResponse | null;
  errorMessage: string | null;
  onDismiss: () => void;
  onRetry?: () => void;
  onFetchEvidence?: (evidenceId: string) => Promise<EvidenceResponse>;
  onNavigateToReview?: (taskId: string) => void;
}

/**
 * Safely renders a structured specialist outcome without dumping raw JSON.
 */
const SpecialistOutcomeContent: React.FC<{ outcome: unknown }> = ({ outcome }) => {
  const formatted = formatSpecialistOutcome(outcome);

  if (formatted.isEmpty) {
    return <p className="response-branch-empty">No trace output recorded for this specialist.</p>;
  }

  return (
    <div className="response-branch-structured">
      {formatted.leadSummary && (
        <p className="response-branch-summary-lead">{formatted.leadSummary}</p>
      )}
      {formatted.text && (
        <p className="response-branch-text">{formatted.text}</p>
      )}
      {formatted.listItems && (
        <ul className="response-branch-list">
          {formatted.listItems.map((item, idx) => (
            <li key={idx}>{item}</li>
          ))}
        </ul>
      )}
      {formatted.attributes && (
        <div className="response-branch-attrs">
          {formatted.attributes.map((attr, idx) => (
            <div key={idx} className="response-branch-attr-row">
              <span className="response-branch-attr-key">{attr.key}:</span>
              <span className="response-branch-attr-val" title={attr.value}>
                {attr.value}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export const ResponseCard: React.FC<ResponseCardProps> = ({
  lifecycleState,
  question,
  response,
  errorMessage,
  onDismiss,
  onRetry,
  onFetchEvidence,
  onNavigateToReview
}) => {
  const [copied, setCopied] = useState(false);
  const [expandedSpecialists, setExpandedSpecialists] = useState<Record<string, boolean>>({});

  // Evidence Drill-down State & Session Cache (Phase 5)
  const [evidenceCache, setEvidenceCache] = useState<Record<string, EvidenceResponse>>({});
  const [selectedEvidenceId, setSelectedEvidenceId] = useState<string | null>(null);
  const [isLoadingEvidence, setIsLoadingEvidence] = useState(false);
  const [evidenceError, setEvidenceError] = useState<string | null>(null);

  if (lifecycleState === 'idle') {
    return null;
  }

  // 1. Loading State View
  if (lifecycleState === 'loading') {
    return (
      <div className="response-card-container">
        <div className="response-loading-card" role="status" aria-live="polite">
          <div className="response-loading-spinner" />
          <h2 className="response-loading-title">Analyzing Research Evidence</h2>
          <p className="response-loading-subtitle">
            Orchestrating clinical trial records, biomedical literature, and safety logs across specialist agents.
          </p>
          <div className="response-loading-question-pill" title={question}>
            &ldquo;{question}&rdquo;
          </div>
        </div>
      </div>
    );
  }

  // 2. Failed / Error State View
  if (lifecycleState === 'failed') {
    return (
      <div className="response-card-container">
        <div className="response-card failed" role="alert">
          <div className="response-header">
            <div className="response-header-left">
              <span className="response-status-badge failed">
                <XCircleIcon size={14} />
                <span>Analysis Failed</span>
              </span>
              <p className="response-query-text">&ldquo;{question}&rdquo;</p>
            </div>
            <button
              type="button"
              className="response-dismiss-btn"
              onClick={onDismiss}
              aria-label="Close error"
            >
              Dismiss ✕
            </button>
          </div>

          <div className="response-findings-section">
            <h3 className="response-section-title">Error Details</h3>
            <div className="response-findings-body error-text">
              {errorMessage || response?.error_message || 'The analysis request could not be completed.'}
            </div>
          </div>

          {onRetry && (
            <div>
              <button type="button" className="response-retry-btn" onClick={onRetry}>
                Retry Analysis ↻
              </button>
            </div>
          )}

          <p className="response-legal-disclaimer">
            Synthetic research data; for R&amp;D/clinical operations analysis only. Not for patient diagnosis, treatment advice, or emergency response.
          </p>
        </div>
      </div>
    );
  }

  // 3. Completed State Views (success, partial_success, no_evidence, guardrail_refusal)
  const statusInfo = getStatusDisplay(lifecycleState);
  const StatusIcon = statusInfo.isRefusal
    ? ShieldCheckIcon
    : statusInfo.isNoEvidence
    ? LibraryIcon
    : statusInfo.isPartial
    ? AlertTriangleIcon
    : CheckCircleIcon;

  // Extract paragraphs from findings safely
  const rawFindings = (response?.findings || '').trim();
  const findingsParagraphs = parseFindingsParagraphs(response?.findings);

  // Handle Copy Findings action
  const handleCopy = async () => {
    if (!rawFindings) return;
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(rawFindings);
      } else {
        const textarea = document.createElement('textarea');
        textarea.value = rawFindings;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
      }
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Graceful copy fallback
    }
  };

  // Toggle specialist card expansion
  const toggleSpecialist = (name: string) => {
    setExpandedSpecialists((prev) => ({
      ...prev,
      [name]: prev[name] === undefined ? false : !prev[name]
    }));
  };

  // Evidence Drill-down Fetch & Toggle
  const fetchEvidenceItem = async (chunkId: string) => {
    if (!chunkId) return;
    setIsLoadingEvidence(true);
    setEvidenceError(null);

    try {
      const fetchFn = onFetchEvidence || getEvidence;
      const res = await fetchFn(chunkId);
      setEvidenceCache((prev) => ({ ...prev, [chunkId]: res }));
    } catch (err) {
      const msg =
        err instanceof AnalysisApiError || err instanceof Error
          ? err.message
          : 'Failed to retrieve evidence.';
      setEvidenceError(msg);
    } finally {
      setIsLoadingEvidence(false);
    }
  };

  const handleSelectEvidence = (chunkId: string) => {
    if (selectedEvidenceId === chunkId && !evidenceError) {
      // Toggle off if already viewing without error
      setSelectedEvidenceId(null);
      return;
    }

    setSelectedEvidenceId(chunkId);
    setEvidenceError(null);

    // Check session cache
    if (evidenceCache[chunkId]) {
      setIsLoadingEvidence(false);
      return;
    }

    // Cache miss: retrieve from API
    void fetchEvidenceItem(chunkId);
  };

  const handleCloseEvidence = () => {
    setSelectedEvidenceId(null);
    setEvidenceError(null);
    setIsLoadingEvidence(false);
  };

  // Extract invalid chunk citations across all citations
  const allInvalidChunkIds = extractInvalidChunkIds(response?.citations);
  const specialistEntries = extractSpecialistEntries(response?.branch_outcomes);
  const hasBranchOutcomes = specialistEntries.length > 0;
  const telemetry = formatTelemetryData(response);

  // Currently active evidence from cache
  const activeEvidence = selectedEvidenceId ? evidenceCache[selectedEvidenceId] : null;

  return (
    <div className="response-card-container">
      <div className={`response-card ${statusInfo.badgeClass}`} role="region" aria-label="Analysis findings">
        {/* Header with Status Badge and Query */}
        <div className="response-header">
          <div className="response-header-left">
            <span className={`response-status-badge ${statusInfo.badgeClass}`}>
              <StatusIcon size={14} />
              <span>{statusInfo.label}</span>
            </span>
            {response?.limitations?.some(l => l.includes('DEMO MODE') || l.includes('SYNTHETIC DATA')) && (
              <span className="response-status-badge response-demo-badge" style={{
                backgroundColor: 'rgba(14, 165, 233, 0.15)',
                color: '#38bdf8',
                borderColor: 'rgba(14, 165, 233, 0.4)',
                fontWeight: 700,
                fontSize: '11px',
                letterSpacing: '0.04em'
              }}>
                DEMO MODE — SYNTHETIC DATA
              </span>
            )}
            <div className="response-query-wrapper">
              <span className="response-query-label">Research Inquiry</span>
              <p className="response-query-text">&ldquo;{question}&rdquo;</p>
            </div>
          </div>
          <div className="response-header-actions">
            {rawFindings && !statusInfo.isRefusal && (
              <button
                type="button"
                className={`response-copy-btn ${copied ? 'copied' : ''}`}
                onClick={handleCopy}
                title="Copy findings text to clipboard"
                aria-label={copied ? 'Findings copied' : 'Copy findings'}
              >
                {copied ? <CheckIcon size={14} /> : <CopyIcon size={14} />}
                <span>{copied ? 'Copied' : 'Copy Findings'}</span>
              </button>
            )}
            <button
              type="button"
              className="response-dismiss-btn"
              onClick={onDismiss}
              aria-label="Start new analysis"
            >
              New Analysis ✕
            </button>
          </div>
        </div>

        {/* Guardrail Safety Notice Banner */}
        {statusInfo.isRefusal && (
          <div className="response-refusal-notice" role="alert">
            <div className="response-refusal-title">
              <ShieldCheckIcon size={16} />
              <span>Clinical Safety Policy Refusal</span>
            </div>
            <p className="response-refusal-body">
              This request was blocked by the PharmaSenseAI clinical safety guardrails. PharmaSenseAI provides research analysis over synthetic R&amp;D trial evidence and does not provide personalized patient diagnosis, prescription guidance, or clinical treatment recommendations.
            </p>
            {response?.error_message && (
              <div className="response-refusal-code">
                <strong>Enforcement Detail:</strong> {response.error_message}
              </div>
            )}
          </div>
        )}

        {/* Unverified Citation Identifiers Warning */}
        {allInvalidChunkIds.length > 0 && (
          <div className="response-warning-box" role="alert">
            <div className="response-warning-header">
              <AlertTriangleIcon size={15} />
              <span>Unverified Citation Identifiers Detected</span>
            </div>
            <p className="response-warning-desc">
              The following citation chunk IDs were cited by synthesis agents but could not be verified against the active evidence repository:
            </p>
            <div className="response-warning-chips">
              {allInvalidChunkIds.map((chunkId) => (
                <span key={chunkId} className="response-warning-chip" title="Unverified chunk ID (cannot inspect)">
                  {chunkId} ⚠
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Findings Narrative */}
        <div className="response-findings-section">
          <div className="response-section-header">
            <h3 className="response-section-title">
              {statusInfo.isRefusal ? 'Refusal Explanation' : 'Synthesized Findings'}
            </h3>
          </div>
          <div className="response-findings-body">
            {findingsParagraphs.length > 0 ? (
              findingsParagraphs.map((para, idx) => (
                <p key={idx} className="response-finding-paragraph">
                  {para}
                </p>
              ))
            ) : (
              <p className="response-findings-empty">
                {statusInfo.isNoEvidence
                  ? 'No evidence was identified in the synthetic clinical trials or research literature matching the specified criteria.'
                  : 'No detailed findings narrative was emitted for this inquiry.'}
              </p>
            )}
          </div>
        </div>

        {/* Specialist Agent Evidence Breakdown */}
        <div className="response-branches-container">
          <div className="response-section-header">
            <h3 className="response-section-title">Specialist Agent Trace Breakdown</h3>
            {hasBranchOutcomes && (
              <span className="response-section-subtitle">
                {specialistEntries.length} specialist {specialistEntries.length === 1 ? 'branch' : 'branches'} reported
              </span>
            )}
          </div>

          {hasBranchOutcomes ? (
            <div className="response-branches-grid">
              {specialistEntries.map(({ name, label, outcome }) => {
                const isExpanded = expandedSpecialists[name] ?? true;

                return (
                  <div
                    key={name}
                    className={`response-branch-card ${isExpanded ? 'expanded' : 'collapsed'}`}
                  >
                    <button
                      type="button"
                      className="response-branch-header-btn"
                      onClick={() => toggleSpecialist(name)}
                      aria-expanded={isExpanded}
                      aria-label={`Toggle ${label} details`}
                    >
                      <div className="response-branch-title-group">
                        <span className="response-branch-dot" />
                        <span className="response-branch-name">{label}</span>
                      </div>
                      <span className={`response-branch-chevron ${isExpanded ? 'open' : ''}`}>
                        <ChevronDownIcon size={14} />
                      </span>
                    </button>

                    {isExpanded && (
                      <div className="response-branch-body">
                        <SpecialistOutcomeContent outcome={outcome} />
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="response-branches-empty">
              No specialist branch traces returned for this inquiry.
            </div>
          )}
        </div>

        {/* Limitations & Citations */}
        {((response?.limitations && response.limitations.length > 0) ||
          (response?.citations && response.citations.length > 0)) && (
          <div className="response-metadata-grid">
            {response?.limitations && response.limitations.length > 0 && (
              <div className="response-limitations-section">
                <h3 className="response-section-title">Limitations &amp; Constraints Noted</h3>
                <ul className="response-limitations-list">
                  {response.limitations.map((lim, idx) => (
                    <li key={idx}>
                      <span className="response-limitation-bullet" />
                      <span>{lim}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {response?.citations && response.citations.length > 0 && (
              <div className="response-citations-section">
                <h3 className="response-section-title">Grounding Citations &amp; Evidence Drill-Down</h3>
                <div className="response-citations-list">
                  {response.citations.map((c, idx) => (
                    <div key={idx} className="response-citation-item">
                      <span className="response-citation-claim">{c.claim}</span>
                      {c.citations && c.citations.length > 0 ? (
                        <div className="response-citation-chunks" role="group" aria-label="Evidence chunk citations">
                          {c.citations.map((chunkId, cIdx) => {
                            const isInvalid = Boolean(c.invalid_chunk_ids && c.invalid_chunk_ids.includes(chunkId));
                            const isSelected = selectedEvidenceId === chunkId;
                            const isLoadingThis = isLoadingEvidence && isSelected;

                            if (isInvalid) {
                              return (
                                <span
                                  key={cIdx}
                                  className="response-chunk-tag invalid"
                                  title="Unverified chunk ID: cannot be retrieved"
                                  aria-disabled="true"
                                >
                                  {chunkId} ⚠
                                </span>
                              );
                            }

                            return (
                              <button
                                key={cIdx}
                                type="button"
                                className={`response-chunk-tag interactive ${isSelected ? 'active' : ''} ${isLoadingThis ? 'loading' : ''}`}
                                onClick={() => handleSelectEvidence(chunkId)}
                                disabled={isLoadingThis}
                                title={`Inspect source excerpt for ${chunkId}`}
                                aria-pressed={isSelected}
                              >
                                <span>{chunkId}</span>
                                {isSelected && <span className="response-chunk-active-dot" />}
                              </button>
                            );
                          })}
                        </div>
                      ) : (
                        <span className="response-citation-no-chunks">No chunk IDs linked to this claim</span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Phase 5: Dedicated Evidence Excerpt Inspection Panel */}
        {selectedEvidenceId && (
          <div className="response-evidence-panel" role="region" aria-label="Evidence Excerpt Detail">
            <div className="response-evidence-header">
              <div className="response-evidence-header-title">
                <FileTextIcon size={16} />
                <span>Source Evidence Inspection</span>
                <span className="response-evidence-id-badge" title={selectedEvidenceId}>
                  {selectedEvidenceId}
                </span>
                {activeEvidence?.metadata?.doc_type && (
                  <span className="response-evidence-type-badge">
                    {String(activeEvidence.metadata.doc_type)}
                  </span>
                )}
              </div>
              <button
                type="button"
                className="response-evidence-close-btn"
                onClick={handleCloseEvidence}
                aria-label="Close evidence inspection panel"
                title="Close evidence panel"
              >
                ✕
              </button>
            </div>

            {isLoadingEvidence && (
              <div className="response-evidence-loading" role="status" aria-live="polite">
                <div className="response-evidence-spinner" />
                <span>Retrieving evidence chunk &ldquo;{selectedEvidenceId}&rdquo; from document catalog...</span>
              </div>
            )}

            {evidenceError && !isLoadingEvidence && (
              <div className="response-evidence-error" role="alert">
                <div className="response-evidence-error-content">
                  <AlertTriangleIcon size={16} />
                  <span>{evidenceError}</span>
                </div>
                <button
                  type="button"
                  className="response-evidence-retry-btn"
                  onClick={() => fetchEvidenceItem(selectedEvidenceId)}
                >
                  Retry Retrieval ↻
                </button>
              </div>
            )}

            {activeEvidence && !isLoadingEvidence && !evidenceError && (
              <div className="response-evidence-content">
                {activeEvidence.metadata?.title && (
                  <div className="response-evidence-meta-row">
                    <span className="response-evidence-meta-label">Document Title:</span>
                    <span className="response-evidence-meta-val">{String(activeEvidence.metadata.title)}</span>
                  </div>
                )}

                <div className="response-evidence-meta-pills">
                  {activeEvidence.metadata?.trial_id && (
                    <span className="response-evidence-meta-pill">
                      Trial: {String(activeEvidence.metadata.trial_id)}
                    </span>
                  )}
                  {activeEvidence.metadata?.compound_id && (
                    <span className="response-evidence-meta-pill">
                      Compound: {String(activeEvidence.metadata.compound_id)}
                    </span>
                  )}
                  {activeEvidence.metadata?.doc_id && (
                    <span className="response-evidence-meta-pill">
                      Doc ID: {String(activeEvidence.metadata.doc_id)}
                    </span>
                  )}
                </div>

                <div className="response-evidence-excerpt-box">
                  <span className="response-evidence-excerpt-label">Verified Document Chunk Text</span>
                  <p className="response-evidence-excerpt-text">{activeEvidence.content}</p>
                </div>

                <span className="response-evidence-disclaimer-note">
                  Synthetic evidence excerpt retrieved from repository for R&amp;D analysis verification.
                </span>
              </div>
            )}
          </div>
        )}

        {/* Telemetry Footer */}
        {telemetry.hasTelemetry && (
          <div className="response-footer-telemetry">
            <div className="response-metrics-group">
              {telemetry.latencyStr && (
                <span className="response-telemetry-item" title="End-to-end multi-agent orchestration duration">
                  <span className="response-telemetry-label">Latency:</span> {telemetry.latencyStr}
                </span>
              )}
              {telemetry.tokensStr && (
                <span className="response-telemetry-item" title="Total tokens consumed across specialists">
                  <span className="response-telemetry-label">Tokens:</span> {telemetry.tokensStr}
                </span>
              )}
            </div>

            {telemetry.escalationRef && (
              onNavigateToReview ? (
                <button
                  type="button"
                  className="response-escalation-pill"
                  style={{ cursor: 'pointer', borderStyle: 'solid' }}
                  title="View this task in Human Review Queue"
                  onClick={() => onNavigateToReview(telemetry.escalationRef!)}
                >
                  <ShieldCheckIcon size={13} />
                  <span>Review Task: {telemetry.escalationRef} ↗</span>
                </button>
              ) : (
                <span className="response-escalation-pill" title="Adverse Event Human Review Task ID">
                  <ShieldCheckIcon size={13} />
                  <span>Review Task: {telemetry.escalationRef}</span>
                </span>
              )
            )}
          </div>
        )}

        {/* Clinical Safety Disclaimer */}
        <p className="response-legal-disclaimer">
          Synthetic research data; for R&amp;D/clinical operations analysis only. Not for patient diagnosis, treatment advice, or emergency response.
        </p>
      </div>
    </div>
  );
};
