import { AssistantMarkdown } from './AssistantMarkdown';
import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { useAppLocale } from '../../hooks/useAppLocale';
import { assistantService } from '../../services/assistant';
import type { AssistantGuardrailStatus, ChatMessage } from '../../types/assistant';
import '../ui/ui.css';
import '../../features/guest/guest.css';

type GuestChatPanelProps = {
  compact?: boolean;
  showSuggestionsInline?: boolean;
  validationRunId?: string;
  documentIds?: string[];
  pendingQuestion?: string | null;
  onPendingQuestionConsumed?: () => void;
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
  showSuggestionsInline = true,
  validationRunId,
  documentIds = [],
  pendingQuestion = null,
  onPendingQuestionConsumed,
}: GuestChatPanelProps) {
  const { t, i18n } = useTranslation();
  const { locale } = useAppLocale();
  const [message, setMessage] = useState('');
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const isLoadingRef = useRef(false);

  const suggestedQuestions = [
    t('assistant.suggested1'),
    t('assistant.suggested2'),
    t('assistant.suggested3'),
  ];

  const followUps = [t('assistant.followUp1'), t('assistant.followUp2'), t('assistant.followUp3')];

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, [messages, isLoading]);

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
        const response = await assistantService.chat({
          message: trimmed,
          session_id: sessionId,
          document_ids: documentIds,
          validation_run_id: validationRunId,
          locale,
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
    [documentIds, locale, sessionId, t, validationRunId],
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

  const showFollowUps =
    !isLoading && messages.some((msg) => msg.role === 'assistant') && messages.length > 0;

  return (
    <div className={`chat-shell ${compact ? 'chat-shell--compact' : ''}`}>
      {!compact && (
        <div className="chat-shell__heading">
          <h2>{t('landing.chatHeading')}</h2>
          <p>{t('assistant.intro')}</p>
        </div>
      )}

      <div className="chat-shell__messages" aria-live="polite">
        {messages.length === 0 && (
          <div className="chat-shell__empty">
            <p>{t('assistant.empty')}</p>
            {showSuggestionsInline && (
              <div className="chat-shell__suggestions">
                {suggestedQuestions.map((question) => (
                  <button
                    key={question}
                    type="button"
                    className="btn btn--secondary"
                    onClick={() => {
                      void submitMessage(question);
                    }}
                  >
                    {question}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

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
            {msg.sources && msg.sources.length > 0 ? (
              <ul className="chat-message__sources">
                {msg.sources.map((source) => (
                  <li key={`${source.title}-${source.reference ?? 'na'}`}>
                    {source.title}
                    {source.reference ? ` (${source.reference})` : ''}
                  </li>
                ))}
              </ul>
            ) : (
              msg.role === 'assistant' &&
              (msg.guardrailStatus === 'limited' || msg.guardrailStatus === 'limited_in_domain') && (
                <p className="chat-message__guardrail">{t('assistant.noSource')}</p>
              )
            )}
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
      </div>

      {showFollowUps && (
        <div className="chat-shell__followups">
          <p>{t('assistant.followUpHeading')}</p>
          <div className="chat-shell__suggestions">
            {followUps.map((question) => (
              <button
                key={question}
                type="button"
                className="btn btn--secondary"
                onClick={() => {
                  void submitMessage(question);
                }}
              >
                {question}
              </button>
            ))}
          </div>
        </div>
      )}

      {error && <p className="chat-panel__error">{error}</p>}

      <form className="chat-panel__input-row" onSubmit={handleSubmit}>
        <input
          type="text"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder={t('assistant.placeholder')}
          aria-label={t('assistant.ariaMessage')}
          disabled={isLoading}
        />
        <button type="submit" className="btn btn--primary" disabled={isLoading || !message.trim()}>
          {isLoading ? t('common.sending') : t('common.send')}
        </button>
      </form>
    </div>
  );
}
