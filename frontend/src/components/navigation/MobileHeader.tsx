import React from 'react';
import { LogoIcon, MenuIcon } from '../common/Icons';
import './MobileNav.css';

interface MobileHeaderProps {
  onToggleDrawer: () => void;
  healthStatus?: 'checking' | 'ready' | 'offline';
}

export const MobileHeader: React.FC<MobileHeaderProps> = ({
  onToggleDrawer,
  healthStatus = 'ready'
}) => {
  return (
    <header className="mobile-header" aria-label="Mobile Application Bar">
      <div className="mobile-header-left">
        <button
          type="button"
          className="mobile-menu-btn"
          onClick={onToggleDrawer}
          aria-label="Open Navigation Drawer"
        >
          <MenuIcon size={20} />
        </button>

        <div className="mobile-brand">
          <LogoIcon size={18} />
          <span className="mobile-brand-title">
            PharmaSense <span className="mobile-brand-badge">AI</span>
          </span>
        </div>
      </div>

      <div className="mobile-header-right">
        <div className={`mobile-status-pill ${healthStatus}`} title={`Backend API: ${healthStatus}`}>
          <span className={`mobile-status-dot ${healthStatus}`} />
          <span>{healthStatus === 'ready' ? 'Ready' : healthStatus === 'offline' ? 'Offline' : 'Checking'}</span>
        </div>
      </div>
    </header>
  );
};
