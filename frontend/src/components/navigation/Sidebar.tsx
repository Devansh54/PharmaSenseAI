import React from 'react';
import { type NavTabId, NAV_ITEMS } from '../../types/navigation';
import {
  LogoIcon,
  PlusSparkleIcon,
  WorkspaceIcon,
  LibraryIcon,
  ShieldCheckIcon
} from '../common/Icons';
import './Sidebar.css';

interface SidebarProps {
  activeTab: NavTabId;
  onSelectTab: (tab: NavTabId) => void;
  healthStatus?: 'checking' | 'ready' | 'offline';
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  onSelectTab,
  healthStatus = 'ready'
}) => {
  const getNavIcon = (id: NavTabId) => {
    switch (id) {
      case 'new-analysis':
        return <PlusSparkleIcon size={17} />;
      case 'workspace':
        return <WorkspaceIcon size={17} />;
      case 'library':
        return <LibraryIcon size={17} />;
      case 'review':
        return <ShieldCheckIcon size={17} />;
    }
  };

  return (
    <aside className="app-sidebar" aria-label="Desktop Navigation">
      <div>
        <div className="sidebar-header">
          <div className="sidebar-brand">
            <div className="sidebar-brand-icon">
              <LogoIcon size={20} />
            </div>
            <div className="sidebar-brand-text">
              <span className="sidebar-brand-title">
                PharmaSense <span className="sidebar-brand-badge">AI</span>
              </span>
              <span className="sidebar-brand-sub">R&amp;D Intelligence</span>
            </div>
          </div>
        </div>

        <nav className="sidebar-nav-section" aria-label="Main menu">
          <span className="sidebar-nav-heading">Analysis &amp; Operations</span>
          {NAV_ITEMS.map((item) => {
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                type="button"
                className={`sidebar-nav-item ${isActive ? 'active' : ''}`}
                onClick={() => onSelectTab(item.id)}
                title={item.description}
                aria-current={isActive ? 'page' : undefined}
              >
                <div className="sidebar-nav-item-left">
                  <span className="sidebar-nav-item-icon">{getNavIcon(item.id)}</span>
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
      </div>

      <div className="sidebar-footer">
        <div className="sidebar-status-box" aria-label="System status">
          <div className="sidebar-status-row">
            <span className="sidebar-status-label">Backend API</span>
            <span className="sidebar-status-value">
              <span className={`sidebar-status-dot ${healthStatus}`} />
              <span>{healthStatus === 'ready' ? 'Ready (:8000)' : healthStatus === 'offline' ? 'Offline' : 'Checking...'}</span>
            </span>
          </div>
          <div className="sidebar-status-row">
            <span className="sidebar-status-label">Database</span>
            <span className="sidebar-status-value">
              <span className="sidebar-status-dot" />
              <span>pgvector :5432</span>
            </span>
          </div>
          <div className="sidebar-status-row">
            <span className="sidebar-status-label">Runtime LLM</span>
            <span className="sidebar-status-value">qwen3.8-27b</span>
          </div>
        </div>

        <div className="sidebar-user-pill">
          <div className="sidebar-user-info">
            <div className="sidebar-user-avatar">RD</div>
            <span className="sidebar-user-name">Clinical Ops</span>
          </div>
          <span className="sidebar-version-tag">v0.2.1</span>
        </div>
      </div>
    </aside>
  );
};
