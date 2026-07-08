import { useCallback, useEffect, useMemo, useState } from 'react';
import { PortalPage } from '../../components/PortalPage';
import { documentLabService } from '../../services/documentLab';
import { authService } from '../../services/auth';
import type {
  DocumentLabFixtureItem,
  DocumentLabPipelineResult,
  DocumentLabRunResult,
} from '../../types/document-lab';
import './document-lab.css';

type OutputPanelProps = {
  title: string;
  value: unknown;
};

function OutputPanel({ title, value }: OutputPanelProps) {
  const text = value === undefined || value === null ? '' : JSON.stringify(value, null, 2);

  const copy = async () => {
    if (!text) return;
    await navigator.clipboard.writeText(text);
  };

  return (
    <section className="document-lab__panel">
      <div className="document-lab__panel-header">
        <h3>{title}</h3>
        <button type="button" className="btn btn--ghost" onClick={() => void copy()} disabled={!text}>
          Copy
        </button>
      </div>
      <pre className="document-lab__pre">{text || 'No output yet.'}</pre>
    </section>
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
  return (
    <section className="document-lab__fixture-group">
      <h3>{title}</h3>
      {items.length === 0 ? <p className="document-lab__muted">No fixtures found.</p> : null}
      <ul className="document-lab__fixture-list">
        {items.map((item) => (
          <li key={item.id}>
            <button
              type="button"
              className={`document-lab__fixture ${selectedId === item.id ? 'is-selected' : ''}`}
              onClick={() => onSelect(item.id)}
            >
              <strong>{item.filename}</strong>
              <span>{Math.round(item.size_bytes / 1024)} KB · {item.media_type}</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function DocumentLabPage() {
  const [fixtures, setFixtures] = useState<{ valid: DocumentLabFixtureItem[]; invalid: DocumentLabFixtureItem[] }>(
    { valid: [], invalid: [] },
  );
  const [selectedFixtureId, setSelectedFixtureId] = useState<string | null>(null);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [language, setLanguage] = useState('auto');
  const [locale, setLocale] = useState<'he' | 'en' | 'ar'>('en');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<DocumentLabRunResult | DocumentLabPipelineResult | null>(null);

  const inputLabel = useMemo(() => {
    if (uploadFile) return `Upload: ${uploadFile.name}`;
    if (selectedFixtureId) return `Fixture: ${selectedFixtureId}`;
    return 'Select a fixture or upload a file';
  }, [selectedFixtureId, uploadFile]);

  useEffect(() => {
    void documentLabService
      .listFixtures()
      .then((response) => setFixtures({ valid: response.valid, invalid: response.invalid }))
      .catch((err: Error) => setError(err.message));
  }, []);

  const resolveInput = useCallback(() => {
    if (uploadFile) {
      return { file: uploadFile };
    }
    if (selectedFixtureId) {
      return { fixtureId: selectedFixtureId };
    }
    throw new Error('Select a fixture or upload a file first.');
  }, [selectedFixtureId, uploadFile]);

  const run = useCallback(
    async (action: 'ocr' | 'parser' | 'ocr-parser' | 'pipeline') => {
      setLoading(true);
      setError(null);
      try {
        const input = resolveInput();
        if (action === 'ocr') {
          const response = await documentLabService.runOcr({ ...input, language });
          setResult(response);
          return;
        }
        if (action === 'parser') {
          const current = result?.ocr;
          if (!current) {
            throw new Error('Run OCR first or use OCR → Parser.');
          }
          const response = await documentLabService.runParser(current as Record<string, unknown>);
          setResult((prev) => ({ ...(prev ?? {}), ...response }));
          return;
        }
        if (action === 'ocr-parser') {
          const response = await documentLabService.runOcrParser({ ...input, language });
          setResult(response);
          return;
        }
        await authService.createGuestSession();
        const response = await documentLabService.runPipeline({
          ...input,
          language,
          locale,
          includeExplanation: true,
        });
        setResult(response);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Document Lab request failed.');
      } finally {
        setLoading(false);
      }
    },
    [language, locale, resolveInput, result?.ocr],
  );

  return (
    <PortalPage
      title="Document Lab"
      description="Developer-only manual debugger for OCR, parser, validation, and AI explanation. Uses real services — no mocked outputs."
    >
      <div className="document-lab">
        <p className="document-lab__notice">
          Developer tool only. Not exposed on the public guest flow. Current input: {inputLabel}
        </p>

        {error && <p className="document-lab__error">{error}</p>}

        <div className="document-lab__layout">
          <div className="document-lab__sidebar">
            <FixtureGroup
              title="Valid fixtures"
              items={fixtures.valid}
              selectedId={selectedFixtureId}
              onSelect={(id) => {
                setSelectedFixtureId(id);
                setUploadFile(null);
              }}
            />
            <FixtureGroup
              title="Invalid fixtures"
              items={fixtures.invalid}
              selectedId={selectedFixtureId}
              onSelect={(id) => {
                setSelectedFixtureId(id);
                setUploadFile(null);
              }}
            />

            <section className="document-lab__upload">
              <h3>Temporary upload</h3>
              <input
                type="file"
                accept=".pdf,.png,.jpg,.jpeg"
                onChange={(event) => {
                  const file = event.target.files?.[0] ?? null;
                  setUploadFile(file);
                  if (file) setSelectedFixtureId(null);
                }}
              />
            </section>

            <section className="document-lab__controls">
              <label>
                OCR language
                <select value={language} onChange={(event) => setLanguage(event.target.value)}>
                  <option value="auto">auto</option>
                  <option value="he">he</option>
                  <option value="en">en</option>
                  <option value="ar">ar</option>
                </select>
              </label>
              <label>
                Validation locale
                <select value={locale} onChange={(event) => setLocale(event.target.value as 'he' | 'en' | 'ar')}>
                  <option value="en">en</option>
                  <option value="he">he</option>
                  <option value="ar">ar</option>
                </select>
              </label>
            </section>

            <div className="document-lab__actions">
              <button type="button" className="btn btn--secondary" disabled={loading} onClick={() => void run('ocr')}>
                Run OCR
              </button>
              <button type="button" className="btn btn--secondary" disabled={loading} onClick={() => void run('parser')}>
                Run Parser
              </button>
              <button
                type="button"
                className="btn btn--secondary"
                disabled={loading}
                onClick={() => void run('ocr-parser')}
              >
                Run OCR → Parser
              </button>
              <button type="button" className="btn btn--primary" disabled={loading} onClick={() => void run('pipeline')}>
                Run OCR → Parser → Validation
              </button>
            </div>
            {loading && <p className="document-lab__muted">Running… this may take a while for OCR/LLM.</p>}
          </div>

          <div className="document-lab__outputs">
            <OutputPanel title="OCR" value={result?.ocr} />
            <OutputPanel title="Parser fields" value={result?.parser} />
            <OutputPanel title="ValidationContext summary" value={result?.validation_context_summary} />
            <OutputPanel title="Extraction (pipeline)" value={(result as DocumentLabPipelineResult | null)?.extraction} />
            <OutputPanel title="Validation (pipeline)" value={(result as DocumentLabPipelineResult | null)?.validation} />
            <OutputPanel
              title="AI explanation (pipeline)"
              value={(result as DocumentLabPipelineResult | null)?.ai_explanation}
            />
            {result?.ocr?.raw_text ? (
              <section className="document-lab__panel">
                <div className="document-lab__panel-header">
                  <h3>OCR raw text</h3>
                  <button
                    type="button"
                    className="btn btn--ghost"
                    onClick={() => void navigator.clipboard.writeText(result.ocr?.raw_text ?? '')}
                  >
                    Copy
                  </button>
                </div>
                <pre className="document-lab__pre document-lab__pre--text">{result.ocr.raw_text}</pre>
              </section>
            ) : null}
          </div>
        </div>
      </div>
    </PortalPage>
  );
}
