import React from 'react';
import { SparkleIcon } from '../common/Icons';
import './SuggestedQuestions.css';

export interface SuggestionItem {
  id: string;
  category: string;
  categoryType: 'trial' | 'literature';
  prompt: string;
}

const DEFAULT_SUGGESTIONS: SuggestionItem[] = [
  {
    id: 'sug-trial-oncology',
    category: 'Trial Analytics',
    categoryType: 'trial',
    prompt: 'Which Phase II oncology trials are below 60% enrollment right now?'
  },
  {
    id: 'sug-lit-cardiotox',
    category: 'Literature Research',
    categoryType: 'literature',
    prompt: 'What has our internal research said about JAK2 inhibitors and cardiotoxicity?'
  }
];

interface SuggestedQuestionsProps {
  onSelectSuggestion: (prompt: string) => void;
}

export const SuggestedQuestions: React.FC<SuggestedQuestionsProps> = ({
  onSelectSuggestion
}) => {
  return (
    <div className="suggested-questions-section" aria-label="Suggested research queries">
      <div className="suggested-questions-header">
        <span className="suggested-questions-icon">
          <SparkleIcon size={12} />
        </span>
        <span>Suggested questions</span>
      </div>

      <div className="suggested-questions-grid" role="group" aria-label="Suggested question chips">
        {DEFAULT_SUGGESTIONS.map((item) => (
          <button
            key={item.id}
            type="button"
            className="suggested-chip"
            onClick={() => onSelectSuggestion(item.prompt)}
            aria-label={`Fill composer with: ${item.prompt}`}
            title="Click to populate question composer (does not submit automatically)"
          >
            <div className="suggested-chip-top">
              <span className={`suggested-chip-tag ${item.categoryType}`}>
                {item.category}
              </span>
              <span className="suggested-chip-action-hint">Fill prompt ↵</span>
            </div>
            <p className="suggested-chip-text">{item.prompt}</p>
          </button>
        ))}
      </div>
    </div>
  );
};
