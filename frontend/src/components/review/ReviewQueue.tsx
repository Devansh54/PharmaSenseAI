import React, { useState, useEffect, useMemo, useCallback } from 'react';
import type { ReviewTask, ReviewDecisionPayload, ReviewDecisionResponse } from '../../types/api';
import {
  listReviews as apiListReviews,
  createReviewDecision as apiCreateReviewDecision,
  AnalysisApiError
} from '../../services/api';
import {
  ShieldCheckIcon,
  AlertTriangleIcon,
  CheckCircleIcon,
  SearchIcon,
  ActivityIcon
} from '../common/Icons';
import './ReviewQueue.css';

export interface ReviewQueueProps {
  initialTaskId?: string | null;
  onSelectReviewTask?: (task: ReviewTask) => void;
  fetchListReviews?: () => Promise<ReviewTask[]>;
  fetchSubmitDecision?: (id: string, payload: ReviewDecisionPayload) => Promise<ReviewDecisionResponse>;
}

export const ReviewQueue: React.FC<ReviewQueueProps> = ({
  initialTaskId,
  onSelectReviewTask,
  fetchListReviews,
  fetchSubmitDecision
}) => {
  const [tasks, setTasks] = useState<ReviewTask[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(initialTaskId || null);
  const [statusFilter, setStatusFilter] = useState<'ALL' | 'PENDING' | 'ACKNOWLEDGED' | 'RESOLVED'>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');

  // Decision Form State
  const [reviewerId, setReviewerId] = useState<string>('');
  const [comments, setComments] = useState<string>('');
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [decisionFeedback, setDecisionFeedback] = useState<{
    type: 'success' | 'error';
    message: string;
  } | null>(null);
  const [pendingConfirmAction, setPendingConfirmAction] = useState<'resolved' | null>(null);

  // Manual refresh callback
  const handleRefresh = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const fetchFn = fetchListReviews || apiListReviews;
      const data = await fetchFn();
      setTasks(data);
      if (data.length > 0 && !selectedTaskId) {
        setSelectedTaskId(data[0].task_id);
      }
    } catch (err) {
      const msg =
        err instanceof AnalysisApiError || err instanceof Error
          ? err.message
          : 'Failed to load review queue.';
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  }, [fetchListReviews, selectedTaskId]);

  // Initial mount load
  useEffect(() => {
    let isMounted = true;
    const fetchFn = fetchListReviews || apiListReviews;
    fetchFn()
      .then((data) => {
        if (!isMounted) return;
        setTasks(data);
        if (data.length > 0) {
          setSelectedTaskId((prev) => prev || data[0].task_id);
        }
        setIsLoading(false);
      })
      .catch((err) => {
        if (!isMounted) return;
        const msg =
          err instanceof AnalysisApiError || err instanceof Error
            ? err.message
            : 'Failed to load review queue.';
        setError(msg);
        setIsLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [fetchListReviews]);

  // Adjust selectedTaskId when initialTaskId prop changes (official React pattern)
  const [prevInitialId, setPrevInitialId] = useState(initialTaskId);
  if (initialTaskId !== prevInitialId) {
    setPrevInitialId(initialTaskId);
    if (initialTaskId) {
      setSelectedTaskId(initialTaskId);
    }
  }

  // Currently selected task
  const selectedTask = useMemo(() => {
    return tasks.find((t) => t.task_id === selectedTaskId) || null;
  }, [tasks, selectedTaskId]);

  // Filtered task list
  const filteredTasks = useMemo(() => {
    const qLower = searchQuery.trim().toLowerCase();
    return tasks.filter((t) => {
      // Status filter
      if (statusFilter !== 'ALL') {
        if (t.status.toUpperCase() !== statusFilter) {
          return false;
        }
      }
      // Text query
      if (qLower) {
        const matchText = (
          t.task_id +
          ' ' +
          t.event_id +
          ' ' +
          t.status +
          ' ' +
          t.reason
        ).toLowerCase();
        if (!matchText.includes(qLower)) {
          return false;
        }
      }
      return true;
    });
  }, [tasks, statusFilter, searchQuery]);

  // Status metrics counts
  const metrics = useMemo(() => {
    let pending = 0;
    let acknowledged = 0;
    let resolved = 0;
    for (const t of tasks) {
      const s = t.status.toUpperCase();
      if (s === 'PENDING') pending++;
      else if (s === 'ACKNOWLEDGED') acknowledged++;
      else if (s === 'RESOLVED') resolved++;
    }
    return { total: tasks.length, pending, acknowledged, resolved };
  }, [tasks]);

  const handleSelectTask = (task: ReviewTask) => {
    setSelectedTaskId(task.task_id);
    setDecisionFeedback(null);
    setPendingConfirmAction(null);
    if (onSelectReviewTask) {
      onSelectReviewTask(task);
    }
  };

  // Decision Submission Handler
  const handleExecuteDecision = async (decision: 'acknowledged' | 'resolved') => {
    if (!selectedTask) return;

    const trimmedReviewer = reviewerId.trim();
    if (!trimmedReviewer) {
      setDecisionFeedback({
        type: 'error',
        message: 'Reviewer Identifier is required before recording a review decision.'
      });
      return;
    }

    setIsSubmitting(true);
    setDecisionFeedback(null);
    setPendingConfirmAction(null);

    const payload: ReviewDecisionPayload = {
      reviewer_id: trimmedReviewer,
      decision,
      ...(comments.trim() ? { comments: comments.trim() } : {})
    };

    try {
      const submitFn = fetchSubmitDecision || apiCreateReviewDecision;
      await submitFn(selectedTask.task_id, payload);

      const targetStatus = decision.toUpperCase();
      // Update local task state truthfully based on success
      setTasks((prev) =>
        prev.map((t) =>
          t.task_id === selectedTask.task_id ? { ...t, status: targetStatus } : t
        )
      );
      setDecisionFeedback({
        type: 'success',
        message: `Decision successfully recorded: Task ${selectedTask.task_id} transitioned to ${targetStatus}.`
      });
      setComments('');
    } catch (err) {
      const msg =
        err instanceof AnalysisApiError || err instanceof Error
          ? err.message
          : 'Failed to record review decision.';
      setDecisionFeedback({
        type: 'error',
        message: `Decision rejected: ${msg}. Current task status retained.`
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const getStatusBadgeClass = (status: string) => {
    const s = status.toUpperCase();
    if (s === 'PENDING') return 'review-badge-pending';
    if (s === 'ACKNOWLEDGED') return 'review-badge-acknowledged';
    if (s === 'RESOLVED') return 'review-badge-resolved';
    return 'review-badge-default';
  };

  const currentStatusNormalized = selectedTask?.status.toUpperCase() || '';

  return (
    <div className="review-container">
      {/* Disclaimer Banner */}
      <div className="review-disclaimer-banner" role="note">
        <ShieldCheckIcon size={16} className="review-disclaimer-icon" />
        <span className="review-disclaimer-text">
          Synthetic research data; for R&amp;D/clinical operations analysis only. Not for patient diagnosis, treatment advice, or emergency response.
        </span>
      </div>

      {/* Header & Stats Bar */}
      <div className="review-header">
        <div className="review-header-left">
          <div className="review-title-row">
            <h1 className="review-title">Human-in-the-Loop Review Queue</h1>
            <span className="review-badge-safety">Safety Oversight</span>
          </div>
          <p className="review-subtitle">
            Triage safety escalations created by deterministic adverse-event rules. Review seriousness criteria and log clinical oversight decisions.
          </p>
        </div>

        <div className="review-header-actions">
          <button
            type="button"
            className="review-refresh-btn"
            onClick={handleRefresh}
            disabled={isLoading || isSubmitting}
            title="Refresh review task queue"
          >
            <ActivityIcon size={14} />
            <span>{isLoading ? 'Refreshing...' : 'Refresh Queue ↻'}</span>
          </button>
        </div>
      </div>

      {/* Metrics Row */}
      <div className="review-metrics-row">
        <div className="review-metric-chip">
          <span className="metric-label">Total Escalations</span>
          <span className="metric-val">{metrics.total}</span>
        </div>
        <div className="review-metric-chip chip-pending">
          <span className="metric-label">Pending Triage</span>
          <span className="metric-val">{metrics.pending}</span>
        </div>
        <div className="review-metric-chip chip-acknowledged">
          <span className="metric-label">Acknowledged</span>
          <span className="metric-val">{metrics.acknowledged}</span>
        </div>
        <div className="review-metric-chip chip-resolved">
          <span className="metric-label">Resolved</span>
          <span className="metric-val">{metrics.resolved}</span>
        </div>
      </div>

      {/* Main Review Grid: Queue on Left, Details on Right */}
      <div className="review-layout-grid">
        {/* Left Column: Queue List & Filters */}
        <section className="review-queue-panel" aria-label="Review task list">
          <div className="review-search-bar">
            <SearchIcon size={16} className="search-bar-icon" />
            <input
              type="text"
              className="review-search-input"
              placeholder="Search by task ID, event ID, or reason..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              aria-label="Search review tasks"
            />
            {searchQuery && (
              <button
                type="button"
                className="review-search-clear"
                onClick={() => setSearchQuery('')}
                aria-label="Clear search"
              >
                ✕
              </button>
            )}
          </div>

          <div className="review-status-filters" role="tablist" aria-label="Filter by status">
            {(['ALL', 'PENDING', 'ACKNOWLEDGED', 'RESOLVED'] as const).map((filter) => (
              <button
                key={filter}
                type="button"
                role="tab"
                aria-selected={statusFilter === filter}
                className={`review-filter-btn ${statusFilter === filter ? 'active' : ''}`}
                onClick={() => setStatusFilter(filter)}
              >
                {filter === 'ALL' ? 'All Tasks' : filter.charAt(0) + filter.slice(1).toLowerCase()}
              </button>
            ))}
          </div>

          {/* List Content States */}
          {isLoading && tasks.length === 0 && (
            <div className="review-state-loading" role="status">
              <div className="review-spinner" />
              <span>Loading review tasks from safety queue...</span>
            </div>
          )}

          {error && (
            <div className="review-state-error" role="alert">
              <AlertTriangleIcon size={18} />
              <div className="error-text-wrap">
                <span className="error-title">Unable to retrieve review queue</span>
                <span className="error-desc">{error}</span>
              </div>
              <button
                type="button"
                className="review-retry-btn"
                onClick={handleRefresh}
              >
                Retry ↻
              </button>
            </div>
          )}

          {!isLoading && !error && filteredTasks.length === 0 && (
            <div className="review-state-empty">
              <CheckCircleIcon size={24} className="empty-icon" />
              <span className="empty-title">No review tasks found</span>
              <p className="empty-desc">
                {searchQuery || statusFilter !== 'ALL'
                  ? 'No tasks match your current filter or search criteria.'
                  : 'All adverse event escalations have been processed or queue is empty.'}
              </p>
            </div>
          )}

          {/* Task Card List */}
          <div className="review-card-list">
            {filteredTasks.map((task) => {
              const isSelected = task.task_id === selectedTaskId;
              return (
                <div
                  key={task.task_id}
                  className={`review-card ${isSelected ? 'selected' : ''}`}
                  onClick={() => handleSelectTask(task)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      handleSelectTask(task);
                    }
                  }}
                  aria-pressed={isSelected}
                >
                  <div className="review-card-top">
                    <span className="review-card-task-id">{task.task_id}</span>
                    <span className={`review-status-badge ${getStatusBadgeClass(task.status)}`}>
                      {task.status}
                    </span>
                  </div>

                  <div className="review-card-event-row">
                    <span className="review-card-label">Event ID:</span>
                    <span className="review-card-val">{task.event_id || 'N/A'}</span>
                  </div>

                  <p className="review-card-reason-excerpt" title={task.reason}>
                    {task.reason}
                  </p>

                  <div className="review-card-bottom">
                    <span className="review-card-date">
                      {new Date(task.created_at).toLocaleString()}
                    </span>
                    <span className="review-card-select-hint">
                      {isSelected ? 'Active Details ▸' : 'Select'}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        {/* Right Column: Selected Task Details & Decision Actions */}
        <section className="review-details-panel" aria-label="Selected task details">
          {!selectedTask ? (
            <div className="review-details-placeholder">
              <ShieldCheckIcon size={32} className="placeholder-icon" />
              <h2 className="placeholder-title">Select a Task to Inspect</h2>
              <p className="placeholder-desc">
                Select any adverse-event escalation from the queue on the left to review seriousness details, check causality, and record an audit decision.
              </p>
            </div>
          ) : (
            <div className="review-details-content">
              {/* Task Header */}
              <div className="details-header">
                <div>
                  <span className="details-kicker">Safety Escalation Review</span>
                  <h2 className="details-task-id">{selectedTask.task_id}</h2>
                </div>
                <span className={`review-status-badge badge-large ${getStatusBadgeClass(selectedTask.status)}`}>
                  {selectedTask.status}
                </span>
              </div>

              {/* Task Metadata Box */}
              <div className="details-meta-grid">
                <div className="meta-item">
                  <span className="meta-label">Event Identifier</span>
                  <span className="meta-val">{selectedTask.event_id || 'Not specified'}</span>
                </div>
                <div className="meta-item">
                  <span className="meta-label">Created At</span>
                  <span className="meta-val">
                    {new Date(selectedTask.created_at).toLocaleString()}
                  </span>
                </div>
                <div className="meta-item">
                  <span className="meta-label">Escalation Source</span>
                  <span className="meta-val">Adverse Event Triage</span>
                </div>
                <div className="meta-item">
                  <span className="meta-label">Oversight Mandate</span>
                  <span className="meta-val">Deterministic Rule</span>
                </div>
              </div>

              {/* Seriousness & Triage Reason */}
              <div className="details-reason-section">
                <h3 className="section-title">Clinical Escalation Reason</h3>
                <div className="reason-content-box">
                  <p className="reason-text">{selectedTask.reason}</p>
                </div>
                <p className="reason-disclaimer-note">
                  * Seriousness criteria (death, life-threatening, inpatient hospitalization) require mandatory human review under safety protocols regardless of causality assessment. No external emails or SMS alerts were dispatched.
                </p>
              </div>

              {/* Decision Feedback Banner */}
              {decisionFeedback && (
                <div
                  className={`review-feedback-banner ${decisionFeedback.type}`}
                  role={decisionFeedback.type === 'error' ? 'alert' : 'status'}
                >
                  {decisionFeedback.type === 'success' ? (
                    <CheckCircleIcon size={18} />
                  ) : (
                    <AlertTriangleIcon size={18} />
                  )}
                  <span>{decisionFeedback.message}</span>
                </div>
              )}

              {/* Decision Submission Form */}
              <div className="details-decision-section">
                <h3 className="section-title">Record Review Decision</h3>

                {currentStatusNormalized === 'RESOLVED' ? (
                  <div className="details-resolved-box">
                    <CheckCircleIcon size={20} className="resolved-check" />
                    <div>
                      <h4 className="resolved-title">Safety Escalation Resolved</h4>
                      <p className="resolved-desc">
                        This review task has been finalized as RESOLVED. The safety contract permits no further state transitions.
                      </p>
                    </div>
                  </div>
                ) : (
                  <div className="decision-form">
                    {/* Reviewer ID Input */}
                    <div className="form-field">
                      <label htmlFor="reviewer-id-input" className="form-label">
                        Reviewer Identifier <span className="required-mark">*</span>
                      </label>
                      <input
                        id="reviewer-id-input"
                        type="text"
                        className="form-input"
                        placeholder="e.g. rev-clin-01 or Dr. Gomez"
                        value={reviewerId}
                        onChange={(e) => setReviewerId(e.target.value)}
                        disabled={isSubmitting}
                        required
                      />
                      <span className="form-hint">
                        Required for audit traceability. The identity is not authenticated or fabricated.
                      </span>
                    </div>

                    {/* Optional Comments Textarea */}
                    <div className="form-field">
                      <label htmlFor="reviewer-comments-input" className="form-label">
                        Reviewer Notes &amp; Clinical Justification <span className="optional-tag">(Optional)</span>
                      </label>
                      <textarea
                        id="reviewer-comments-input"
                        className="form-textarea"
                        placeholder="Enter clinical rationale, investigation notes, or follow-up instructions..."
                        rows={3}
                        value={comments}
                        onChange={(e) => setComments(e.target.value)}
                        disabled={isSubmitting}
                      />
                    </div>

                    {/* Confirmation Dialog for Resolution */}
                    {pendingConfirmAction === 'resolved' && (
                      <div className="confirmation-callout" role="alert">
                        <AlertTriangleIcon size={20} className="confirm-icon" />
                        <div className="confirm-text-wrap">
                          <h4 className="confirm-heading">Confirm Escalation Resolution</h4>
                          <p className="confirm-desc">
                            Are you sure you want to mark task <strong>{selectedTask.task_id}</strong> as <strong>RESOLVED</strong>? This completes human oversight for this adverse event.
                          </p>
                          <div className="confirm-btn-row">
                            <button
                              type="button"
                              className="confirm-btn-yes"
                              onClick={() => handleExecuteDecision('resolved')}
                              disabled={isSubmitting}
                            >
                              {isSubmitting ? 'Submitting...' : 'Yes, Confirm Resolution'}
                            </button>
                            <button
                              type="button"
                              className="confirm-btn-cancel"
                              onClick={() => setPendingConfirmAction(null)}
                              disabled={isSubmitting}
                            >
                              Cancel
                            </button>
                          </div>
                        </div>
                      </div>
                    )}

                    {/* Transition Action Buttons */}
                    {pendingConfirmAction !== 'resolved' && (
                      <div className="decision-actions-row">
                        {/* Acknowledge Button: Valid only when PENDING */}
                        {currentStatusNormalized === 'PENDING' && (
                          <button
                            type="button"
                            className="btn-decision btn-acknowledge"
                            onClick={() => handleExecuteDecision('acknowledged')}
                            disabled={isSubmitting || !reviewerId.trim()}
                            title={
                              !reviewerId.trim()
                                ? 'Enter reviewer identifier to enable'
                                : 'Transition status to ACKNOWLEDGED'
                            }
                          >
                            <span>Acknowledge Escalation</span>
                          </button>
                        )}

                        {/* Resolve Button: Valid when PENDING or ACKNOWLEDGED */}
                        {(currentStatusNormalized === 'PENDING' ||
                          currentStatusNormalized === 'ACKNOWLEDGED') && (
                          <button
                            type="button"
                            className="btn-decision btn-resolve"
                            onClick={() => setPendingConfirmAction('resolved')}
                            disabled={isSubmitting || !reviewerId.trim()}
                            title={
                              !reviewerId.trim()
                                ? 'Enter reviewer identifier to enable'
                                : 'Transition status to RESOLVED'
                            }
                          >
                            <span>Resolve Escalation</span>
                          </button>
                        )}
                      </div>
                    )}

                    {!reviewerId.trim() && (
                      <span className="validation-warning-hint">
                        * Enter a Reviewer Identifier above to enable decision actions.
                      </span>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  );
};
