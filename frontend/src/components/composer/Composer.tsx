import React, { useState } from 'react';
import { SendIcon } from '../common/Icons';
import './Composer.css';

export const MAX_QUESTION_LENGTH = 2000;

export interface ComposerProps {
  promptText: string;
  onChangePrompt: (text: string) => void;
  onSubmitQuestion: (text: string) => void;
  onFocusChange?: (focused: boolean) => void;
  textareaRef?: React.RefObject<HTMLTextAreaElement | null>;
  isAnalyzing?: boolean;
}

export const Composer: React.FC<ComposerProps> = ({
  promptText,
  onChangePrompt,
  onSubmitQuestion,
  onFocusChange,
  textareaRef,
  isAnalyzing = false
}) => {
  const [activeFilter, setActiveFilter] = useState<'all' | 'trials' | 'literature' | 'safety'>('all');

  const charCount = promptText.length;
  const trimmed = promptText.trim();
  const isEmpty = trimmed.length === 0;
  const isOverLimit = charCount > MAX_QUESTION_LENGTH;
  const isValid = !isEmpty && !isOverLimit && !isAnalyzing;

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Ctrl+Enter or Cmd+Enter submits the question
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      if (isValid) {
        onSubmitQuestion(trimmed);
      }
    }
    // Normal Enter creates a new line without submitting
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (isValid) {
      onSubmitQuestion(trimmed);
    }
  };

  return (
    <div className="composer-container">
      <form onSubmit={handleSubmit} className={`composer-card ${isOverLimit ? 'has-error' : ''}`}>
        {isOverLimit && (
          <div className="composer-validation-banner" role="alert">
            <span>Question exceeds the maximum limit of {MAX_QUESTION_LENGTH.toLocaleString()} characters.</span>
            <span>{charCount - MAX_QUESTION_LENGTH} chars over</span>
          </div>
        )}

        <div className="composer-input-row">
          <textarea
            ref={textareaRef}
            className="composer-textarea"
            placeholder={isAnalyzing ? 'Analysis in progress, please wait...' : 'Ask about trials, compounds, safety, or research literature...'}
            value={promptText}
            onChange={(e) => onChangePrompt(e.target.value)}
            onKeyDown={handleKeyDown}
            onFocus={() => onFocusChange?.(true)}
            onBlur={() => onFocusChange?.(false)}
            rows={2}
            aria-label="Research prompt input"
            aria-invalid={isOverLimit}
            disabled={isAnalyzing}
          />
        </div>

        <div className="composer-footer">
          <div className="composer-filters" role="group" aria-label="Evidence scope">
            <button
              type="button"
              className={`composer-filter-chip ${activeFilter === 'all' ? 'active' : ''}`}
              onClick={() => setActiveFilter('all')}
              disabled={isAnalyzing}
              title="Filter scope: All available evidence"
            >
              All Evidence
            </button>
            <button
              type="button"
              className={`composer-filter-chip ${activeFilter === 'trials' ? 'active' : ''}`}
              onClick={() => setActiveFilter('trials')}
              disabled={isAnalyzing}
              title="Filter scope: Clinical trials"
            >
              Trials (SQL)
            </button>
            <button
              type="button"
              className={`composer-filter-chip ${activeFilter === 'literature' ? 'active' : ''}`}
              onClick={() => setActiveFilter('literature')}
              disabled={isAnalyzing}
              title="Filter scope: Research documents"
            >
              Literature (RAG)
            </button>
            <button
              type="button"
              className={`composer-filter-chip ${activeFilter === 'safety' ? 'active' : ''}`}
              onClick={() => setActiveFilter('safety')}
              disabled={isAnalyzing}
              title="Filter scope: Safety records"
            >
              Safety Triage
            </button>
          </div>

          <div className="composer-actions">
            {charCount > 0 && (
              <span
                className={`composer-char-count ${
                  isOverLimit ? 'danger' : charCount >= 1800 ? 'warning' : ''
                }`}
                aria-live="polite"
              >
                {charCount.toLocaleString()} / {MAX_QUESTION_LENGTH.toLocaleString()}
              </span>
            )}

            <span className="composer-shortcut-hint" title="Keyboard shortcut to submit">
              Ctrl+↵
            </span>

            <div className="composer-model-badge" title="Active LLM Runtime Provider">
              <span className="model-indicator-dot" />
              <span>Groq / qwen-27b</span>
            </div>

            <button
              type="submit"
              className="composer-submit-btn"
              disabled={!isValid || isAnalyzing}
              aria-label="Submit analysis question"
              title={
                isAnalyzing
                  ? 'Analysis in progress, please wait...'
                  : isEmpty
                  ? 'Enter a question to submit'
                  : isOverLimit
                  ? 'Shorten question before submitting'
                  : 'Submit question (Ctrl+Enter)'
              }
            >
              <SendIcon size={16} />
            </button>
          </div>
        </div>
      </form>

      <p className="composer-disclaimer">
        PharmaSenseAI provides R&amp;D analysis over synthetic evidence. Clinical medical advice is strictly restricted by input guardrails.
      </p>
    </div>
  );
};
