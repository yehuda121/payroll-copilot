import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { PortalPage } from '../../components/PortalPage';
import { ModalDialog, useConfirmDialog } from '../../components/ui/Dialog';
import { mapPresentationStatus } from '../../lib/employee/presentation-status';
import { ApiClientError } from '../../services/api';
import {
  employeePortalService,
  type PayrollMonthDetail,
  type PayrollMonthsResponse,
  type PayrollMonthSummary,
} from '../../services/employeePortal';
import { useAppLocale } from '../../hooks/useAppLocale';
import './MyPayslips.css';

type UploadResult = {
  name: string;
  ok: boolean;
  message: string;
};

function monthLabel(month: number, locale: string): string {
  return new Intl.DateTimeFormat(locale, { month: 'long' }).format(new Date(2020, month - 1, 1));
}

function StatusBadge({ code }: { code: string }) {
  const { t } = useTranslation();
  const visual = mapPresentationStatus(code);
  return (
    <span className={`employee-status-badge ${visual.cssClass}`} title={t(visual.labelKey)}>
      <span className="employee-status-badge__icon" aria-hidden="true">
        {visual.icon}
      </span>
      <span>{t(visual.labelKey)}</span>
    </span>
  );
}

export function MyPayslipsPage() {
  const { t } = useTranslation();
  const { locale } = useAppLocale();
  const { confirm } = useConfirmDialog();
  const currentYear = new Date().getFullYear();

  const [year, setYear] = useState(currentYear);
  const [data, setData] = useState<PayrollMonthsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedMonth, setSelectedMonth] = useState<number | null>(null);
  const [detail, setDetail] = useState<PayrollMonthDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [uploadResults, setUploadResults] = useState<UploadResult[]>([]);
  const [busy, setBusy] = useState(false);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [explanationByFinding, setExplanationByFinding] = useState<
    Record<string, { text: string; status: string }>
  >({});
  const [explainingId, setExplainingId] = useState<string | null>(null);

  const years = useMemo(() => {
    const fromApi = data?.available_years ?? [];
    return Array.from(new Set([...fromApi, currentYear, year])).sort((a, b) => b - a);
  }, [data, currentYear, year]);

  const loadYear = async (nextYear: number) => {
    setLoading(true);
    setError(null);
    try {
      const response = await employeePortalService.listPayrollMonths(nextYear);
      setData(response);
      setYear(response.year);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('common.error'));
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadYear(year);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- initial + explicit retry
  }, []);

  const openMonth = async (month: number) => {
    setSelectedMonth(month);
    setDetail(null);
    setDetailError(null);
    setUploadResults([]);
    setDetailLoading(true);
    try {
      const row = await employeePortalService.getPayrollMonthDetail(year, month);
      setDetail(row);
      setSelectedRunId(row.latest_validation.validation_run_id);
      setExplanationByFinding({});
    } catch (err) {
      setDetailError(err instanceof Error ? err.message : t('common.error'));
    } finally {
      setDetailLoading(false);
    }
  };

  const refreshOpenMonth = async () => {
    if (selectedMonth == null) return;
    await loadYear(year);
    await openMonth(selectedMonth);
  };

  const onPickFiles = async (
    files: FileList | null,
    documentType: 'payslip' | 'attendance',
  ) => {
    if (!files || files.length === 0 || selectedMonth == null) return;
    setBusy(true);
    const results: UploadResult[] = [];
    for (const file of Array.from(files)) {
      try {
        if (documentType === 'payslip') {
          try {
            await employeePortalService.extractPayslip(file, {
              periodYear: year,
              periodMonth: selectedMonth,
              confirmNewVersion: false,
            });
            results.push({ name: file.name, ok: true, message: t('employee.payslips.uploadSuccess') });
          } catch (err) {
            if (err instanceof ApiClientError && err.code === 'duplicate_payslip_period') {
              const ok = await confirm({
                title: t('employee.payslips.duplicateTitle'),
                message: t('employee.payslips.duplicateMessage'),
                confirmLabel: t('employee.payslips.confirmNewVersion'),
                cancelLabel: t('common.cancel'),
                variant: 'warning',
              });
              if (!ok) {
                results.push({
                  name: file.name,
                  ok: false,
                  message: t('employee.payslips.duplicateCancelled'),
                });
                continue;
              }
              await employeePortalService.extractPayslip(file, {
                periodYear: year,
                periodMonth: selectedMonth,
                confirmNewVersion: true,
              });
              results.push({
                name: file.name,
                ok: true,
                message: t('employee.payslips.uploadVersionSuccess'),
              });
            } else {
              throw err;
            }
          }
        } else {
          await employeePortalService.uploadOwnedDocument(file, {
            documentType: 'attendance',
            periodYear: year,
            periodMonth: selectedMonth,
          });
          results.push({ name: file.name, ok: true, message: t('employee.payslips.uploadSuccess') });
        }
      } catch (err) {
        results.push({
          name: file.name,
          ok: false,
          message: err instanceof Error ? err.message : t('common.error'),
        });
      }
    }
    setUploadResults(results);
    setBusy(false);
    await refreshOpenMonth();
  };

  const runValidation = async () => {
    if (!detail?.payslip.document_id) return;
    if (!detail.actions.can_run_validation) {
      setDetailError(t('employee.upload.confirmBeforeValidate'));
      return;
    }
    setBusy(true);
    setDetailError(null);
    try {
      await employeePortalService.validatePayslip({
        documentId: detail.payslip.document_id,
        locale,
        supportingDocumentIds: detail.attendance.document_id
          ? [detail.attendance.document_id]
          : [],
      });
      await refreshOpenMonth();
    } catch (err) {
      if (err instanceof ApiClientError) {
        setDetailError(
          t(`employee.upload.errors.${err.code}`, {
            defaultValue: err.message,
          }),
        );
      } else {
        setDetailError(err instanceof Error ? err.message : t('common.error'));
      }
    } finally {
      setBusy(false);
    }
  };

  const confirmFromMonth = async () => {
    if (!detail?.payslip.document_id) return;
    const ok = await confirm({
      title: t('employee.upload.confirmExtraction'),
      message: t('employee.upload.confirmAcknowledgement'),
      confirmLabel: t('employee.upload.confirmExtraction'),
      cancelLabel: t('common.cancel'),
    });
    if (!ok) return;
    setBusy(true);
    setDetailError(null);
    try {
      await employeePortalService.confirmExtraction(detail.payslip.document_id, true);
      await refreshOpenMonth();
    } catch (err) {
      if (err instanceof ApiClientError) {
        setDetailError(
          t(`employee.upload.errors.${err.code}`, { defaultValue: err.message }),
        );
      } else {
        setDetailError(err instanceof Error ? err.message : t('common.error'));
      }
    } finally {
      setBusy(false);
    }
  };

  const explainFinding = async (findingId: string) => {
    const runId =
      selectedRunId || detail?.latest_validation.validation_run_id || null;
    if (!runId) return;
    setExplainingId(findingId);
    try {
      const result = await employeePortalService.explainFinding(runId, findingId, locale);
      setExplanationByFinding((prev) => ({
        ...prev,
        [findingId]: {
          text: result.explanation || t('employee.validation.aiUnavailable'),
          status: result.explanation_status,
        },
      }));
    } catch (err) {
      setExplanationByFinding((prev) => ({
        ...prev,
        [findingId]: {
          text: err instanceof Error ? err.message : t('employee.validation.aiUnavailable'),
          status: 'ai_unavailable',
        },
      }));
    } finally {
      setExplainingId(null);
    }
  };

  const activeFindings = detail?.latest_validation.findings || [];
  const history = detail?.validation_history || [];

  return (
    <PortalPage
      title={t('employee.payslips.pageTitle')}
      description={t('employee.payslips.pageDescription')}
    >
      <div className="employee-payslips">
        <div className="employee-payslips__toolbar">
          <label className="employee-payslips__year">
            <span>{t('employee.payslips.yearLabel')}</span>
            <select
              value={year}
              aria-label={t('employee.payslips.yearLabel')}
              onChange={(event) => {
                const next = Number(event.target.value);
                setYear(next);
                void loadYear(next);
              }}
            >
              {years.map((y) => (
                <option key={y} value={y}>
                  {y}
                </option>
              ))}
            </select>
          </label>
          <ul className="employee-payslips__legend" aria-label={t('employee.payslips.legendTitle')}>
            {(['passed', 'error', 'warning', 'unavailable'] as const).map((key) => {
              const visual = mapPresentationStatus(key === 'passed' ? 'passed' : key);
              return (
                <li key={key} className={`employee-status-badge ${visual.cssClass}`}>
                  <span aria-hidden="true">{visual.icon}</span>
                  <span>{t(visual.labelKey)}</span>
                </li>
              );
            })}
          </ul>
        </div>

        {loading && (
          <div className="employee-payslips__skeleton" aria-busy="true">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="employee-month-card employee-month-card--skeleton" />
            ))}
          </div>
        )}

        {error && (
          <div className="employee-payslips__error" role="alert">
            <p>{error}</p>
            <button type="button" className="btn btn--secondary" onClick={() => void loadYear(year)}>
              {t('common.retry')}
            </button>
          </div>
        )}

        {!loading && !error && data && (
          <div className="employee-payslips__grid" role="list">
            {data.months.map((month: PayrollMonthSummary) => (
              <button
                key={month.month}
                type="button"
                role="listitem"
                className="employee-month-card"
                onClick={() => void openMonth(month.month)}
              >
                <div className="employee-month-card__head">
                  <strong>{monthLabel(month.month, locale)}</strong>
                  <StatusBadge code={month.presentation_status} />
                </div>
                <ul className="employee-month-card__meta">
                  <li>
                    {t('employee.payslips.payslip')}:{' '}
                    {month.payslip.exists
                      ? t('employee.payslips.docPresent')
                      : t('employee.payslips.docMissing')}
                  </li>
                  <li>
                    {t('employee.payslips.attendance')}:{' '}
                    {month.attendance.exists
                      ? t('employee.payslips.docPresent')
                      : t('employee.payslips.docMissing')}
                  </li>
                  <li>
                    {t('employee.payslips.validation')}:{' '}
                    {month.latest_validation.exists
                      ? t('employee.payslips.validationPresent')
                      : t('employee.payslips.validationMissing')}
                  </li>
                  {month.latest_validation.completed_at && (
                    <li>
                      {t('employee.payslips.lastValidated')}:{' '}
                      {new Date(month.latest_validation.completed_at).toLocaleString(locale)}
                    </li>
                  )}
                </ul>
              </button>
            ))}
          </div>
        )}
      </div>

      {selectedMonth != null && (
        <ModalDialog
          wide
          title={`${monthLabel(selectedMonth, locale)} ${year}`}
          onClose={() => {
            setSelectedMonth(null);
            setDetail(null);
          }}
        >
          {detailLoading && <p>{t('common.loading')}</p>}
          {detailError && <p className="chat-panel__error">{detailError}</p>}
          {detail && (
            <div className="employee-month-detail">
              <StatusBadge code={detail.presentation_status} />

              <section>
                <h3>{t('employee.payslips.payslip')}</h3>
                {detail.payslip.exists ? (
                  <ul>
                    <li>{detail.payslip.original_filename}</li>
                    <li>
                      {t('employee.payslips.uploadedAt')}:{' '}
                      {detail.payslip.uploaded_at
                        ? new Date(detail.payslip.uploaded_at).toLocaleString(locale)
                        : t('common.emDash')}
                    </li>
                    <li>
                      {t('employee.payslips.docStatus')}: {detail.payslip.status}
                    </li>
                  </ul>
                ) : (
                  <p>{t('employee.payslips.payslipMissing')}</p>
                )}
              </section>

              <section>
                <h3>{t('employee.payslips.reviewTitle')}</h3>
                {detail.extraction?.exists ? (
                  <ul>
                    <li>
                      {t('employee.documents.confirmationStatus')}:{' '}
                      {t(`employee.lifecycle.${detail.extraction.confirmation_status}`, {
                        defaultValue: detail.extraction.confirmation_status,
                      })}
                    </li>
                    <li>
                      {t('employee.payslips.extractionVersion')}:{' '}
                      {detail.extraction.extraction_version ?? t('common.emDash')}
                    </li>
                    <li>
                      {t('employee.documents.lifecycleStatus')}:{' '}
                      {t(`employee.lifecycle.${detail.extraction.lifecycle_status}`, {
                        defaultValue: detail.extraction.lifecycle_status,
                      })}
                    </li>
                  </ul>
                ) : (
                  <p>{t('employee.payslips.reviewMissing')}</p>
                )}
                {detail.actions.can_confirm_extraction && (
                  <button
                    type="button"
                    className="btn btn--secondary"
                    disabled={busy}
                    onClick={() => void confirmFromMonth()}
                  >
                    {t('employee.upload.confirmExtraction')}
                  </button>
                )}
                <p>
                  <Link className="btn btn--ghost" to="/employee/upload">
                    {t('employee.payslips.continueReview')}
                  </Link>
                </p>
              </section>

              <section>
                <h3>{t('employee.payslips.attendance')}</h3>
                {detail.attendance.exists ? (
                  <>
                    <ul>
                      <li>{detail.attendance.original_filename}</li>
                      <li>
                        {t('employee.payslips.uploadedAt')}:{' '}
                        {detail.attendance.uploaded_at
                          ? new Date(detail.attendance.uploaded_at).toLocaleString(locale)
                          : t('common.emDash')}
                      </li>
                    </ul>
                    {detail.attendance.analysis_status === 'not_connected' && (
                      <p className="employee-month-detail__note">
                        {t('employee.payslips.attendanceNotConnected')}
                      </p>
                    )}
                  </>
                ) : (
                  <p>{t('employee.payslips.attendanceMissing')}</p>
                )}
              </section>

              <section>
                <h3>{t('employee.payslips.validation')}</h3>
                {history.length > 0 && (
                  <label className="employee-payslips__year">
                    <span>{t('employee.payslips.validationHistory')}</span>
                    <select
                      value={selectedRunId || ''}
                      aria-label={t('employee.payslips.validationHistory')}
                      onChange={(event) => setSelectedRunId(event.target.value || null)}
                    >
                      {history.map((run) => (
                        <option key={run.validation_run_id} value={run.validation_run_id}>
                          {(run.completed_at
                            ? new Date(run.completed_at).toLocaleString(locale)
                            : run.validation_run_id) +
                            (run.outdated ? ` (${t('employee.payslips.outdated')})` : '')}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
                {detail.latest_validation.exists ? (
                  <ul>
                    {detail.latest_validation.outdated && (
                      <li role="status">{t('employee.payslips.outdatedResult')}</li>
                    )}
                    <li>
                      {t('employee.payslips.docStatus')}:{' '}
                      {detail.latest_validation.overall_result ||
                        detail.latest_validation.status}
                    </li>
                    <li>
                      {t('employee.payslips.confidence')}:{' '}
                      {detail.latest_validation.confidence != null
                        ? `${Math.round(detail.latest_validation.confidence * 100)}%`
                        : t('common.emDash')}
                    </li>
                    <li>
                      {t('employee.payslips.findingsCount')}:{' '}
                      {detail.latest_validation.findings_count}
                    </li>
                    {activeFindings.map((finding) => {
                      const visual = mapPresentationStatus(
                        finding.severity === 'critical'
                          ? 'error'
                          : finding.severity === 'warning'
                            ? 'warning'
                            : finding.severity === 'info'
                              ? 'passed'
                              : 'unavailable',
                      );
                      const showExplain =
                        finding.severity === 'critical' ||
                        finding.severity === 'warning' ||
                        finding.severity === 'info';
                      const explainRelevant =
                        finding.severity === 'critical' || finding.severity === 'warning';
                      return (
                        <li
                          key={finding.id}
                          className={`employee-finding employee-finding--${visual.category}`}
                        >
                          <span aria-hidden="true">{visual.icon}</span>{' '}
                          <strong>{t(visual.labelKey)}</strong> — {finding.message_key}
                          {finding.actual_value != null && (
                            <span>
                              {' '}
                              ({t('employee.payslips.actual')}: {finding.actual_value})
                            </span>
                          )}
                          {explainRelevant && showExplain && (
                            <div className="employee-finding__ai">
                              <button
                                type="button"
                                className="btn btn--ghost"
                                disabled={explainingId === finding.id}
                                onClick={() => void explainFinding(finding.id)}
                              >
                                {t('employee.validation.explain')}
                              </button>
                              {explanationByFinding[finding.id] && (
                                <div className="employee-finding__ai-panel">
                                  <p className="employee-finding__ai-label">
                                    {t('employee.validation.aiExplanation')}
                                  </p>
                                  <p>{explanationByFinding[finding.id].text}</p>
                                  <p className="employee-finding__ai-disclaimer">
                                    {t('employee.validation.aiExplanationDisclaimer')}
                                  </p>
                                </div>
                              )}
                            </div>
                          )}
                        </li>
                      );
                    })}
                    {(detail.latest_validation.scope || []).map((scope) => (
                      <li key={scope.key}>
                        {scope.label}: {scope.status}
                        {scope.reason ? ` (${scope.reason})` : ''}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p>{t('employee.payslips.validationMissing')}</p>
                )}
              </section>

              <section>
                <h3>{t('employee.payslips.missingTitle')}</h3>
                {detail.missing_documents.length === 0 ? (
                  <p>{t('employee.payslips.missingNone')}</p>
                ) : (
                  <ul>
                    {detail.missing_documents.map((item) => (
                      <li key={item.document_type}>
                        {t(`employee.payslips.missing.${item.reason_code}`, {
                          defaultValue: item.reason_code,
                        })}
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              <section className="employee-month-detail__actions">
                <h3>{t('employee.payslips.uploadTitle')}</h3>
                <div className="employee-month-detail__upload-row">
                  <label className="btn btn--secondary">
                    {t('employee.payslips.uploadPayslip')}
                    <input
                      type="file"
                      accept=".pdf,.png,.jpg,.jpeg"
                      multiple
                      hidden
                      disabled={busy}
                      onChange={(event) => {
                        void onPickFiles(event.target.files, 'payslip');
                        event.target.value = '';
                      }}
                    />
                  </label>
                  <label className="btn btn--secondary">
                    {t('employee.payslips.uploadAttendance')}
                    <input
                      type="file"
                      accept=".pdf,.png,.jpg,.jpeg,.xlsx,.csv"
                      multiple
                      hidden
                      disabled={busy}
                      onChange={(event) => {
                        void onPickFiles(event.target.files, 'attendance');
                        event.target.value = '';
                      }}
                    />
                  </label>
                  <button
                    type="button"
                    className="btn btn--primary"
                    disabled={busy || !detail.actions.can_run_validation}
                    onClick={() => void runValidation()}
                  >
                    {detail.latest_validation.exists
                      ? t('employee.payslips.rerunValidation')
                      : t('employee.payslips.runValidation')}
                  </button>
                </div>
                {uploadResults.length > 0 && (
                  <ul className="employee-month-detail__upload-results">
                    {uploadResults.map((item) => (
                      <li key={`${item.name}-${item.message}`} className={item.ok ? 'is-ok' : 'is-fail'}>
                        {item.name}: {item.message}
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </div>
          )}
        </ModalDialog>
      )}
    </PortalPage>
  );
}
