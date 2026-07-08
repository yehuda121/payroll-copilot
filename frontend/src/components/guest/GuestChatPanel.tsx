import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { useAppLocale } from '../../hooks/useAppLocale';
import { assistantService } from '../../services/assistant';
import type { AssistantGuardrailStatus, ChatMessage } from '../../types/assistant';
import { Card } from '../ui/Card';
import '../ui/ui.css';
import '../../features/guest/guest.css';

type GuestChatPanelProps = {
  title?: string;
  intro?: string;
  validationRunId?: string;
  documentIds?: string[];
};

export function GuestChatPanel({
  title,
  intro,
  validationRunId,
  documentIds = [],
}: GuestChatPanelProps) {
  const { t } = useTranslation();
  const { locale } = useAppLocale();
  const [message, setMessage] = useState('');
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const resolvedTitle = title ?? t('assistant.title');
  const resolvedIntro = intro ?? t('assistant.intro');
  const suggestedQuestions = [
    t('assistant.suggested1'),
    t('assistant.suggested2'),
    t('assistant.suggested3'),
  ];

  const guardrailLabel = (status: AssistantGuardrailStatus): string => {
    switch (status) {
      case 'blocked':
        return t('assistant.guardrailBlocked');
      case 'limited':
        return t('assistant.guardrailLimited');
      default:
        return '';
    }
  };

  const submitMessage = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || isLoading) return;

    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: trimmed,
    };
    setMessages((prev) => [...prev, userMessage]);
    setMessage('');
    setError(null);
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
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: response.answer,
          sources: response.sources,
          guardrailStatus: response.guardrail_status,
        },
      ]);
    } catch {
      setError(t('assistant.unavailable'));
    } finally {
      setIsLoading(false);
    }
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    await submitMessage(message);
  };

  return (
    <Card title={resolvedTitle}>
      <p className="guest-section__intro">{resolvedIntro}</p>
      <div className="chat-panel">
        <div className="chat-panel__messages" aria-live="polite">
          {messages.length === 0 ? (
            <div className="chat-panel__empty">
              <p>{t('assistant.empty')}</p>
              <div className="chat-panel__suggestions">
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
            </div>
          ) : (
            messages.map((msg) => (
              <div key={msg.id} className={`chat-message chat-message--${msg.role}`}>
                <p>{msg.content}</p>
                {msg.guardrailStatus && msg.guardrailStatus !== 'passed' && (
                  <div
                    className={`assistant-banner assistant-banner--${msg.guardrailStatus === 'blocked' ? 'blocked' : 'limited'}`}
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
                  msg.guardrailStatus === 'limited' && (
                    <p className="chat-message__guardrail">{t('assistant.noSource')}</p>
                  )
                )}
              </div>
            ))
          )}
        </div>
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
    </Card>
  );
}
