import React from 'react';
import './GlowingOrb.css';

export const GlowingOrb: React.FC = () => {
  return (
    <div className="glowing-orb-wrapper" aria-hidden="true">
      <div className="glowing-orb-aura" />
      <div className="glowing-orb-flare" />
      <div className="glowing-orb-ring" />
      <div className="glowing-orb-core">
        <div className="glowing-orb-highlight" />
      </div>
    </div>
  );
};
