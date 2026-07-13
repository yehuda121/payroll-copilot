import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useAppLocale } from '../../../hooks/useAppLocale';
import { assistantService } from '../../../services/assistant';
import { AssistantMarkdown } from '../../../components/guest/AssistantMarkdown';

type FindingExplainPanelProps = {
  findingId: string;
  ruleId: string;
  validationRunId: string;
  documentIds: string[];
  autoLoad?: boolean;
};

export function FindingExplainPanel({
  findingId,
  ruleId,
  validationRunId,
  documentIds,
  autoLoad = false,
}: FindingExplainPanelProps) {
  const { t } = useTranslation();
  const { locale } = useAppLocale();
  const [isLoading, setIsLoading] = useState(false);
  const [explanation, setExplanation] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadExplanation = async () => {
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
        locale,
      });
      setExplanation(response.answer);
    } catch {
      setError(t('report.explainFailed'));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (autoLoad) {
      void loadExplanation();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoLoad, findingId]);

  return (
    <div className="finding-explain">
      {!autoLoad && (
        <button type="button" className="btn btn--ghost" onClick={() => void loadExplanation()}>
          {t('report.explain')}
        </button>
      )}
      <div className="finding-explain__panel" aria-live="polite">
        <p className="finding-explain__note">{t('report.explainNote')}</p>
        {isLoading && <p>{t('report.explainPreparing')}</p>}
        {error && <p className="finding-explain__error">{error}</p>}
        {explanation && <AssistantMarkdown content={explanation} />}
      </div>
    </div>
  );
}
