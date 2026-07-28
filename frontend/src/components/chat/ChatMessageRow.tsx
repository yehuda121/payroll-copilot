import type { ReactNode } from 'react';
import { ChatAvatar } from './ChatAvatar';

type ChatMessageRowProps = {
  role: 'assistant' | 'user';
  children: ReactNode;
  meta?: ReactNode;
  className?: string;
  assistantLabel?: string;
  userLabel?: string;
};

/**
 * Full-width ChatGPT-style message row with avatar.
 * Content direction uses dir=auto so mixed HE/EN wraps correctly.
 */
export function ChatMessageRow({
  role,
  children,
  meta,
  className = '',
  assistantLabel,
  userLabel,
}: ChatMessageRowProps) {
  return (
    <article
      className={`chat-message-row chat-message-row--${role}${className ? ` ${className}` : ''}`}
    >
      <ChatAvatar
        role={role}
        label={role === 'assistant' ? assistantLabel : userLabel}
      />
      <div className="chat-message-row__body">
        <div className={`chat-bubble chat-bubble--${role}`} dir="auto">
          {children}
        </div>
        {meta ? <div className="chat-message-row__meta">{meta}</div> : null}
      </div>
    </article>
  );
}
