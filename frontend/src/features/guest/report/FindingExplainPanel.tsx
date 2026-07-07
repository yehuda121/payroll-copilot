import { useState } from 'react';
import { assistantService } from '../../../services/assistant';

type FindingExplainPanelProps = {
  findingId: string;
  ruleId: string;
  validationRunId: string;
  documentIds: string[];
};

export function FindingExplainPanel({
  findingId,
  ruleId,
  validationRunId,
  documentIds,
}: FindingExplainPanelProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [explanation, setExplanation] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleExplain = async () => {
    setIsOpen(true);
    if (explanation || isLoading) {
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const response = await assistantService.chat({
        message: `Explain the existing validation finding with rule_id ${ruleId}. Do not create new findings.`,
        validation_run_id: validationRunId,
        document_ids: documentIds,
        locale: 'en',
      });
      setExplanation(response.answer);
    } catch {
      setError('An explanation could not be generated for this finding.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="finding-explain">
      <button type="button" className="btn btn--ghost" onClick={handleExplain}>
        Explain
      </button>
      {isOpen && (
        <div className="finding-explain__panel" aria-live="polite">
          <p className="finding-explain__note">
            Explanation based on existing deterministic findings only.
          </p>
          {isLoading && <p>Preparing explanation…</p>}
          {error && <p className="finding-explain__error">{error}</p>}
          {explanation && <p>{explanation}</p>}
          <p className="finding-explain__meta">Finding ID: {findingId}</p>
        </div>
      )}
    </div>
  );
}
