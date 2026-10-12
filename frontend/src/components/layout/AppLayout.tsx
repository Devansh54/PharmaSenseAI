import React, { useState, useRef, useEffect } from 'react';
import type { NavTabId } from '../../types/navigation';
import type { AnalysisResponse, RequestLifecycleState } from '../../types/api';
import { createAnalysis, checkHealth, classifyAnalysisOutcome, AnalysisApiError } from '../../services/api';
import { Sidebar } from '../navigation/Sidebar';
import { MobileHeader } from '../navigation/MobileHeader';
import { MobileDrawer } from '../navigation/MobileDrawer';
import { HeroSection } from '../hero/HeroSection';
import { Composer } from '../composer/Composer';
import { SuggestedQuestions } from '../composer/SuggestedQuestions';
import { FeatureCards } from '../cards/FeatureCards';
import { ResponseCard } from '../response/ResponseCard';
import { QuestionLibrary } from '../library/QuestionLibrary';
import { ReviewQueue } from '../review/ReviewQueue';
import { WorkspaceIcon } from '../common/Icons';
import './AppLayout.css';

export const AppLayout: React.FC = () => {
  const [activeTab, setActiveTab] = useState<NavTabId>('new-analysis');
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [promptText, setPromptText] = useState<string>('');

  // Request Flow & Lifecycle State (Phase 3)
  const [lifecycleState, setLifecycleState] = useState<RequestLifecycleState>('idle');
  const [activeQuestion, setActiveQuestion] = useState<string>('');
  const [analysisResponse, setAnalysisResponse] = useState<AnalysisResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [healthStatus, setHealthStatus] = useState<'checking' | 'ready' | 'offline'>('checking');

  const [selectedReviewTaskId, setSelectedReviewTaskId] = useState<string | null>(null);

  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  // Bounded initial health check
  useEffect(() => {
    let isMounted = true;
    checkHealth()
      .then((res) => {
        if (isMounted) {
          setHealthStatus(res.status === 'ok' ? 'ready' : 'offline');
        }
      })
      .catch(() => {
        if (isMounted) {
          setHealthStatus('offline');
        }
      });
    return () => {
      isMounted = false;
    };
  }, []);

  const handleSelectSuggestion = (suggestionPrompt: string) => {
    // Populate textarea with suggestion without submitting
    setPromptText(suggestionPrompt);
    // Focus the textarea so user can immediately edit
    setTimeout(() => {
      textareaRef.current?.focus();
    }, 50);
  };

  const handleSelectFromLibrary = (selectedQuery: string) => {
    // Populate textarea with library question, switch to new-analysis tab without submitting
    setPromptText(selectedQuery);
    setActiveTab('new-analysis');
    setTimeout(() => {
      textareaRef.current?.focus();
    }, 50);
  };

  const handleSubmitQuestion = async (submittedText: string) => {
    // Prevent duplicate submission while already running
    if (lifecycleState === 'loading') {
      return;
    }

    const trimmed = submittedText.trim();
    if (!trimmed) {
      return;
    }

    // Set truthful loading lifecycle state and preserve submitted question
    setActiveQuestion(trimmed);
    setLifecycleState('loading');
    setErrorMessage(null);
    setAnalysisResponse(null);
    setPromptText('');

    try {
      const response = await createAnalysis({ user_prompt: trimmed });
      const outcome = classifyAnalysisOutcome(response);
      setLifecycleState(outcome);
      setAnalysisResponse(response);
    } catch (err) {
      const displayMsg =
        err instanceof AnalysisApiError || err instanceof Error
          ? err.message
          : 'An unexpected error occurred while processing the analysis.';
      setLifecycleState('failed');
      setErrorMessage(displayMsg);
    }
  };

  const handleRetry = () => {
    if (activeQuestion && lifecycleState !== 'loading') {
      void handleSubmitQuestion(activeQuestion);
    }
  };

  const handleDismissResponse = () => {
    setLifecycleState('idle');
    setAnalysisResponse(null);
    setErrorMessage(null);
    setActiveQuestion('');
  };

  const handleCardClick = (cardId: string) => {
    // Clicking capability card populates a representative question
    switch (cardId) {
      case 'trial-analytics':
        handleSelectSuggestion('Which Phase II oncology trials are below 60% enrollment right now?');
        break;
      case 'literature-research':
        handleSelectSuggestion('What has our internal research said about JAK2 inhibitors and cardiotoxicity?');
        break;
      case 'compound-similarity':
        handleSelectSuggestion('Find compounds similar to DKU-1042 and explain why they are considered similar.');
        break;
      case 'safety-human-review':
        handleSelectSuggestion('A site just reported a serious adverse event for Trial TRL-0034 - triage it.');
        break;
    }
  };

  const handleNavigateToReview = (taskId: string) => {
    setSelectedReviewTaskId(taskId);
    setActiveTab('review');
  };

  const isAnalyzing = lifecycleState === 'loading';

  const renderContent = () => {
    switch (activeTab) {
      case 'new-analysis':
        return (
          <>
            <HeroSection />
            <Composer
              promptText={promptText}
              onChangePrompt={setPromptText}
              onSubmitQuestion={handleSubmitQuestion}
              textareaRef={textareaRef}
              isAnalyzing={isAnalyzing}
            />
            <SuggestedQuestions onSelectSuggestion={handleSelectSuggestion} />

            <ResponseCard
              lifecycleState={lifecycleState}
              question={activeQuestion}
              response={analysisResponse}
              errorMessage={errorMessage}
              onDismiss={handleDismissResponse}
              onRetry={handleRetry}
              onNavigateToReview={handleNavigateToReview}
            />

            <FeatureCards onCardClick={handleCardClick} />
          </>
        );

      case 'workspace':
        return (
          <div className="secondary-tab-view">
            <div className="secondary-tab-icon">
              <WorkspaceIcon size={24} />
            </div>
            <h2 className="secondary-tab-title">Analysis Workspace</h2>
            <p className="secondary-tab-desc">
              Multi-agent orchestration traces, specialist sub-task execution graphs, and synthesis reports will be presented here in Phase 4.
            </p>
            <span className="secondary-tab-pill">Roadmap: Phase 4</span>
          </div>
        );

      case 'library':
        return <QuestionLibrary onSelectQuestion={handleSelectFromLibrary} />;

      case 'review':
        return (
          <ReviewQueue
            initialTaskId={selectedReviewTaskId}
            onSelectReviewTask={(task) => setSelectedReviewTaskId(task.task_id)}
          />
        );
    }
  };

  return (
    <div className="app-shell">
      {/* Background ambient lighting */}
      <div className="app-ambient-glow" aria-hidden="true" />

      {/* Desktop sidebar */}
      <Sidebar activeTab={activeTab} onSelectTab={setActiveTab} healthStatus={healthStatus} />

      {/* Mobile top header */}
      <MobileHeader onToggleDrawer={() => setIsDrawerOpen(true)} healthStatus={healthStatus} />

      {/* Mobile slide-out drawer */}
      <MobileDrawer
        isOpen={isDrawerOpen}
        activeTab={activeTab}
        onClose={() => setIsDrawerOpen(false)}
        onSelectTab={setActiveTab}
      />

      {/* Central main workspace canvas */}
      <main className="app-main-canvas" role="main">
        <div className="canvas-content-wrapper">
          {renderContent()}
        </div>
      </main>
    </div>
  );
};
