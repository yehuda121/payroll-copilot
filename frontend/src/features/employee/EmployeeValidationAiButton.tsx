import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ModalDialog } from '../../components/ui/Dialog';
import { useAppLocale } from '../../hooks/useAppLocale';
import { useEmployeeWorkspace } from './EmployeeWorkspaceContext';
import '../guest/landing/landing-chat.css';

type EmployeeValidationAiButtonProps = {
  cardTitle: string;
  /** Validation finding id — enables server AI explain endpoint. */
  findingId?: string | null;
  validationRunId?: string | null;
  /** Deterministic static explanation when no finding AI is available. */
  staticExplanation?: string | null;
};

/**
 * Reuses employeePortalService.explainFinding (existing employee AI explain API).
 * Falls back to a static explanation panel for identity/period cards.
 */
export function EmployeeValidationAiButton({
  cardTitle,
  findingId,
  validationRunId,
  staticExplanation,
}: EmployeeValidationAiButtonProps) {
  const { t } = useTranslation();
  const { locale } = useAppLocale();
  const { api: workspaceApi } = useEmployeeWorkspace();
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [explanation, setExplanation] = useState<string | null>(null);
  const [recommendation, setRecommendation] = useState<string | null>(null);

  const canCallApi = Boolean(findingId && validationRunId);
  const canShowStatic = Boolean(staticExplanation?.trim());
  if (!canCallApi && !canShowStatic) return null;

  const onOpen = async () => {
    setOpen(true);
    setError(null);
    if (!canCallApi) {
      setExplanation(staticExplanation ?? null);
      setRecommendation(null);
      return;
    }
    if (explanation) return;
    setLoading(true);
    try {
      const result = await workspaceApi.explainFinding(
        validationRunId!,
        findingId!,
        locale,
      );
      if (result.explanation_status === 'not_applicable' && !result.explanation) {
        setExplanation(staticExplanation || t('employee.validation.aiUnavailable'));
        setRecommendation(result.recommended_action);
      } else if (result.explanation_status === 'ai_unavailable' && !result.explanation) {
        setExplanation(staticExplanation || t('employee.validation.aiUnavailable'));
        setRecommendation(result.recommended_action);
      } else {
        setExplanation(result.explanation || staticExplanation || t('employee.validation.aiUnavailable'));
        setRecommendation(result.recommended_action);
      }
    } catch {
      setError(t('employee.validation.aiUnavailable'));
      setExplanation(staticExplanation ?? null);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <button
        type="button"
        className="employee-validation-ai-btn"
        onClick={() => {
          void onOpen();
        }}
        aria-label={t('employee.validation.explainAria', { title: cardTitle })}
      >
        <span aria-hidden="true">💡</span>
        <span>{t('employee.validation.explain')}</span>
      </button>

      {open && (
        <ModalDialog
          title={t('employee.validation.aiExplanation')}
          onClose={() => setOpen(false)}
          footer={
            <button type="button" className="btn btn--secondary" onClick={() => setOpen(false)}>
              {t('common.close')}
            </button>
          }
        >
          <p className="employee-validation-ai-panel__title">{cardTitle}</p>
          <p className="employee-validation-ai-panel__note">
            {t('employee.validation.aiExplanationDisclaimer')}
          </p>
          {loading && <p>{t('report.explainPreparing')}</p>}
          {error && <p className="employee-validation-ai-panel__error">{error}</p>}
          {explanation && <p className="employee-validation-ai-panel__body">{explanation}</p>}
          {recommendation && (
            <p className="employee-validation-ai-panel__rec">
              <strong>{t('common.recommendation')}:</strong> {recommendation}
            </p>
          )}
        </ModalDialog>
      )}
    </>
  );
}
