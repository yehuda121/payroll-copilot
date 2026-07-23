import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type DragEvent,
  type FormEvent,
} from 'react';
import { useTranslation } from 'react-i18next';
import { AssistantMarkdown } from '../../../components/guest/AssistantMarkdown';
import { AssistantUsageFooter } from '../../../components/guest/AssistantUsageFooter';
import { ChatComposer } from '../../../components/guest/ChatComposer';
import { PopularQuestionsPanel } from '../../../components/guest/PopularQuestionsPanel';
import { env } from '../../../config/env';
import { useAppLocale } from '../../../hooks/useAppLocale';
import { useGuestValidationFlow } from '../../../hooks/useGuestValidationFlow';
import {
  GUEST_ACTIVE_DOCUMENT_SLOTS,
  type GuestDocumentSlotId,
} from '../../../lib/guest/document-slots';
import { detectSlotFromFile } from '../../../lib/guest/detectDocumentSlot';
import { assistantService } from '../../../services/assistant';
import type { AssistantGuardrailStatus, ChatMessage } from '../../../types/assistant';
import { ChatDocumentReviewCard } from './ChatDocumentReviewCard';
import { ChatValidationSummaryCard } from './ChatValidationSummaryCard';
import './landing-chat.css';

type LandingMessage = ChatMessage & {
  kind?: 'text' | 'document_review' | 'validation_summary' | 'status';
};

type PendingAttachment = {
  id: string;
  file: File;
  slotId: GuestDocumentSlotId;
};

const ACCEPT =
  'image/*,.pdf,.png,.jpg,.jpeg,.xlsx,.csv,application/pdf,image/png,image/jpeg,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv';

function looksLikeValidationRequest(text: string): boolean {
  const normalized = text.toLowerCase();
  return (
    /payslip|paycheck|salary|validate|correct| overtime|tax|pension/.test(normalized) ||
    /תלוש|שכר|אימות|נכון|מס|פנסיה/.test(text) ||
    /قسيمة|راتب|تحقق|صحيح/.test(text)
  );
}

function looksLikeIdRequest(text: string): boolean {
  const normalized = text.toLowerCase();
  return (
    /\bid\b|national.?id|identity|teudat/.test(normalized) ||
    /תעודת.?זהות|ת\.ז/.test(text) ||
    /هوية|بطاقة/.test(text)
  );
}

function formatTimestamp(iso: string, locale: string): string {
  try {
    return new Intl.DateTimeFormat(locale, { hour: '2-digit', minute: '2-digit' }).format(
      new Date(iso),
    );
  } catch {
    return '';
  }
}

