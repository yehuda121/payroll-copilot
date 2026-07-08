import { useState } from 'react';
import { useTranslation } from 'react-i18next';
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
  const [mode, setMode] = useState<GuestWorkspaceMode | null>(null);
  const [assistantContext, setAssistantContext] = useState<AssistantFollowUpContext | undefined>();

  return (
    <div className="landing">
      <section className="landing__hero landing__hero--compact">
        <div>
          <p className="landing__eyebrow">{t('landing.eyebrow')}</p>
          <h1>{t('landing.title')}</h1>
          <p className="landing__hero-lead">{t('landing.lead')}</p>
        </div>
      </section>

      <section className="guest-action-cards" aria-label={t('landing.primaryActions')}>
        <button
          type="button"
          className={`guest-action-card ${mode === 'assistant' ? 'is-active' : ''}`}
          onClick={() => setMode('assistant')}
        >
          <h2>{t('landing.assistantTitle')}</h2>
          <p>{t('landing.assistantBody')}</p>
        </button>
        <button
          type="button"
          className={`guest-action-card ${mode === 'validate' ? 'is-active' : ''}`}
          onClick={() => setMode('validate')}
        >
          <h2>{t('landing.validateTitle')}</h2>
          <p>{t('landing.validateBody')}</p>
        </button>
      </section>

      {mode && (
        <section className="landing__workspace">
          <GuestWorkspace
            mode={mode}
            assistantContext={assistantContext}
            onFollowUp={(context) => {
              setAssistantContext(context);
              setMode('assistant');
            }}
          />
        </section>
      )}
    </div>
  );
}
