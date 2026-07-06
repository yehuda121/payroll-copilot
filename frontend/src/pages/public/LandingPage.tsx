import { GuestChatPanel } from '../../components/guest/GuestChatPanel';
import { GuestUploadArea } from '../../components/guest/GuestUploadArea';
import '../../layouts/PublicLayout.css';

export function LandingPage() {
  return (
    <div className="landing">
      <section className="landing__hero">
        <div>
          <h1>AI-Powered Payroll Compliance</h1>
          <p className="landing__hero-lead">
            Payroll Copilot helps organizations validate payslips against Israeli labor law,
            company policies, and employment contracts — before salaries are paid.
          </p>
          <div className="landing__principles">
            <div className="landing__principle">
              <strong>Deterministic validation</strong> — Rule engine decides compliance; AI never
              overrides pass/fail.
            </div>
            <div className="landing__principle">
              <strong>Extensible rule packs</strong> — Legal, department, and contract rules without
              hardcoded frontend logic.
            </div>
            <div className="landing__principle">
              <strong>AI assistance</strong> — OCR, document understanding, RAG, and explanations
              support human review.
            </div>
          </div>
        </div>
        <div className="landing__hero-visual">
          <h2>Built for payroll accountants & employees</h2>
          <p>
            Bulk-process hundreds of payslips, surface validation findings with confidence scores,
            and give employees transparent explanations of their payroll data.
          </p>
        </div>
      </section>
      <section className="landing__sections">
        <GuestUploadArea />
        <GuestChatPanel />
      </section>
    </div>
  );
}
