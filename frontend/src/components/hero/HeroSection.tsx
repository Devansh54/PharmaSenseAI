import React from 'react';
import { GlowingOrb } from './GlowingOrb';
import { SparkleIcon } from '../common/Icons';
import './HeroSection.css';

export const HeroSection: React.FC = () => {
  return (
    <section className="hero-section" aria-label="Welcome Overview">
      <GlowingOrb />

      <div className="hero-pill">
        <span className="hero-pill-sparkle">
          <SparkleIcon size={13} />
        </span>
        <span>Evidence-First Multi-Agent Platform</span>
      </div>

      <h1 className="hero-heading">
        Ready to explore <span className="hero-heading-highlight">research evidence?</span>
      </h1>

      <p className="hero-subtitle">
        Analyze clinical trials, laboratory results, adverse-event records, and research literature with evidence-backed multi-agent intelligence.
      </p>
    </section>
  );
};
