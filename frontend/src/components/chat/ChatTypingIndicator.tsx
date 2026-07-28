import type { ReactNode } from 'react';

type ChatTypingIndicatorProps = {
  label: string;
  action?: ReactNode;
};

/**
 * Shared thinking / typing indicator — presentation only.
 */
export function ChatTypingIndicator({ label, action }: ChatTypingIndicatorProps) {
  return (
    <div className="chat-message-row chat-message-row--assistant chat-message-row--typing">
      <span className="chat-avatar chat-avatar--assistant" aria-hidden="true">
        <span className="chat-avatar__pulse" />
      </span>
      <div className="chat-message-row__body">
        <div className="chat-bubble chat-bubble--assistant chat-bubble--typing" aria-live="polite">
          <div className="chat-typing">
            <span className="chat-typing__label" dir="auto">
              {label}
            </span>
            <span className="chat-typing__dots" aria-hidden="true">
              <span />
              <span />
              <span />
            </span>
          </div>
          {action}
        </div>
      </div>
    </div>
  );
}
