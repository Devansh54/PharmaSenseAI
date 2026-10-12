import React from 'react';
import {
  ActivityIcon,
  FileTextIcon,
  GitBranchIcon,
  AlertTriangleIcon,
  ArrowUpRightIcon
} from '../common/Icons';
import './FeatureCards.css';

interface FeatureCardItem {
  id: string;
  title: string;
  description: string;
  tag: string;
  type: 'trial' | 'literature' | 'similarity' | 'safety';
  icon: React.ReactNode;
}

const CAPABILITY_CARDS: FeatureCardItem[] = [
  {
    id: 'trial-analytics',
    title: 'Trial Analytics',
    description: 'Query structured Phase I–IV trials, enrollment thresholds, and site operations across 110 clinical trials.',
    tag: 'SQL Engine',
    type: 'trial',
    icon: <ActivityIcon size={18} />
  },
  {
    id: 'literature-research',
    title: 'Literature Research',
    description: 'Retrieve verified scientific literature findings with strict citation grounding over 250 research documents.',
    tag: 'pgvector RAG',
    type: 'literature',
    icon: <FileTextIcon size={18} />
  },
  {
    id: 'compound-similarity',
    title: 'Compound Similarity',
    description: 'Analyze multi-attribute candidate similarity over 150 compounds across target, therapeutic area, and phase.',
    tag: 'Attribute Distance',
    type: 'similarity',
    icon: <GitBranchIcon size={18} />
  },
  {
    id: 'safety-human-review',
    title: 'Safety & Human Review',
    description: 'Triage adverse event severity and automatically escalate serious safety signals to human review queues.',
    tag: 'Triage & Escalation',
    type: 'safety',
    icon: <AlertTriangleIcon size={18} />
  }
];

interface FeatureCardsProps {
  onCardClick?: (id: string) => void;
}

export const FeatureCards: React.FC<FeatureCardsProps> = ({ onCardClick }) => {
  return (
    <section className="feature-cards-container" aria-label="Core Capabilities">
      <div className="feature-cards-header">
        <h2 className="feature-cards-title">Core Research Capabilities</h2>
      </div>

      <div className="feature-cards-grid">
        {CAPABILITY_CARDS.map((card) => (
          <div
            key={card.id}
            className="feature-card"
            onClick={() => onCardClick?.(card.id)}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onCardClick?.(card.id);
              }
            }}
            aria-label={`${card.title}: ${card.description}`}
          >
            <div className="feature-card-top">
              <div className={`feature-card-icon-badge ${card.type}`}>
                {card.icon}
              </div>
              <span className="feature-card-tag">{card.tag}</span>
            </div>

            <div className="feature-card-body">
              <h3>
                <span>{card.title}</span>
                <span className="feature-card-arrow" aria-hidden="true">
                  <ArrowUpRightIcon size={14} />
                </span>
              </h3>
              <p>{card.description}</p>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
};
