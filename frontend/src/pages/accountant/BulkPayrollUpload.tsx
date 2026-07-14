import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { PortalPage } from '../../components/PortalPage';
import { Card } from '../../components/ui/Card';
import { ProgressDialog, useConfirmDialog } from '../../components/ui/Dialog';
import { UploadPanel } from '../../components/ui/UploadPanel';
import { useBatchNavigationGuard } from '../../features/accountant/BatchNavigationGuard';
import { getAccountantErrorMessage } from '../../i18n/accountantLabels';
import { batchService } from '../../services/batch';
import { employeesService } from '../../services/employees';

export function BulkPayrollUploadPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { confirm } = useConfirmDialog();
  const { setBatchActive, setBatchLabel } = useBatchNavigationGuard();
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [matchId, setMatchId] = useState('');
  const [matchResult, setMatchResult] = useState<string | null>(null);

  const startUpload = async () => {
    if (!file) {
      setError(t('accountant.batches.selectPdf'));
      return;
    }
    const ok = await confirm({
      title: t('accountant.batches.startTitle'),
      message: t('accountant.batches.startMessage'),
      confirmLabel: t('accountant.batches.startConfirm'),
      cancelLabel: t('common.cancel'),
      variant: 'warning',
    });
    if (!ok) return;

    setUploading(true);
    setError(null);
    setBatchActive(true);
    setBatchLabel(t('accountant.batches.batchActiveLabel'));
    try {
      const result = await batchService.uploadBulkPdf(file);
      navigate(`/accountant/batch-monitor?job=${result.batch_job_id}`);
    } catch {
      setBatchActive(false);
      setError(getAccountantErrorMessage('uploadFailed', t));
    } finally {
      setUploading(false);
    }
  };

  const runMatch = async () => {
    setMatchResult(null);
    if (!matchId.trim()) return;
    try {
      const result = await employeesService.matchNationalId(matchId.trim());
      if (result.matched && result.employee) {
        setMatchResult(
          t('accountant.batches.matchFound', {
            number: result.employee.employeeNumber,
            name: result.employee.fullName,
          }),
        );
      } else {
        const create = await confirm({
          title: t('accountant.batches.matchNotFoundTitle'),
          message: t('accountant.batches.matchNotFoundMessage'),
          confirmLabel: t('accountant.batches.matchCreateConfirm'),
          cancelLabel: t('accountant.batches.matchKeepUnmatched'),
          variant: 'warning',
        });
        setMatchResult(
          create
            ? t('accountant.batches.matchCreateHint')
            : t('accountant.batches.matchUnmatchedHint'),
        );
        if (create) navigate('/accountant/employees/add');
      }
    } catch {
      setError(getAccountantErrorMessage('matchFailed', t));
    }
  };

  return (
    <PortalPage
      title={t('accountant.batches.uploadTitle')}
      description={t('accountant.batches.uploadDescription')}
    >
      {uploading && (
        <ProgressDialog
          title={t('accountant.batches.uploadingTitle')}
          message={t('accountant.batches.uploadingMessage')}
          progressPercent={35}
          indeterminate={false}
        />
      )}
      <Card title={t('accountant.batches.uploadCardTitle')}>
        <UploadPanel
          slots={[
            {
              id: 'bulk_pdf',
              label: t('accountant.batches.uploadSlotLabel'),
              accept: '.pdf,application/pdf',
            },
          ]}
          selectedFileName={file?.name}
          errorMessage={error ?? undefined}
          onFilesSelected={(_slot, selected) => {
            setFile(selected);
            setError(null);
          }}
          onRemove={() => setFile(null)}
        />
        <div className="form-actions">
          <button type="button" className="btn btn--primary" onClick={() => void startUpload()}>
            {t('accountant.batches.startProcessing')}
          </button>
          <Link to="/accountant/batch-monitor" className="btn btn--secondary">
            {t('accountant.batches.openMonitor')}
          </Link>
        </div>
      </Card>

      <Card title={t('accountant.batches.matchTitle')}>
        <p className="guest-section__intro">{t('accountant.batches.matchIntro')}</p>
        <div className="accountant-toolbar__filters">
          <input
            type="text"
            placeholder={t('accountant.batches.matchPlaceholder')}
            value={matchId}
            onChange={(e) => setMatchId(e.target.value)}
            aria-label={t('accountant.batches.matchAria')}
          />
          <button type="button" className="btn btn--secondary" onClick={() => void runMatch()}>
            {t('accountant.batches.matchButton')}
          </button>
        </div>
        {matchResult && <p className="match-result">{matchResult}</p>}
      </Card>
    </PortalPage>
  );
}
