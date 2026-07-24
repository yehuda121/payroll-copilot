import { AssistantMarkdown } from './AssistantMarkdown';
import { AssistantUsageFooter } from './AssistantUsageFooter';
import { ChatComposer } from './ChatComposer';
import { ChatWelcome } from '../chat/ChatWelcome';
import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { env } from '../../config/env';
import { useAppLocale } from '../../hooks/useAppLocale';
import { assistantService } from '../../services/assistant';
import type {
  AssistantChatRequest,
  AssistantChatResponse,
  AssistantGuardrailStatus,
  ChatMessage,
} from '../../types/assistant';
import '../ui/ui.css';
import '../../features/guest/guest.css';
import '../../features/guest/landing/landing-chat.css';

type GuestChatPanelProps = {
  compact?: boolean;
  validationRunId?: string;
  documentIds?: string[];
  pendingQuestion?: string | null;
  onPendingQuestionConsumed?: () => void;
  /** Opens existing upload flow when provided (Landing). */
  onAttach?: () => void;
  /**
   * Employee chat supplies its authenticated handler. Public callers omit it
   * and keep using the existing public assistant service unchanged.
   */
  chatHandler?: (payload: AssistantChatRequest) => Promise<AssistantChatResponse>;
  /**
   * Use Landing product shell (fixed viewport height, toolbar composer).
   * Domain behavior is unchanged.
   */
  productShell?: boolean;
  /** When set with productShell, shows ChatWelcome using this i18n namespace. */
  welcomeNamespace?: string;
  welcomeSuggestionKeys?: readonly string[];
};

