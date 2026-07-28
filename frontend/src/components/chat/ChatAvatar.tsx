import { SparklesIcon } from '../ui/icons';

type ChatAvatarProps = {
  role: 'assistant' | 'user';
  label?: string;
};

/**
 * Language-agnostic avatar for chat rows.
 * Layout mirrors via logical CSS; no hardcoded LTR/RTL.
 */
export function ChatAvatar({ role, label }: ChatAvatarProps) {
  if (role === 'user') {
    return (
      <span className="chat-avatar chat-avatar--user" aria-hidden={label ? undefined : true} title={label}>
        <span className="chat-avatar__initial">{label?.trim().charAt(0)?.toUpperCase() || 'U'}</span>
      </span>
    );
  }

  return (
    <span className="chat-avatar chat-avatar--assistant" aria-hidden={label ? undefined : true} title={label}>
      <SparklesIcon size={14} aria-hidden="true" />
    </span>
  );
}
