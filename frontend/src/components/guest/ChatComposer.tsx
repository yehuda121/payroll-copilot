import type { FormEvent, ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { PaperclipIcon, SendIcon } from '../ui/icons';

export type ChatComposerProps = {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (event: FormEvent) => void;
  disabled?: boolean;
  canSend: boolean;
  placeholder: string;
  ariaMessage: string;
  /** When set, opens the existing upload flow (paperclip). */
  onAttach?: () => void;
  attachAria?: string;
  modelChoices?: string[];
  modelValue?: string;
  onModelChange?: (value: string) => void;
  sendingLabel?: ReactNode;
  /**
   * Landing-only: single-row toolbar — paperclip | input | model+send (fixed LTR).
   * Default keeps the existing inline layout for other surfaces.
   */
  toolbarControls?: boolean;
};

function modelLabel(name: string, t: (key: string) => string): string {
  if (name === 'ollama') return t('assistant.modelLocal');
  if (name === 'openai') return 'OpenAI';
  if (name === 'bedrock') return 'Bedrock';
  return name;
}

/**
 * Shared modern chat composer used by Landing, Employee, and Accountant chat.
 */
export function ChatComposer({
  value,
  onChange,
  onSubmit,
  disabled = false,
  canSend,
  placeholder,
  ariaMessage,
  onAttach,
  attachAria,
  modelChoices = [],
  modelValue = '',
  onModelChange,
  sendingLabel,
  toolbarControls = false,
}: ChatComposerProps) {
  const { t } = useTranslation();
  const showModel = modelChoices.length > 0 && onModelChange;
  // Empty value = current default (Local/Ollama). Avoid a duplicate "Local" option.
  const listedModels = modelChoices.filter((name) => name !== 'ollama');

  const attachButton = onAttach ? (
    <button
      type="button"
      className="chat-composer__attach"
      aria-label={attachAria || t('landingChat.attachAria')}
      title={attachAria || t('landingChat.attachAria')}
      onClick={onAttach}
      disabled={disabled}
    >
      <PaperclipIcon aria-hidden="true" />
    </button>
  ) : null;

  const modelSelect = showModel ? (
    <select
      className="chat-composer__model"
      value={modelValue}
      onChange={(event) => onModelChange(event.target.value)}
      disabled={disabled}
      aria-label={t('assistant.chatModel')}
    >
      <option value="">{t('assistant.modelLocal')}</option>
      {listedModels.map((name) => (
        <option key={name} value={name}>
          {modelLabel(name, t)}
        </option>
      ))}
    </select>
  ) : null;

  const sendButton = (
    <button
      type="submit"
      className="chat-composer__send"
      disabled={disabled || !canSend}
      aria-label={t('common.send')}
      title={t('common.send')}
    >
      {sendingLabel ?? <SendIcon aria-hidden="true" />}
    </button>
  );

  if (toolbarControls) {
    return (
      <form className="chat-composer chat-composer--toolbar" onSubmit={onSubmit} dir="ltr">
        <div className="chat-composer__row chat-composer__row--toolbar">
          {attachButton}
          <div className="chat-composer__field">
            <input
              type="text"
              dir="auto"
              value={value}
              onChange={(event) => onChange(event.target.value)}
              placeholder={placeholder}
              aria-label={ariaMessage}
              disabled={disabled}
            />
          </div>
          <div className="chat-composer__actions">
            {modelSelect}
            {sendButton}
          </div>
        </div>
      </form>
    );
  }

  return (
    <form className="chat-composer" onSubmit={onSubmit}>
      <div className="chat-composer__row">
        {attachButton}

        <div className="chat-composer__field">
          <input
            type="text"
            value={value}
            onChange={(event) => onChange(event.target.value)}
            placeholder={placeholder}
            aria-label={ariaMessage}
            disabled={disabled}
          />
          {modelSelect}
          {sendButton}
        </div>
      </div>
    </form>
  );
}
