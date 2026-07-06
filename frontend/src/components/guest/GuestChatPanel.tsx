import { useState, type FormEvent } from 'react';
import { Card } from '../ui/Card';
import '../ui/ui.css';

/**
 * Guest payroll chat — AI assists with explanations, not legality decisions.
 * @integration-point GUEST_CHAT
 */
export function GuestChatPanel() {
  const [message, setMessage] = useState('');
  const [messages, setMessages] = useState<string[]>([]);

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (!message.trim()) return;
    setMessages((prev) => [...prev, message.trim()]);
    setMessage('');
    // @integration-point GUEST_CHAT_SEND — connect to AI explanation endpoint
  };

  return (
    <Card title="Payroll Assistant Chat">
      <p className="guest-section__intro">
        Ask payroll-related questions. Responses are AI-generated explanations and do not
        constitute legal validation.
      </p>
      <div className="chat-panel">
        <div className="chat-panel__messages">
          {messages.length === 0 ? (
            <p className="chat-panel__empty">
              No messages yet. Ask about payslip line items, leave balances, or document requirements.
            </p>
          ) : (
            messages.map((msg, i) => <p key={i}>{msg}</p>)
          )}
        </div>
        <form className="chat-panel__input-row" onSubmit={handleSubmit}>
          <input
            type="text"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="Ask a payroll question..."
            aria-label="Chat message"
          />
          <button type="submit" className="btn btn--primary">
            Send
          </button>
        </form>
      </div>
    </Card>
  );
}
