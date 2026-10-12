import React, { useEffect } from 'react';
import { type NavTabId, NAV_ITEMS } from '../../types/navigation';
import {
  LogoIcon,
  CloseIcon,
  PlusSparkleIcon,
  WorkspaceIcon,
  LibraryIcon,
  ShieldCheckIcon
} from '../common/Icons';
import './MobileNav.css';

interface MobileDrawerProps {
  isOpen: boolean;
  activeTab: NavTabId;
  onClose: () => void;
  onSelectTab: (tab: NavTabId) => void;
}

export const MobileDrawer: React.FC<MobileDrawerProps> = ({
  isOpen,
  activeTab,
  onClose,
  onSelectTab
}) => {
  // Close drawer on escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  const getNavIcon = (id: NavTabId) => {
    switch (id) {
      case 'new-analysis':
        return <PlusSparkleIcon size={18} />;
      case 'workspace':
        return <WorkspaceIcon size={18} />;
      case 'library':
        return <LibraryIcon size={18} />;
      case 'review':
        return <ShieldCheckIcon size={18} />;
    }
  };

  return (
    <>
      <div
        className={`mobile-drawer-backdrop ${isOpen ? 'open' : ''}`}
        onClick={onClose}
        aria-hidden="true"
      />

      <div
        className={`mobile-drawer ${isOpen ? 'open' : ''}`}
        role="dialog"
        aria-modal="true"
        aria-label="Navigation Menu"
      >
        <div className="mobile-drawer-header">
          <div className="mobile-brand">
            <LogoIcon size={20} />
            <span className="mobile-brand-title">
              PharmaSense <span className="mobile-brand-badge">AI</span>
            </span>
          </div>

          <button
            type="button"
            className="mobile-drawer-close-btn"
            onClick={onClose}
            aria-label="Close menu"
          >
            <CloseIcon size={20} />
          </button>
        </div>

        <nav className="mobile-drawer-nav" aria-label="Mobile navigation links">
          {NAV_ITEMS.map((item) => {
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                type="button"
                className={`mobile-drawer-item ${isActive ? 'active' : ''}`}
                onClick={() => {
                  onSelectTab(item.id);
                  onClose();
                }}
              >
                <div className="mobile-drawer-item-left">
                  <span>{getNavIcon(item.id)}</span>
                  <span>{item.label}</span>
                </div>
                {item.badge && (
                  <span
                    className={`sidebar-nav-badge ${
                      item.id === 'review' ? 'danger' : 'accent'
                    }`}
                  >
                    {item.badge}
                  </span>
                )}
              </button>
            );
          })}
        </nav>

        <div className="mobile-drawer-footer">
          <div className="sidebar-status-box">
            <div className="sidebar-status-row">
              <span className="sidebar-status-label">Database</span>
              <span className="sidebar-status-value">
                <span className="sidebar-status-dot" />
                <span>pgvector :5432</span>
              </span>
            </div>
            <div className="sidebar-status-row">
              <span className="sidebar-status-label">Model</span>
              <span className="sidebar-status-value">qwen3.8-27b</span>
            </div>
          </div>
        </div>
      </div>
    </>
  );
};