function formatTimestamp(iso: string, locale: string): string {
  try {
    return new Intl.DateTimeFormat(locale, {
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date(iso));
  } catch {
    return '';
  }
}

export function GuestChatPanel({
  compact = false,
  validationRunId,
  documentIds = [],
  pendingQuestion = null,
  onPendingQuestionConsumed,
  onAttach,
  chatHandler = assistantService.chat,
  productShell = false,
  welcomeNamespace,
  welcomeSuggestionKeys,
}: GuestChatPanelProps) {
  const { t, i18n } = useTranslation();
  const { locale } = useAppLocale();
  const [message, setMessage] = useState('');
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [chatModel, setChatModel] = useState('');
  const [chatModelChoices, setChatModelChoices] = useState<string[]>([]);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const isLoadingRef = useRef(false);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, [messages, isLoading]);

  useEffect(() => {
    let cancelled = false;
    void assistantService
      .modelChoices()
      .then((choices) => {
        if (!cancelled) setChatModelChoices(choices.chat);
      })
      .catch(() => {
        /* optional allowlist endpoint */
      });
    return () => {
      cancelled = true;
    };
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

  const submitMessage = useCallback(
    async (text: string, options?: { replaceAssistantId?: string }) => {
      const trimmed = text.trim();
      if (!trimmed || isLoadingRef.current) return;

      const now = new Date().toISOString();
      if (!options?.replaceAssistantId) {
        const userMessage: ChatMessage = {
          id: crypto.randomUUID(),
          role: 'user',
          content: trimmed,
          createdAt: now,
          prompt: trimmed,
        };
        setMessages((prev) => [...prev, userMessage]);
      }
      setMessage('');
      setError(null);
      isLoadingRef.current = true;
      setIsLoading(true);

      try {
        const conversation_turns = messages
          .filter((msg) => (msg.role === 'user' || msg.role === 'assistant') && msg.content.trim())
          .slice(-12)
          .map((msg) => ({ role: msg.role, content: msg.content }));
        const response = await chatHandler({
          message: trimmed,
          session_id: sessionId,
          document_ids: documentIds,
          validation_run_id: validationRunId,
          conversation_turns,
          locale,
          model_provider_override: chatModel || undefined,
        });
        setSessionId(response.session_id);
        const assistantMessage: ChatMessage = {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: response.answer,
          createdAt: new Date().toISOString(),
          prompt: trimmed,
          sources: response.sources,
          guardrailStatus: response.guardrail_status,
          usage: response.usage ?? null,
        };

        setMessages((prev) => {
          if (!options?.replaceAssistantId) {
            return [...prev, assistantMessage];
          }
          return prev.map((msg) => (msg.id === options.replaceAssistantId ? assistantMessage : msg));
        });
      } catch {
        setError(t('assistant.unavailable'));
      } finally {
        isLoadingRef.current = false;
        setIsLoading(false);
      }
    },
    [chatHandler, chatModel, documentIds, locale, messages, sessionId, t, validationRunId],
  );

  useEffect(() => {
    if (!pendingQuestion) return;
    const question = pendingQuestion;
    onPendingQuestionConsumed?.();
    void submitMessage(question);
    // Consume immediately so session updates don't retrigger the same suggestion.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingQuestion]);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    await submitMessage(message);
  };

  const copyMessage = async (msg: ChatMessage) => {
    try {
      await navigator.clipboard.writeText(msg.content);
      setCopiedId(msg.id);
      window.setTimeout(() => setCopiedId(null), 1500);
    } catch {
      setError(t('common.error'));
    }
  };

  const regenerate = async (msg: ChatMessage) => {
    if (!msg.prompt) return;
    await submitMessage(msg.prompt, { replaceAssistantId: msg.id });
  };

  const emptyState =
    messages.length === 0 ? (
      welcomeNamespace ? (
        <div className={productShell ? 'landing-chat__empty' : 'chat-shell__empty'}>
          <ChatWelcome namespace={welcomeNamespace} suggestionKeys={welcomeSuggestionKeys} />
        </div>
      ) : (
        <div className={productShell ? 'landing-chat__empty' : 'chat-shell__empty'}>
          <p>{t('assistant.empty')}</p>
        </div>
      )
    ) : null;

  const messageList = (
    <>
      {emptyState}
      {messages.map((msg) => (
        <div key={msg.id} className={`chat-bubble chat-bubble--${msg.role}`}>
          {msg.role === 'assistant' ? (
            <AssistantMarkdown content={msg.content} />
          ) : (
            <p className="chat-bubble__plain">{msg.content}</p>
          )}
          {msg.guardrailStatus &&
            msg.guardrailStatus !== 'passed' &&
            msg.guardrailStatus !== 'answered_from_source' && (
              <div
                className={`assistant-banner assistant-banner--${
                  msg.guardrailStatus === 'blocked' ||
                  msg.guardrailStatus === 'blocked_off_topic' ||
                  msg.guardrailStatus === 'blocked_safety'
                    ? 'blocked'
                    : 'limited'
                }`}
              >
                {guardrailLabel(msg.guardrailStatus)}
              </div>
            )}
          {msg.sources && msg.sources.length > 0 && env.isDevRuntime ? (
            <ul className="chat-message__sources">
              {msg.sources.map((source) => (
                <li key={`${source.title}-${source.reference ?? 'na'}`}>
                  {source.title}
                  {source.reference ? ` (${source.reference})` : ''}
                </li>
              ))}
            </ul>
          ) : null}
          {msg.role === 'assistant' &&
          (!msg.sources || msg.sources.length === 0) &&
          (msg.guardrailStatus === 'limited' || msg.guardrailStatus === 'limited_in_domain') ? (
            <p className="chat-message__guardrail">{t('assistant.noSource')}</p>
          ) : null}
          <div className="chat-bubble__meta">
            <time dateTime={msg.createdAt}>{formatTimestamp(msg.createdAt, i18n.language)}</time>
            {msg.role === 'assistant' && (
              <div className="chat-bubble__actions">
                <button type="button" className="btn btn--ghost" onClick={() => void copyMessage(msg)}>
                  {copiedId === msg.id ? t('common.copied') : t('common.copy')}
                </button>
                <button
                  type="button"
                  className="btn btn--ghost"
                  onClick={() => {
                    void regenerate(msg);
                  }}
                  disabled={isLoading}
                >
                  {t('common.regenerate')}
                </button>
              </div>
            )}
          </div>
          {msg.role === 'assistant' ? <AssistantUsageFooter usage={msg.usage} /> : null}
        </div>
      ))}

      {isLoading && (
        <div className="chat-bubble chat-bubble--assistant" aria-label={t('assistant.typing')}>
          <div className="chat-typing">
            <span>{t('assistant.typing')}</span>
            <span className="chat-typing__dots" aria-hidden="true">
              <span />
              <span />
              <span />
            </span>
          </div>
        </div>
      )}
      <div ref={bottomRef} />
    </>
  );

  const composer = (
    <ChatComposer
      value={message}
      onChange={setMessage}
      onSubmit={handleSubmit}
      disabled={isLoading}
      canSend={Boolean(message.trim())}
      placeholder={t('assistant.placeholder')}
      ariaMessage={t('assistant.ariaMessage')}
      onAttach={onAttach}
      modelChoices={chatModelChoices}
      modelValue={chatModel}
      onModelChange={setChatModel}
      toolbarControls={productShell}
      sendingLabel={
        isLoading ? (
          <span className="chat-composer__send-icon" aria-hidden="true">
            …
          </span>
        ) : undefined
      }
    />
  );

  if (productShell) {
    return (
      <div className={`landing-chat payroll-chat${compact ? ' payroll-chat--compact' : ''}`}>
        <div className="landing-chat__layout">
          <div className="landing-chat__shell" aria-label={t('assistant.title')}>
            <div className="landing-chat__messages" aria-live="polite">
              {messageList}
            </div>
            {error ? <p className="chat-panel__error">{error}</p> : null}
            <div className="landing-chat__composer">{composer}</div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={`chat-shell ${compact ? 'chat-shell--compact' : ''}`}>
      <div className="chat-shell__messages" aria-live="polite">
        {messageList}
      </div>
      {error ? <p className="chat-panel__error">{error}</p> : null}
      {composer}
    </div>
  );
}
