import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { PortalPage } from '../../components/PortalPage';
import { ModalDialog } from '../../components/ui/Dialog';
import {
  FormField,
  FormSection,
  FormSelect,
  FormShell,
} from '../../components/ui/form/FormPrimitives';
import { SettingsIcon, UploadIcon } from '../../components/ui/icons';
import { documentLabService } from '../../services/documentLab';
import { authService } from '../../services/auth';
import type {
  DocumentLabFixtureItem,
  DocumentLabPipelineResult,
  DocumentLabRunResult,
} from '../../types/document-lab';
import './document-lab.css';

type PipelineStageId = 'upload' | 'ocr' | 'parser' | 'validation' | 'ai';
type RunAction = 'ocr' | 'parser' | 'ocr-parser' | 'pipeline';
type ResultKey =
  | 'ocr'
  | 'parser'
  | 'validation_context_summary'
  | 'extraction'
  | 'validation'
  | 'ai_explanation'
  | 'ocr_raw_text';

type ResultCardModel = {
  key: ResultKey;
  titleKey: string;
  value: unknown;
  isText?: boolean;
};

const PIPELINE_STAGES: PipelineStageId[] = ['upload', 'ocr', 'parser', 'validation', 'ai'];

function formatJson(value: unknown): string {
  if (value === undefined || value === null) return '';
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function ResultCard({
  title,
  value,
  loading,
  isText = false,
  onClear,
}: {
  title: string;
  value: unknown;
  loading: boolean;
  isText?: boolean;
  onClear: () => void;
}) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(true);
  const [fullscreen, setFullscreen] = useState(false);
  const [copied, setCopied] = useState(false);
  const text = formatJson(value);
  const empty = !text;

  const copy = async () => {
    if (!text) return;
    await navigator.clipboard.writeText(text);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  };

  const body = (
    <>
      {loading ? (
        <p className="document-lab__muted" role="status">
          {t('admin.documentLab.loadingResult')}
        </p>
      ) : empty ? (
        <p className="document-lab__empty" role="status">
          {t('admin.documentLab.emptyResult')}
        </p>
      ) : (
        <pre
          className={`document-lab__pre${isText ? ' document-lab__pre--text' : ' document-lab__pre--json'}`}
        >
          {text}
        </pre>
      )}
    </>
  );

  return (
    <>
      <section className={`document-lab__result-card${expanded ? ' is-expanded' : ''}`}>
        <header className="document-lab__result-card-header">
          <button
            type="button"
            className="document-lab__result-toggle"
            aria-expanded={expanded}
            onClick={() => setExpanded((prev) => !prev)}
          >
            <span className="document-lab__result-chevron" aria-hidden="true">
              {expanded ? '▾' : '▸'}
            </span>
            <h3>{title}</h3>
          </button>
          <div className="document-lab__result-actions">
            <button
              type="button"
              className="btn btn--ghost"
              disabled={empty}
              onClick={() => void copy()}
            >
              {copied ? t('common.copied') : t('common.copy')}
            </button>
            <button
              type="button"
              className="btn btn--ghost"
              disabled={empty}
              onClick={onClear}
            >
              {t('admin.documentLab.clearResult')}
            </button>
            <button
              type="button"
              className="btn btn--ghost"
              disabled={empty}
              onClick={() => setFullscreen(true)}
            >
              {t('admin.documentLab.fullscreen')}
            </button>
          </div>
        </header>
        {expanded ? <div className="document-lab__result-card-body">{body}</div> : null}
      </section>

      {fullscreen ? (
        <ModalDialog
          title={title}
          size="xl"
          onClose={() => setFullscreen(false)}
          footer={
            <>
              <button
                type="button"
                className="btn btn--secondary"
                disabled={empty}
                onClick={() => void copy()}
              >
                {copied ? t('common.copied') : t('common.copy')}
              </button>
              <button type="button" className="btn btn--primary" onClick={() => setFullscreen(false)}>
                {t('common.close')}
              </button>
            </>
          }
        >
          <div className="document-lab__fullscreen-body">{body}</div>
        </ModalDialog>
      ) : null}
    </>
  );
}