export function GuestLandingChat() {
  const { t, i18n } = useTranslation();
  const { locale } = useAppLocale();
  const flow = useGuestValidationFlow();

  const [message, setMessage] = useState('');
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [messages, setMessages] = useState<LandingMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [documentConfirmed, setDocumentConfirmed] = useState(false);
  const [typedFacts, setTypedFacts] = useState<string[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const [reviewMessageId, setReviewMessageId] = useState<string | null>(null);
  const [reportMessageId, setReportMessageId] = useState<string | null>(null);
  const [pendingAttachments, setPendingAttachments] = useState<PendingAttachment[]>([]);
  const [chatModel, setChatModel] = useState('');
  const [chatModelChoices, setChatModelChoices] = useState<string[]>([]);

  const bottomRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const isLoadingRef = useRef(false);
  const composerBusy = isLoading || flow.isBusy;

  const documentIds = Object.values(flow.slots)
    .map((slot) => slot?.documentId)
    .filter(Boolean) as string[];
  const payslipName = flow.slots.payslip?.file.name ?? null;
  const hasPayslip = Boolean(flow.slots.payslip?.file);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, [messages, isLoading, flow.step, flow.report]);

  useEffect(() => {
    let cancelled = false;
    void assistantService.modelChoices().then((choices) => {
      if (cancelled) return;
      setChatModelChoices(choices.chat);
    }).catch(() => {
      /* allowlist endpoint is optional; defaults remain */
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const pushMessage = useCallback((msg: LandingMessage) => {
    setMessages((prev) => [...prev, msg]);
    return msg.id;
  }, []);

  const guardrailLabel = (status: AssistantGuardrailStatus): string => {
    switch (status) {
      case 'blocked':
      case 'blocked_off_topic':
      case 'blocked_safety':
        return t('assistant.guardrailBlocked');
      case 'limited':
      case 'limited_in_domain':
        return t('assistant.guardrailLimited');
      default:
        return '';
    }
  };

  const askAssistant = useCallback(
    async (text: string) => {
      const hasPrivateIds = documentIds.length > 0 || Boolean(flow.report?.runId);
      const conversation_turns = messages
        .filter(
          (msg) =>
            (msg.kind === 'text' || !msg.kind) &&
            (msg.role === 'user' || msg.role === 'assistant') &&
            msg.content.trim(),
        )
        .slice(-12)
        .map((msg) => ({ role: msg.role, content: msg.content }));

      const response = await assistantService.chat(
        {
          message: text,
          session_id: sessionId,
          document_ids: documentIds,
          validation_run_id: flow.report?.runId,
          conversation_turns,
          locale,
          model_provider_override: chatModel || undefined,
        },
        { auth: hasPrivateIds },
      );
      setSessionId(response.session_id);
      return response;
    },
    [messages, flow.report, sessionId, documentIds, locale, chatModel],
  );

  /** Attach files to composer only — never starts extraction until Send. */
  const queueFiles = useCallback(
    async (fileList: FileList | File[]) => {
      const files = Array.from(fileList);
      if (files.length === 0 || composerBusy) return;

      const existingNames = new Set([
        ...pendingAttachments.map((item) => item.file.name),
        ...Object.values(flow.slots).map((slot) => slot?.file.name).filter(Boolean),
      ]);

      for (const file of files) {
        if (existingNames.has(file.name)) continue;
        const slotId = detectSlotFromFile(file);
        const ok = await flow.selectFile(slotId, file);
        if (!ok) continue;
        existingNames.add(file.name);
        setPendingAttachments((prev) => [
          ...prev.filter((item) => item.slotId !== slotId),
          { id: crypto.randomUUID(), file, slotId },
        ]);
      }
    },
    [composerBusy, flow, pendingAttachments],
  );

  const removePendingAttachment = useCallback(
    (id: string) => {
      setPendingAttachments((prev) => {
        const target = prev.find((item) => item.id === id);
        if (target) {
          flow.removeFile(target.slotId);
        }
        return prev.filter((item) => item.id !== id);
      });
    },
    [flow],
  );

  const submitComposer = useCallback(
    async (raw: string) => {
      const trimmed = raw.trim();
      const pending = [...pendingAttachments];
      if ((!trimmed && pending.length === 0) || isLoadingRef.current || flow.isBusy) return;

      isLoadingRef.current = true;
      setIsLoading(true);
      setError(null);
      setMessage('');
      setPendingAttachments([]);

      const now = new Date().toISOString();
      if (trimmed) {
        pushMessage({
          id: crypto.randomUUID(),
          role: 'user',
          content: trimmed,
          createdAt: now,
          prompt: trimmed,
          kind: 'text',
        });
        if (/\b\d{8,9}\b/.test(trimmed) || /id\s*(number|#|no)/i.test(trimmed)) {
          setTypedFacts((prev) => [...prev, trimmed]);
        }
      }

      for (const item of pending) {
        pushMessage({
          id: crypto.randomUUID(),
          role: 'user',
          content: t('landingChat.userUploaded', {
            type: t(`slots.${item.slotId}`),
            name: item.file.name,
          }),
          createdAt: new Date().toISOString(),
          kind: 'text',
        });
      }

      try {
        const payslip = pending.find((item) => item.slotId === 'payslip');
        const supporting = pending.filter((item) => item.slotId !== 'payslip');

        if (payslip) {
          setDocumentConfirmed(false);
          setReviewMessageId(null);
          setReportMessageId(null);
          pushMessage({
            id: crypto.randomUUID(),
            role: 'assistant',
            content: t('landingChat.extracting'),
            createdAt: new Date().toISOString(),
            kind: 'status',
          });
          const payslipDocumentId = await flow.startExtraction(payslip.file);
          if (supporting.length > 0 && payslipDocumentId) {
            await flow.storeSupportingFiles(
              supporting.map((item) => ({ slotId: item.slotId, file: item.file })),
              payslipDocumentId,
            );
            for (const item of supporting) {
              pushMessage({
                id: crypto.randomUUID(),
                role: 'assistant',
                content: t('landingChat.supportingStored', {
                  type: t(`slots.${item.slotId}`),
                }),
                createdAt: new Date().toISOString(),
                kind: 'text',
              });
            }
          }
        } else if (supporting.length > 0) {
          await flow.storeSupportingFiles(
            supporting.map((item) => ({ slotId: item.slotId, file: item.file })),
            flow.slots.payslip?.documentId,
          );
          for (const item of supporting) {
            pushMessage({
              id: crypto.randomUUID(),
              role: 'assistant',
              content: t('landingChat.supportingStored', {
                type: t(`slots.${item.slotId}`),
              }),
              createdAt: new Date().toISOString(),
              kind: 'text',
            });
          }
        }

        if (trimmed) {
          const payslipReady = Boolean(payslip || hasPayslip || flow.slots.payslip?.file);
          if (looksLikeValidationRequest(trimmed) && !payslipReady) {
            pushMessage({
              id: crypto.randomUUID(),
              role: 'assistant',
              content: t('landingChat.needPayslip'),
              createdAt: new Date().toISOString(),
              kind: 'text',
            });
            return;
          }

          if (
            looksLikeIdRequest(trimmed) &&
            !flow.slots.national_id?.file &&
            !supporting.some((item) => item.slotId === 'national_id') &&
            !/\d{8,9}/.test(trimmed)
          ) {
            pushMessage({
              id: crypto.randomUUID(),
              role: 'assistant',
              content: t('landingChat.needId'),
              createdAt: new Date().toISOString(),
              kind: 'text',
            });
            return;
          }

          // Skip assistant call when this Send was primarily a document submission.
          if (!payslip && supporting.length === 0) {
            const response = await askAssistant(trimmed);
            pushMessage({
              id: crypto.randomUUID(),
              role: 'assistant',
              content: response.answer,
              createdAt: new Date().toISOString(),
              prompt: trimmed,
              sources: response.sources,
              guardrailStatus: response.guardrail_status,
              usage: response.usage ?? null,
              kind: 'text',
            });
          } else if (payslip && trimmed && !looksLikeValidationRequest(trimmed)) {
            const response = await askAssistant(trimmed);
            pushMessage({
              id: crypto.randomUUID(),
              role: 'assistant',
              content: response.answer,
              createdAt: new Date().toISOString(),
              prompt: trimmed,
              sources: response.sources,
              guardrailStatus: response.guardrail_status,
              usage: response.usage ?? null,
              kind: 'text',
            });
          }
        }
      } catch {
        setError(t('assistant.unavailable'));
      } finally {
        isLoadingRef.current = false;
        setIsLoading(false);
      }
    },
    [askAssistant, flow, hasPayslip, pendingAttachments, pushMessage, t],
  );

  const handleFiles = useCallback(
    async (fileList: FileList | File[]) => {
      await queueFiles(fileList);
    },
    [queueFiles],
  );

  // When extraction reaches review, embed the editable document card once.
  useEffect(() => {
    if (flow.step !== 'review' || !flow.extraction || reviewMessageId) return;
    const id = crypto.randomUUID();
    setReviewMessageId(id);
    pushMessage({
      id,
      role: 'assistant',
      content: t('landingChat.reviewReady'),
      createdAt: new Date().toISOString(),
      kind: 'document_review',
    });
  }, [flow.step, flow.extraction, reviewMessageId, pushMessage, t]);

  // Surface extraction errors as chat messages (once per distinct message).
  const lastErrorRef = useRef<string | null>(null);
  useEffect(() => {
    if (!flow.flowError || flow.flowError === lastErrorRef.current) return;
    lastErrorRef.current = flow.flowError;
    pushMessage({
      id: crypto.randomUUID(),
      role: 'assistant',
      content: flow.flowError,
      createdAt: new Date().toISOString(),
      kind: 'status',
    });
  }, [flow.flowError, pushMessage]);

  // When validation report arrives, embed summary card.
  useEffect(() => {
    if (flow.step !== 'report' || !flow.report || reportMessageId) return;
    const id = crypto.randomUUID();
    setReportMessageId(id);
    pushMessage({
      id,
      role: 'assistant',
      content: t('landingChat.validationReady'),
      createdAt: new Date().toISOString(),
      kind: 'validation_summary',
    });
  }, [flow.step, flow.report, reportMessageId, pushMessage, t]);

  // Confirmed without report is no longer expected (mapping → validation runs after confirm).
  useEffect(() => {
    if (flow.step !== 'report' || flow.report || reportMessageId) return;
    if (!documentConfirmed) return;
    const id = crypto.randomUUID();
    setReportMessageId(id);
    pushMessage({
      id,
      role: 'assistant',
      content: t('landingChat.confirmedReady', {
        defaultValue: 'Document confirmed. Running validation…',
      }),
      createdAt: new Date().toISOString(),
      kind: 'text',
    });
  }, [flow.step, flow.report, reportMessageId, documentConfirmed, pushMessage, t]);

  const confirmDocument = useCallback(async () => {
    setDocumentConfirmed(true);
    pushMessage({
      id: crypto.randomUUID(),
      role: 'user',
      content: t('landingChat.userConfirmed'),
      createdAt: new Date().toISOString(),
      kind: 'text',
    });
    pushMessage({
      id: crypto.randomUUID(),
      role: 'assistant',
      content: t('landingChat.confirming', {
        defaultValue: 'Saving your confirmed fields…',
      }),
      createdAt: new Date().toISOString(),
      kind: 'status',
    });
    setReportMessageId(null);
    await flow.continueToValidate();
  }, [flow, pushMessage, t]);

  const onDrop = async (event: DragEvent) => {
    event.preventDefault();
    setDragOver(false);
    if (event.dataTransfer.files?.length) {
      await handleFiles(event.dataTransfer.files);
    }
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    await submitComposer(message);
  };

  const canSend =
    !composerBusy && (message.trim().length > 0 || pendingAttachments.length > 0);

  return (
    <div
      className={`landing-chat ${dragOver ? 'landing-chat--drag' : ''}`}
      onDragEnter={(event) => {
        event.preventDefault();
        setDragOver(true);
      }}
      onDragOver={(event) => {
        event.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={(event) => {
        event.preventDefault();
        if (event.currentTarget === event.target) setDragOver(false);
      }}
      onDrop={(event) => {
        void onDrop(event);
      }}
    >
      <header className="landing-chat__hero">
        <p className="landing__eyebrow">{t('landing.eyebrow')}</p>
        <h1>{t('landing.title')}</h1>
        <p className="landing-chat__lead">{t('landingChat.lead')}</p>
      </header>

      <div className="landing-chat__layout">
      <PopularQuestionsPanel
        disabled={composerBusy}
        onSelect={(question) => {
          void submitComposer(question);
        }}
      />
      <div className="landing-chat__shell" aria-label={t('landing.chatHeading')}>
        <div className="landing-chat__messages" aria-live="polite">
          {messages.length === 0 && (
            <div className="landing-chat__empty">
              <p>{t('landingChat.empty')}</p>
            </div>
          )}

          {messages.map((msg) => (
            <div key={msg.id} className={`chat-bubble chat-bubble--${msg.role}`}>
              {msg.kind === 'document_review' && flow.extraction ? (
                <>
                  <AssistantMarkdown content={msg.content} />
                  <ChatDocumentReviewCard
                    fileName={payslipName || t('slots.payslip')}
                    entries={flow.entries}
                    confirmed={documentConfirmed}
                    busy={flow.step === 'validating'}
                    onChangeEntry={flow.updateEntry}
                    onDeleteEntry={flow.deleteEntry}
                    onAddEntry={flow.addEntry}
                    onConfirm={() => {
                      void confirmDocument();
                    }}
                  />
                </>
              ) : msg.kind === 'validation_summary' && flow.report ? (
                <>
                  <AssistantMarkdown content={msg.content} />
                  <ChatValidationSummaryCard report={flow.report} fileName={payslipName} />
                </>
              ) : msg.role === 'assistant' ? (
                <AssistantMarkdown content={msg.content} />
              ) : (
                <p className="chat-bubble__plain">{msg.content}</p>
              )}

              {msg.guardrailStatus &&
                msg.guardrailStatus !== 'passed' &&
                msg.guardrailStatus !== 'answered_from_source' && (
                  <div
                    className={`assistant-banner assistant-banner--${
                      msg.guardrailStatus.startsWith('blocked') ? 'blocked' : 'limited'
                    }`}
                  >
                    {guardrailLabel(msg.guardrailStatus)}
                  </div>
                )}

              {msg.sources && msg.sources.length > 0 && env.isDevRuntime && (
                <ul className="chat-message__sources">
                  {msg.sources.map((source) => (
                    <li key={`${source.title}-${source.reference ?? 'na'}`}>
                      {source.title}
                      {source.reference ? ` (${source.reference})` : ''}
                    </li>
                  ))}
                </ul>
              )}

              <div className="chat-bubble__meta">
                <time dateTime={msg.createdAt}>{formatTimestamp(msg.createdAt, i18n.language)}</time>
              </div>
              {msg.role === 'assistant' && msg.kind === 'text' ? (
                <AssistantUsageFooter usage={msg.usage} />
              ) : null}
            </div>
          ))}

          {(isLoading || flow.step === 'prepare' || flow.step === 'validating') && (
            <div className="chat-bubble chat-bubble--assistant" aria-label={t('assistant.typing')}>
              <div className="chat-typing">
                <span>
                  {flow.step === 'prepare'
                    ? flow.processingStage === 'reading_pdf'
                      ? t('landingChat.stages.readingPdf')
                      : flow.processingStage === 'running_ocr'
                        ? t('landingChat.stages.runningOcr')
                        : flow.processingStage === 'structuring_fields'
                          ? t('landingChat.stages.structuringFields')
                          : flow.processingStage === 'preparing_review'
                            ? t('landingChat.stages.preparingReview')
                            : t('landingChat.extracting')
                    : flow.step === 'validating'
                      ? t('landingChat.confirming', { defaultValue: 'Saving your confirmed fields…' })
                      : t('assistant.typing')}
                </span>
                <span className="chat-typing__dots" aria-hidden="true">
                  <span />
                  <span />
                  <span />
                </span>
              </div>
              {flow.step === 'prepare' && (
                <button type="button" className="chat-cancel-btn" onClick={() => flow.cancelExtraction()}>
                  {t('common.cancel')}
                </button>
              )}
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {error && <p className="chat-panel__error">{error}</p>}
        {flow.flowError && (
          <div className="landing-chat__extract-error" role="alert">
            <p>{flow.flowError}</p>
            <ul className="landing-chat__extract-hints">
              {flow.extraction?.ocr_status === 'failed' && (
                <li>{t('landingChat.errors.ocrFailed')}</li>
              )}
              {flow.extraction?.parser_status === 'failed' && (
                <li>{t('landingChat.errors.parserFailed')}</li>
              )}
              <li>{t('landingChat.errors.retryHint')}</li>
            </ul>
            <button
              type="button"
              className="btn btn--secondary"
              onClick={() => fileInputRef.current?.click()}
            >
              {t('landingChat.retryUpload')}
            </button>
          </div>
        )}
        {dragOver && (
          <div className="landing-chat__drop-hint" role="status">
            {t('landingChat.dropHint')}
          </div>
        )}

        <div className="landing-chat__composer">
          <input
            ref={fileInputRef}
            type="file"
            accept={ACCEPT}
            multiple
            hidden
            onChange={(event) => {
              if (event.target.files) {
                void handleFiles(event.target.files);
              }
              event.target.value = '';
            }}
          />
          {pendingAttachments.length > 0 && (
            <ul className="landing-chat__pending" aria-label={t('landingChat.pendingAttachments')}>
              {pendingAttachments.map((item) => (
                <li key={item.id} className="landing-chat__pending-item">
                  <span>
                    {t(`slots.${item.slotId}`)} · {item.file.name}
                  </span>
                  <button
                    type="button"
                    className="landing-chat__pending-remove"
                    onClick={() => removePendingAttachment(item.id)}
                    disabled={composerBusy}
                    aria-label={t('landingChat.removeAttachment')}
                  >
                    ×
                  </button>
                </li>
              ))}
            </ul>
          )}
          <ChatComposer
            value={message}
            onChange={setMessage}
            onSubmit={handleSubmit}
            disabled={composerBusy}
            canSend={canSend}
            placeholder={t('landingChat.placeholder')}
            ariaMessage={t('assistant.ariaMessage')}
            onAttach={() => fileInputRef.current?.click()}
            attachAria={t('landingChat.attachAria')}
            modelChoices={chatModelChoices}
            modelValue={chatModel}
            onModelChange={setChatModel}
            sendingLabel={
              composerBusy ? (
                <span className="chat-composer__send-icon" aria-hidden="true">
                  …
                </span>
              ) : undefined
            }
          />
        </div>

        <p className="landing-chat__session-note">{t('landingChat.sessionNote')}</p>
        <p className="landing-chat__formats">
          {GUEST_ACTIVE_DOCUMENT_SLOTS.map((slot) => t(slot.labelKey)).join(' · ')}
        </p>
      </div>
      </div>
    </div>
  );
}
