import type { FormEvent, ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

export type ChatComposerProps = {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (event: FormEvent) => void;
  disabled?: boolean;
  canSend: boolean;
  placeholder: string;
  ariaMessage: string;
  /** When set, + opens the existing upload flow. */
  onAttach?: () => void;
  attachAria?: string;
  modelChoices?: string[];
  modelValue?: string;
  onModelChange?: (value: string) => void;
  sendingLabel?: ReactNode;
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
}: ChatComposerProps) {
  const { t } = useTranslation();
  const showModel = modelChoices.length > 0 && onModelChange;
  // Empty value = current default (Local/Ollama). Avoid a duplicate "Local" option.
  const listedModels = modelChoices.filter((name) => name !== 'ollama');

  return (
    <form className="chat-composer" onSubmit={onSubmit}>
      <div className="chat-composer__row">
        {onAttach ? (
          <button
            type="button"
            className="chat-composer__attach"
            aria-label={attachAria || t('landingChat.attachAria')}
            title={attachAria || t('landingChat.attachAria')}
            onClick={onAttach}
            disabled={disabled}
          >
            +
          </button>
        ) : null}

        <div className="chat-composer__field">
          <input
            type="text"
            value={value}
            onChange={(event) => onChange(event.target.value)}
            placeholder={placeholder}
            aria-label={ariaMessage}
            disabled={disabled}
          />
          {showModel ? (
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
          ) : null}
          <button
            type="submit"
            className="chat-composer__send"
            disabled={disabled || !canSend}
            aria-label={t('common.send')}
            title={t('common.send')}
          >
            {sendingLabel ?? (
              <span className="chat-composer__send-icon" aria-hidden="true">
                ↑
              </span>
            )}
          </button>
        </div>
      </div>
    </form>
  );
}