function FixtureGroup({
  title,
  items,
  selectedId,
  onSelect,
}: {
  title: string;
  items: DocumentLabFixtureItem[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <section className="document-lab__fixture-group">
      <h4>{title}</h4>
      {items.length === 0 ? (
        <p className="document-lab__muted">{t('admin.documentLab.noFixtures')}</p>
      ) : null}
      <ul className="document-lab__fixture-list">
        {items.map((item) => (
          <li key={item.id}>
            <button
              type="button"
              className={`document-lab__fixture${selectedId === item.id ? ' is-selected' : ''}`}
              onClick={() => onSelect(item.id)}
            >
              <strong>{item.filename}</strong>
              <span>
                {t('admin.documentLab.fixtureMeta', {
                  size: Math.round(item.size_bytes / 1024),
                  type: item.media_type,
                })}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function DocumentLabPage() {
  const { t } = useTranslation();
  const [fixtures, setFixtures] = useState<{
    valid: DocumentLabFixtureItem[];
    invalid: DocumentLabFixtureItem[];
  }>({ valid: [], invalid: [] });
  const [selectedFixtureId, setSelectedFixtureId] = useState<string | null>(null);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [language, setLanguage] = useState('auto');
  const [locale, setLocale] = useState<'he' | 'en' | 'ar'>('en');
  const [loading, setLoading] = useState(false);
  const [activeStage, setActiveStage] = useState<PipelineStageId | null>(null);
  const [lastAction, setLastAction] = useState<RunAction | null>(null);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [elapsedMs, setElapsedMs] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<DocumentLabRunResult | DocumentLabPipelineResult | null>(null);
  const [clearedKeys, setClearedKeys] = useState<Partial<Record<ResultKey, boolean>>>({});

  const inputSummary = useMemo(() => {
    if (uploadFile) {
      return t('admin.documentLab.inputUpload', { name: uploadFile.name });
    }
    if (selectedFixtureId) {
      return t('admin.documentLab.inputFixture', { id: selectedFixtureId });
    }
    return t('admin.documentLab.inputEmpty');
  }, [selectedFixtureId, t, uploadFile]);

  useEffect(() => {
    void documentLabService
      .listFixtures()
      .then((response) => setFixtures({ valid: response.valid, invalid: response.invalid }))
      .catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => {
    if (!loading || startedAt == null) return;
    const timer = window.setInterval(() => {
      setElapsedMs(Date.now() - startedAt);
    }, 200);
    return () => window.clearInterval(timer);
  }, [loading, startedAt]);

  const resolveInput = useCallback(() => {
    if (uploadFile) return { file: uploadFile };
    if (selectedFixtureId) return { fixtureId: selectedFixtureId };
    throw new Error(t('admin.documentLab.errorSelectInput'));
  }, [selectedFixtureId, t, uploadFile]);

  const clearResultKey = (key: ResultKey) => {
    setClearedKeys((prev) => ({ ...prev, [key]: true }));
  };

  const resetAll = () => {
    setResult(null);
    setClearedKeys({});
    setError(null);
    setActiveStage(null);
    setLastAction(null);
    setElapsedMs(null);
    setStartedAt(null);
  };

  const run = useCallback(
    async (action: RunAction) => {
      setLoading(true);
      setError(null);
      setClearedKeys({});
      setLastAction(action);
      const start = Date.now();
      setStartedAt(start);
      setElapsedMs(0);
      try {
        const input = resolveInput();
        setActiveStage('upload');
        if (action === 'ocr') {
          setActiveStage('ocr');
          const response = await documentLabService.runOcr({ ...input, language });
          setResult(response);
          return;
        }
        if (action === 'parser') {
          const current = result?.ocr;
          if (!current) {
            throw new Error(t('admin.documentLab.errorRunOcrFirst'));
          }
          setActiveStage('parser');
          const response = await documentLabService.runParser(current as Record<string, unknown>);
          setResult((prev) => ({ ...(prev ?? {}), ...response }));
          return;
        }
        if (action === 'ocr-parser') {
          setActiveStage('ocr');
          const response = await documentLabService.runOcrParser({ ...input, language });
          setActiveStage('parser');
          setResult(response);
          return;
        }
        setActiveStage('ocr');
        await authService.createGuestSession();
        setActiveStage('parser');
        const response = await documentLabService.runPipeline({
          ...input,
          language,
          locale,
          includeExplanation: true,
        });
        setActiveStage('validation');
        setResult(response);
        setActiveStage('ai');
      } catch (err) {
        setError(err instanceof Error ? err.message : t('admin.documentLab.errorGeneric'));
      } finally {
        setElapsedMs(Date.now() - start);
        setActiveStage(null);
        setLoading(false);
      }
    },
    [language, locale, resolveInput, result?.ocr, t],
  );

  const pipelineResult = result as DocumentLabPipelineResult | null;
  const cards: ResultCardModel[] = [
    { key: 'ocr', titleKey: 'admin.documentLab.results.ocr', value: result?.ocr },
    { key: 'parser', titleKey: 'admin.documentLab.results.parser', value: result?.parser },
    {
      key: 'validation_context_summary',
      titleKey: 'admin.documentLab.results.validationContext',
      value: result?.validation_context_summary,
    },
    {
      key: 'extraction',
      titleKey: 'admin.documentLab.results.extraction',
      value: pipelineResult?.extraction,
    },
    {
      key: 'validation',
      titleKey: 'admin.documentLab.results.validation',
      value: pipelineResult?.validation,
    },
    {
      key: 'ai_explanation',
      titleKey: 'admin.documentLab.results.aiExplanation',
      value: pipelineResult?.ai_explanation,
    },
  ];
  if (result?.ocr?.raw_text) {
    cards.push({
      key: 'ocr_raw_text',
      titleKey: 'admin.documentLab.results.ocrRawText',
      value: result.ocr.raw_text,
      isText: true,
    });
  }

  const stageStatus = (stage: PipelineStageId): 'idle' | 'active' | 'done' => {
    if (activeStage === stage) return 'active';
    if (!lastAction && !result) return 'idle';
    const order = PIPELINE_STAGES.indexOf(stage);
    const activeOrder = activeStage ? PIPELINE_STAGES.indexOf(activeStage) : -1;
    if (loading && activeOrder >= 0 && order < activeOrder) return 'done';
    if (!loading && result) {
      if (stage === 'upload') return 'done';
      if (stage === 'ocr' && result.ocr) return 'done';
      if (stage === 'parser' && result.parser) return 'done';
      if (stage === 'validation' && pipelineResult?.validation) return 'done';
      if (stage === 'ai' && pipelineResult?.ai_explanation) return 'done';
    }
    return 'idle';
  };

  return (
    <PortalPage
      title={t('admin.documentLab.title')}
      description={t('admin.documentLab.description')}
    >
      <div className="document-lab">
        <p className="document-lab__notice">{t('admin.documentLab.notice')}</p>
        {error ? (
          <p className="document-lab__error" role="alert">
            {error}
          </p>
        ) : null}

        <div className="document-lab__layout">
          <aside className="document-lab__sidebar">
            <section className="document-lab__panel-block">
              <header className="document-lab__section-header">
                <h2>{t('admin.documentLab.sections.testInput')}</h2>
                <p>{t('admin.documentLab.sections.testInputDesc')}</p>
              </header>
              <FixtureGroup
                title={t('admin.documentLab.validFixtures')}
                items={fixtures.valid}
                selectedId={selectedFixtureId}
                onSelect={(id) => {
                  setSelectedFixtureId(id);
                  setUploadFile(null);
                }}
              />
              <FixtureGroup
                title={t('admin.documentLab.invalidFixtures')}
                items={fixtures.invalid}
                selectedId={selectedFixtureId}
                onSelect={(id) => {
                  setSelectedFixtureId(id);
                  setUploadFile(null);
                }}
              />
              <FormShell>
                <FormSection
                  title={t('admin.documentLab.uploadTitle')}
                  description={t('admin.documentLab.uploadDesc')}
                  icon={<UploadIcon size={18} />}
                  columns={1}
                >
                  <FormField
                    label={t('admin.documentLab.uploadLabel')}
                    htmlFor="document-lab-upload"
                    span={2}
                  >
                    <input
                      id="document-lab-upload"
                      className="pc-form-control"
                      type="file"
                      accept=".pdf,.png,.jpg,.jpeg"
                      onChange={(event) => {
                        const file = event.target.files?.[0] ?? null;
                        setUploadFile(file);
                        if (file) setSelectedFixtureId(null);
                      }}
                    />
                  </FormField>
                </FormSection>
              </FormShell>
              <div className="document-lab__summary">
                <strong>{t('admin.documentLab.inputSummary')}</strong>
                <span>{inputSummary}</span>
              </div>
            </section>

            <section className="document-lab__panel-block">
              <header className="document-lab__section-header">
                <h2>{t('admin.documentLab.sections.config')}</h2>
                <p>{t('admin.documentLab.sections.configDesc')}</p>
              </header>
              <FormShell>
                <FormSection
                  title={t('admin.documentLab.runOptions')}
                  description={t('admin.documentLab.runOptionsDesc')}
                  icon={<SettingsIcon size={18} />}
                  columns={1}
                >
                  <FormField
                    label={t('admin.documentLab.ocrLanguage')}
                    htmlFor="document-lab-language"
                    span={2}
                  >
                    <FormSelect
                      id="document-lab-language"
                      value={language}
                      onChange={(event) => setLanguage(event.target.value)}
                    >
                      <option value="auto">{t('admin.documentLab.lang.auto')}</option>
                      <option value="he">{t('admin.documentLab.lang.he')}</option>
                      <option value="en">{t('admin.documentLab.lang.en')}</option>
                      <option value="ar">{t('admin.documentLab.lang.ar')}</option>
                    </FormSelect>
                  </FormField>
                  <FormField
                    label={t('admin.documentLab.validationLocale')}
                    htmlFor="document-lab-locale"
                    span={2}
                  >
                    <FormSelect
                      id="document-lab-locale"
                      value={locale}
                      onChange={(event) => setLocale(event.target.value as 'he' | 'en' | 'ar')}
                    >
                      <option value="en">{t('admin.documentLab.lang.en')}</option>
                      <option value="he">{t('admin.documentLab.lang.he')}</option>
                      <option value="ar">{t('admin.documentLab.lang.ar')}</option>
                    </FormSelect>
                  </FormField>
                </FormSection>
              </FormShell>
            </section>

            <section className="document-lab__panel-block">
              <header className="document-lab__section-header">
                <h2>{t('admin.documentLab.sections.execution')}</h2>
                <p>{t('admin.documentLab.sections.executionDesc')}</p>
              </header>

              <ol className="document-lab__pipeline" aria-label={t('admin.documentLab.pipelineLabel')}>
                {PIPELINE_STAGES.map((stage, index) => {
                  const status = stageStatus(stage);
                  return (
                    <li
                      key={stage}
                      className={`document-lab__pipeline-stage is-${status}`}
                      aria-current={status === 'active' ? 'step' : undefined}
                    >
                      <span className="document-lab__pipeline-dot" aria-hidden="true" />
                      <div>
                        <strong>{t(`admin.documentLab.stages.${stage}`)}</strong>
                        <span>{t(`admin.documentLab.stageStatus.${status}`)}</span>
                      </div>
                      {index < PIPELINE_STAGES.length - 1 ? (
                        <span className="document-lab__pipeline-arrow" aria-hidden="true">
                          ↓
                        </span>
                      ) : null}
                    </li>
                  );
                })}
              </ol>

              <div className="document-lab__status-row">
                <span>
                  {loading
                    ? t('admin.documentLab.statusRunning')
                    : result
                      ? t('admin.documentLab.statusReady')
                      : t('admin.documentLab.statusIdle')}
                </span>
                {elapsedMs != null ? (
                  <span>
                    {t('admin.documentLab.elapsed', {
                      seconds: (elapsedMs / 1000).toFixed(1),
                    })}
                  </span>
                ) : null}
              </div>

              <div className="document-lab__actions">
                <button
                  type="button"
                  className="btn btn--primary document-lab__run-primary"
                  disabled={loading}
                  onClick={() => void run('pipeline')}
                >
                  {loading
                    ? t('admin.documentLab.running')
                    : t('admin.documentLab.runPipeline')}
                </button>
                <button
                  type="button"
                  className="btn btn--secondary"
                  disabled={loading}
                  onClick={() => void run('ocr')}
                >
                  {t('admin.documentLab.runOcr')}
                </button>
                <button
                  type="button"
                  className="btn btn--secondary"
                  disabled={loading}
                  onClick={() => void run('parser')}
                >
                  {t('admin.documentLab.runParser')}
                </button>
                <button
                  type="button"
                  className="btn btn--secondary"
                  disabled={loading}
                  onClick={() => void run('ocr-parser')}
                >
                  {t('admin.documentLab.runOcrParser')}
                </button>
                <button
                  type="button"
                  className="btn btn--ghost"
                  disabled={loading || (!result && !error)}
                  onClick={resetAll}
                >
                  {t('admin.documentLab.reset')}
                </button>
              </div>
            </section>
          </aside>

          <section className="document-lab__outputs">
            <header className="document-lab__section-header">
              <h2>{t('admin.documentLab.sections.results')}</h2>
              <p>{t('admin.documentLab.sections.resultsDesc')}</p>
            </header>
            <div className="document-lab__results-grid">
              {cards.map((card) => (
                <ResultCard
                  key={card.key}
                  title={t(card.titleKey)}
                  value={clearedKeys[card.key] ? null : card.value}
                  loading={loading && !card.value}
                  isText={card.isText}
                  onClear={() => clearResultKey(card.key)}
                />
              ))}
            </div>
          </section>
        </div>
      </div>
    </PortalPage>
  );
}
