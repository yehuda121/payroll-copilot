import { useState, type FormEvent } from 'react';
import { assistantService } from '../../services/assistant';
import type { AssistantGuardrailStatus, ChatMessage } from '../../types/assistant';
import { Card } from '../ui/Card';
import '../ui/ui.css';
import '../../features/guest/guest.css';

const SUGGESTED_QUESTIONS = [
  'What documents are needed to validate a payslip?',
  'How should overtime be reflected on a payslip?',
  'What is the difference between a validation warning and a critical issue?',
];

type GuestChatPanelProps = {
  title?: string;
  intro?: string;
  validationRunId?: string;
  documentIds?: string[];
};

function guardrailLabel(status: AssistantGuardrailStatus): string {
  switch (status) {
    case 'blocked':
      return 'This request could not be processed.';
    case 'limited':
      return 'No approved source was found for this question.';
    default:
      return '';
  }
}

export function GuestChatPanel({
  title = 'Payroll Assistant',
  intro = 'Ask payroll-related questions using approved internal sources. This assistant explains and guides — it does not determine legal compliance.',
  validationRunId,
  documentIds = [],
}: GuestChatPanelProps) {
  const [message, setMessage] = useState('');
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
        locale: 'en',
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
      setError('The Payroll Assistant is temporarily unavailable. Please try again later.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    await submitMessage(message);
  };

  return (
    <Card title={title}>
      <p className="guest-section__intro">{intro}</p>
      <div className="chat-panel">
        <div className="chat-panel__messages" aria-live="polite">
          {messages.length === 0 ? (
            <div className="chat-panel__empty">
              <p>Ask a payroll or employee-rights question.</p>
              <div className="chat-panel__suggestions">
                {SUGGESTED_QUESTIONS.map((question) => (
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
                    <p className="chat-message__guardrail">
                      No approved source was found in the Payroll Assistant knowledge base.
                    </p>
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
            placeholder="Ask a payroll question..."
            aria-label="Chat message"
            disabled={isLoading}
          />
          <button type="submit" className="btn btn--primary" disabled={isLoading || !message.trim()}>
            {isLoading ? 'Sending...' : 'Send'}
          </button>
        </form>
      </div>
    </Card>
  );
}
