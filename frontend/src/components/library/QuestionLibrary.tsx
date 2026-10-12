import React, { useState, useMemo } from 'react';
import {
  QUESTION_CATALOG,
  GOLDEN_SET_CASE_COUNT,
  CATALOG_TOTAL_COUNT
} from '../../data/questionCatalog';
import {
  SearchIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  SparkleIcon,
  AlertTriangleIcon,
  CheckCircleIcon,
  CloseIcon,
  FileTextIcon
} from '../common/Icons';
import './QuestionLibrary.css';

interface QuestionLibraryProps {
  onSelectQuestion: (query: string) => void;
}

export const QuestionLibrary: React.FC<QuestionLibraryProps> = ({ onSelectQuestion }) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [selectedStatus, setSelectedStatus] = useState<string>('all');
  const [selectedType, setSelectedType] = useState<string>('all');
  const [expandedCardId, setExpandedCardId] = useState<string | null>(null);

  // Extract unique categories from catalog
  const categories = useMemo(() => {
    const cats = Array.from(new Set(QUESTION_CATALOG.map((item) => item.category)));
    return cats.sort();
  }, []);

  // Filtered catalog
  const filteredCatalog = useMemo(() => {
    const qLower = searchQuery.trim().toLowerCase();

    return QUESTION_CATALOG.filter((item) => {
      // Category filter
      if (selectedCategory !== 'all' && item.category !== selectedCategory) {
        return false;
      }

      // Status filter
      if (selectedStatus === 'historical_live' && item.historical_live_status !== 'passed') {
        return false;
      }
      if (selectedStatus === 'offline_pass' && item.offline_status !== 'passed') {
        return false;
      }
      if (selectedStatus === 'disputed' && item.offline_status !== 'disputed') {
        return false;
      }
      if (selectedStatus === 'blocked' && item.offline_status !== 'blocked') {
        return false;
      }

      // Type filter
      if (selectedType === 'research' && item.is_evaluation_only) {
        return false;
      }
      if (selectedType === 'eval_only' && !item.is_evaluation_only) {
        return false;
      }

      // Text search
      if (qLower) {
        const matchText = (
          item.query +
          ' ' +
          item.id +
          ' ' +
          item.category +
          ' ' +
          item.workflow_type +
          ' ' +
          item.status_notes +
          ' ' +
          item.sources.join(' ') +
          ' ' +
          item.golden_case_ids.join(' ') +
          ' ' +
          item.acceptance_scenario_ids.join(' ') +
          ' ' +
          item.expected_specialists.join(' ') +
          ' ' +
          item.expected_tools.join(' ')
        ).toLowerCase();

        if (!matchText.includes(qLower)) {
          return false;
        }
      }

      return true;
    });
  }, [searchQuery, selectedCategory, selectedStatus, selectedType]);

  const toggleExpand = (id: string) => {
    setExpandedCardId((prev) => (prev === id ? null : id));
  };

  const clearFilters = () => {
    setSearchQuery('');
    setSelectedCategory('all');
    setSelectedStatus('all');
    setSelectedType('all');
  };

  const hasActiveFilters =
    searchQuery.trim() !== '' ||
    selectedCategory !== 'all' ||
    selectedStatus !== 'all' ||
    selectedType !== 'all';

  return (
    <div className="question-library-container" aria-label="Question Library Explorer">
      {/* Safety Disclaimer Banner */}
      <div className="library-safety-banner" role="note">
        <span className="library-safety-icon" aria-hidden="true">
          <AlertTriangleIcon size={15} />
        </span>
        <span>
          <strong>Synthetic research data</strong>; for R&amp;D/clinical operations analysis only.
          Not for patient diagnosis, treatment advice, or emergency response.
        </span>
      </div>

      {/* Header section */}
      <div className="library-header">
        <div className="library-header-main">
          <div className="library-title-row">
            <h1 className="library-title">Question Library</h1>
            <span className="library-badge-pill">{CATALOG_TOTAL_COUNT} Questions</span>
          </div>
          <p className="library-subtitle">
            Explore the complete repository inventory of {CATALOG_TOTAL_COUNT} benchmark queries,
            Tier 1 acceptance scenarios, and guardrail validation test cases. Select any query to
            load it directly into the analysis composer.
          </p>
        </div>

        {/* Aggregate Metadata Metrics */}
        <div className="library-stat-grid">
          <div className="library-stat-card">
            <span className="library-stat-value">{CATALOG_TOTAL_COUNT}</span>
            <span className="library-stat-label">Total Catalog</span>
          </div>
          <div className="library-stat-card">
            <span className="library-stat-value">{GOLDEN_SET_CASE_COUNT}</span>
            <span className="library-stat-label">Golden Cases</span>
          </div>
          <div className="library-stat-card">
            <span className="library-stat-value">8</span>
            <span className="library-stat-label">Tier 1 Acceptance</span>
          </div>
          <div className="library-stat-card">
            <span className="library-stat-value">2</span>
            <span className="library-stat-label">Default Suggestions</span>
          </div>
        </div>
      </div>

      {/* Local Controls Bar: Search & Filtering (zero network requests) */}
      <div className="library-controls-bar">
        {/* Search input */}
        <div className="library-search-wrapper">
          <span className="library-search-icon" aria-hidden="true">
            <SearchIcon size={16} />
          </span>
          <input
            type="text"
            className="library-search-input"
            placeholder="Search by query text, ID, category, source, status, or specialist..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            aria-label="Search question catalog"
          />
          {searchQuery && (
            <button
              type="button"
              className="library-search-clear"
              onClick={() => setSearchQuery('')}
              aria-label="Clear search text"
            >
              <CloseIcon size={14} />
            </button>
          )}
        </div>

        {/* Filter controls */}
        <div className="library-filters-row">
          <div className="library-filter-group">
            <label htmlFor="category-select" className="library-filter-label">
              Category:
            </label>
            <select
              id="category-select"
              className="library-select"
              value={selectedCategory}
              onChange={(e) => setSelectedCategory(e.target.value)}
            >
              <option value="all">All Categories ({QUESTION_CATALOG.length})</option>
              {categories.map((cat) => {
                const count = QUESTION_CATALOG.filter((c) => c.category === cat).length;
                return (
                  <option key={cat} value={cat}>
                    {cat} ({count})
                  </option>
                );
              })}
            </select>
          </div>

          <div className="library-filter-group">
            <label htmlFor="status-select" className="library-filter-label">
              Verification Status:
            </label>
            <select
              id="status-select"
              className="library-select"
              value={selectedStatus}
              onChange={(e) => setSelectedStatus(e.target.value)}
            >
              <option value="all">All Statuses</option>
              <option value="historical_live">
                Historical Live Pass (
                {QUESTION_CATALOG.filter((c) => c.historical_live_status === 'passed').length}
                )
              </option>
              <option value="offline_pass">
                Offline Pass (
                {QUESTION_CATALOG.filter((c) => c.offline_status === 'passed').length}
                )
              </option>
              <option value="disputed">
                Disputed / Naming Mismatch (
                {QUESTION_CATALOG.filter((c) => c.offline_status === 'disputed').length}
                )
              </option>
              <option value="blocked">
                Blocked / Contract Mismatch (
                {QUESTION_CATALOG.filter((c) => c.offline_status === 'blocked').length}
                )
              </option>
            </select>
          </div>

          <div className="library-filter-group">
            <label htmlFor="type-select" className="library-filter-label">
              Scope:
            </label>
            <select
              id="type-select"
              className="library-select"
              value={selectedType}
              onChange={(e) => setSelectedType(e.target.value)}
            >
              <option value="all">All Inquiries</option>
              <option value="research">
                Research Queries Only (
                {QUESTION_CATALOG.filter((c) => !c.is_evaluation_only).length}
                )
              </option>
              <option value="eval_only">
                Evaluation &amp; Guardrails Only (
                {QUESTION_CATALOG.filter((c) => c.is_evaluation_only).length}
                )
              </option>
            </select>
          </div>

          {hasActiveFilters && (
            <button
              type="button"
              className="library-reset-btn"
              onClick={clearFilters}
              title="Reset all search filters"
            >
              Reset Filters
            </button>
          )}
        </div>
      </div>

      {/* Results Header Count */}
      <div className="library-results-meta">
        <span className="library-results-count">
          Showing <strong>{filteredCatalog.length}</strong> of {CATALOG_TOTAL_COUNT} questions
        </span>
      </div>

      {/* Catalog Cards Grid */}
      {filteredCatalog.length === 0 ? (
        <div className="library-empty-state">
          <div className="library-empty-icon">
            <FileTextIcon size={32} />
          </div>
          <h3 className="library-empty-title">No questions found</h3>
          <p className="library-empty-desc">
            No catalog items matched your current search and filter criteria.
          </p>
          <button type="button" className="library-empty-btn" onClick={clearFilters}>
            Clear all filters
          </button>
        </div>
      ) : (
        <div className="library-cards-list" role="feed" aria-label="Question inventory list">
          {filteredCatalog.map((item) => {
            const isExpanded = expandedCardId === item.id;

            return (
              <article key={item.id} className="library-card" aria-labelledby={`q-title-${item.id}`}>
                {/* Card Header Row */}
                <div className="library-card-header">
                  <div className="library-card-tags">
                    <span className="library-category-badge">{item.category}</span>
                    <span className="library-id-pill">{item.id}</span>

                    {item.show_as_suggestion && (
                      <span className="library-status-badge suggestion-badge">
                        <SparkleIcon size={11} /> Default Suggestion
                      </span>
                    )}

                    {item.is_evaluation_only && (
                      <span className="library-status-badge eval-badge">
                        Evaluation Only
                      </span>
                    )}

                    {item.acceptance_scenario_ids.length > 0 && (
                      <span className="library-status-badge acc-badge">
                        Scenario: {item.acceptance_scenario_ids.join(', ')}
                      </span>
                    )}

                    {item.golden_case_ids.length > 0 && (
                      <span className="library-status-badge golden-badge">
                        {item.golden_case_ids.join(', ')}
                      </span>
                    )}
                  </div>

                  {/* Verification Status Pills */}
                  <div className="library-card-statuses">
                    {item.historical_live_status === 'passed' ? (
                      <span className="library-status-pill status-live-pass" title="Documented in historical live acceptance report">
                        <CheckCircleIcon size={12} /> Historical Live Pass
                      </span>
                    ) : (
                      <span className="library-status-pill status-live-unverified" title="Not documented in live acceptance suite">
                        Live: Unverified
                      </span>
                    )}

                    {item.offline_status === 'passed' ? (
                      <span className="library-status-pill status-offline-pass" title="Offline verification passing">
                        Offline Pass
                      </span>
                    ) : item.offline_status === 'disputed' ? (
                      <span className="library-status-pill status-disputed" title="Naming discrepancy between golden set and agent registry">
                        <AlertTriangleIcon size={12} /> Disputed (Naming Mismatch)
                      </span>
                    ) : item.offline_status === 'blocked' ? (
                      <span className="library-status-pill status-blocked" title="Tool name contract mismatch">
                        <CloseIcon size={12} /> Blocked (Contract Mismatch)
                      </span>
                    ) : (
                      <span className="library-status-pill status-offline-unverified">
                        Offline: Unverified
                      </span>
                    )}

                    <span className="library-status-pill status-current-pending" title="Current uncommitted code revision has not undergone live Groq testing">
                      Current Rev: Pending Live
                    </span>
                  </div>
                </div>

                {/* Query Text */}
                <p id={`q-title-${item.id}`} className="library-card-query">
                  &ldquo;{item.query}&rdquo;
                </p>

                {/* Card Action Row */}
                <div className="library-card-actions">
                  <button
                    type="button"
                    className="library-select-btn"
                    onClick={() => onSelectQuestion(item.query)}
                    aria-label={`Select query and open in composer: ${item.query}`}
                  >
                    <span>Use in Composer</span>
                    <span className="library-btn-arrow">&crarr;</span>
                  </button>

                  <button
                    type="button"
                    className="library-details-toggle"
                    onClick={() => toggleExpand(item.id)}
                    aria-expanded={isExpanded}
                    aria-controls={`details-${item.id}`}
                  >
                    <span>{isExpanded ? 'Hide Details' : 'View Details'}</span>
                    <span className="library-toggle-icon">
                      {isExpanded ? <ChevronDownIcon size={14} /> : <ChevronRightIcon size={14} />}
                    </span>
                  </button>
                </div>

                {/* Expandable Technical Details Accordion */}
                {isExpanded && (
                  <div id={`details-${item.id}`} className="library-card-details">
                    <div className="library-detail-row">
                      <span className="library-detail-label">Workflow Type:</span>
                      <span className="library-detail-value">{item.workflow_type}</span>
                    </div>

                    {item.expected_specialists.length > 0 && (
                      <div className="library-detail-row">
                        <span className="library-detail-label">Expected Specialists:</span>
                        <span className="library-detail-value">
                          {item.expected_specialists.join(', ')}
                        </span>
                      </div>
                    )}

                    {item.expected_tools.length > 0 && (
                      <div className="library-detail-row">
                        <span className="library-detail-label">Expected Tools:</span>
                        <span className="library-detail-value">
                          {item.expected_tools.join(', ')}
                        </span>
                      </div>
                    )}

                    <div className="library-detail-row">
                      <span className="library-detail-label">Repository Sources:</span>
                      <span className="library-detail-value sources-list">
                        {item.sources.join(', ')}
                      </span>
                    </div>

                    <div className="library-detail-row">
                      <span className="library-detail-label">Status &amp; Provenance Notes:</span>
                      <span className="library-detail-value notes-text">
                        {item.status_notes}
                      </span>
                    </div>
                  </div>
                )}
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
};
