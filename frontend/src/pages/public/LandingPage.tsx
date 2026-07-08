import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { GuestChatPanel } from '../../components/guest/GuestChatPanel';
import type { GuestWorkspaceMode } from '../../features/guest/GuestWorkspace';
import { GuestWorkspace } from '../../features/guest/GuestWorkspace';
import '../../features/guest/guest.css';
import '../../layouts/PublicLayout.css';

export type AssistantFollowUpContext = {
  validationRunId: string;
  documentIds: string[];
};

export function LandingPage() {
  const { t } = useTranslation();
  const [mode, setMode] = useState<GuestWorkspaceMode>('assistant');
  const [assistantContext, setAssistantContext] = useState<AssistantFollowUpContext | undefined>();
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null);

  const suggestedQuestions = [
    t('assistant.suggested1'),
    t('assistant.suggested2'),
    t('assistant.suggested3'),
  ];

  if (mode === 'validate') {
    return (
      <div className="landing">
        <section className="landing__validate-shell">
          <button type="button" className="btn btn--ghost" onClick={() => setMode('assistant')}>
            {t('common.back')}
          </button>
          <GuestWorkspace
            mode="validate"
            onFollowUp={(context) => {
              setAssistantContext(context);
              setMode('assistant');
            }}
          />
        </section>
      </div>
    );
  }

  return (
    <div className="landing">
      <section className="landing__hero landing__hero--compact">
        <div>
          <p className="landing__eyebrow">{t('landing.eyebrow')}</p>
          <h1>{t('landing.title')}</h1>
          <p className="landing__hero-lead">{t('landing.lead')}</p>
        </div>
      </section>

      <section className="landing__split" aria-label={t('landing.title')}>
        <div className="landing__chat-pane">
          <GuestChatPanel
            validationRunId={assistantContext?.validationRunId}
            documentIds={assistantContext?.documentIds ?? []}
            showSuggestionsInline={false}
            pendingQuestion={pendingQuestion}
            onPendingQuestionConsumed={() => setPendingQuestion(null)}
          />
        </div>

        <aside className="landing__side-pane">
          <div className="landing__suggestions-card">
            <h2>{t('landing.suggestionsHeading')}</h2>
            <div className="landing__suggestion-list">
              {suggestedQuestions.map((question) => (
                <button
                  key={question}
                  type="button"
                  className="btn btn--secondary landing__suggestion-btn"
                  onClick={() => setPendingQuestion(question)}
                >
                  {question}
                </button>
              ))}
            </div>
          </div>

          <div className="landing__cta-card">
            <h2>{t('landing.validateCta')}</h2>
            <p>{t('landing.validateCtaHint')}</p>
            <button
              type="button"
              className="btn btn--primary btn--large"
              onClick={() => setMode('validate')}
            >
              {t('landing.validateCta')}
            </button>
          </div>
        </aside>
      </section>
    </div>
  );
}
