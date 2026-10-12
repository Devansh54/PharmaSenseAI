import { Component, type ErrorInfo, type ReactNode } from 'react';
import { LogoIcon, AlertTriangleIcon } from './Icons';
import './ErrorBoundary.css';

export interface ErrorBoundaryProps {
  children: ReactNode;
  fallbackTitle?: string;
  onReset?: () => void;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error('PharmaSenseAI React Error Boundary caught an exception:', error, errorInfo);
  }

  handleReset = (): void => {
    this.setState({ hasError: false, error: null });
    if (this.props.onReset) {
      this.props.onReset();
    }
  };

  handleReload = (): void => {
    window.location.reload();
  };

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div className="error-boundary-container" role="alert">
          <div className="error-boundary-card">
            <div className="error-boundary-header">
              <div className="error-boundary-brand">
                <LogoIcon size={24} />
                <span className="error-boundary-brand-name">
                  PharmaSense <span className="error-boundary-badge">AI</span>
                </span>
              </div>
              <span className="error-boundary-tag">Runtime Recovery</span>
            </div>

            <div className="error-boundary-body">
              <div className="error-boundary-icon-wrap">
                <AlertTriangleIcon size={32} />
              </div>
              <h2 className="error-boundary-title">
                {this.props.fallbackTitle || 'Application Encountered an Unexpected Error'}
              </h2>
              <p className="error-boundary-desc">
                A client rendering exception occurred. You can attempt to recover the session without losing application state, or reload the page.
              </p>

              {this.state.error?.message && (
                <div className="error-boundary-details">
                  <span className="error-details-label">Diagnostic Details:</span>
                  <pre className="error-details-text">{this.state.error.message}</pre>
                </div>
              )}

              <div className="error-boundary-actions">
                <button
                  type="button"
                  className="error-boundary-btn-primary"
                  onClick={this.handleReset}
                >
                  Attempt In-Session Recovery ↻
                </button>
                <button
                  type="button"
                  className="error-boundary-btn-secondary"
                  onClick={this.handleReload}
                >
                  Reload Page
                </button>
              </div>

              <div className="error-boundary-help">
                <span>Developer Note: If experiencing stale Vite module resolution or missing export caching after code edits, restart the dev server with: <code>npm run dev -- --force</code></span>
              </div>
            </div>

            <p className="error-boundary-disclaimer">
              Synthetic research data; for R&amp;D/clinical operations analysis only. Not for patient diagnosis, treatment advice, or emergency response.
            </p>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
