import { useState } from 'react';
import type { GuestWorkspaceMode } from '../../features/guest/GuestWorkspace';
import { GuestWorkspace } from '../../features/guest/GuestWorkspace';
import '../../features/guest/guest.css';
import '../../layouts/PublicLayout.css';

export type AssistantFollowUpContext = {
  validationRunId: string;
  documentIds: string[];
};

export function LandingPage() {
  const [mode, setMode] = useState<GuestWorkspaceMode | null>(null);
  const [assistantContext, setAssistantContext] = useState<AssistantFollowUpContext | undefined>();

  return (
    <div className="landing">
      <section className="landing__hero landing__hero--compact">
        <div>
          <p className="landing__eyebrow">Payroll compliance for Israeli employers</p>
          <h1>Validate payslips. Answer employee-rights questions with approved sources.</h1>
          <p className="landing__hero-lead">
            Payroll Copilot combines deterministic payroll validation with a source-bound assistant.
            Compliance decisions are made by the rule engine, not by AI guesswork.
          </p>
        </div>
      </section>

      <section className="guest-action-cards" aria-label="Primary actions">
        <button
          type="button"
          className={`guest-action-card ${mode === 'assistant' ? 'is-active' : ''}`}
          onClick={() => setMode('assistant')}
        >
          <h2>Payroll Assistant</h2>
          <p>Ask about payroll rules and employee rights using approved internal sources only.</p>
        </button>
        <button
          type="button"
          className={`guest-action-card ${mode === 'validate' ? 'is-active' : ''}`}
          onClick={() => setMode('validate')}
        >
          <h2>Validate My Payslip</h2>
          <p>Upload a payslip and optional supporting documents to receive a structured validation report.</p>
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
