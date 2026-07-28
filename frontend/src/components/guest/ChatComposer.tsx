import {
  useEffect,
  useRef,
  type FormEvent,
  type KeyboardEvent,
  type ReactNode,
} from 'react';
import { useTranslation } from 'react-i18next';
import { FREE_TEXT_MAX_LENGTH, clampFreeTextInput } from '../../lib/validation';
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
   * Product shell layout: attach | textarea | model + send.
   * Same markup for all locales — direction follows document.
   */
  toolbarControls?: boolean;
};

function modelLabel(name: string, t: (key: string) => string): string {
  if (name === 'ollama') return t('assistant.modelLocal');
  if (name === 'openai') return 'OpenAI';
  if (name === 'bedrock') return 'Bedrock';
  return name;
}

function resizeTextarea(el: HTMLTextAreaElement | null) {
  if (!el) return;
  el.style.height = '0px';
  const next = Math.min(el.scrollHeight, 160);
  el.style.height = `${Math.max(44, next)}px`;
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
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const showModel = modelChoices.length > 0 && onModelChange;
  const listedModels = modelChoices.filter((name) => name !== 'ollama');

  useEffect(() => {
    resizeTextarea(textareaRef.current);
  }, [value]);

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== 'Enter' || event.shiftKey) return;
    if (event.nativeEvent.isComposing) return;
    event.preventDefault();
    if (disabled || !canSend) return;
    event.currentTarget.form?.requestSubmit();
  };

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

  const field = (
    <div className="chat-composer__field">
      <textarea
        ref={textareaRef}
        rows={1}
        dir="auto"
        value={value}
        maxLength={FREE_TEXT_MAX_LENGTH.chatMessage}
        onChange={(event) =>
          onChange(
            clampFreeTextInput(event.target.value, FREE_TEXT_MAX_LENGTH.chatMessage, {
              allowNewlines: true,
            }),
          )
        }
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        aria-label={ariaMessage}
        disabled={disabled}
      />
      {!toolbarControls ? (
        <div className="chat-composer__inline-actions">
          {modelSelect}
          {sendButton}
        </div>
      ) : null}
    </div>
  );

  return (
    <form
      className={`chat-composer${toolbarControls ? ' chat-composer--toolbar' : ''}`}
      onSubmit={onSubmit}
    >
      <div className={`chat-composer__row${toolbarControls ? ' chat-composer__row--toolbar' : ''}`}>
        {attachButton}
        {field}
        {toolbarControls ? (
          <div className="chat-composer__actions">
            {modelSelect}
            {sendButton}
          </div>
        ) : null}
      </div>
      <p className="chat-composer__hint" dir="auto">
        {t('assistant.composerHint')}
      </p>
    </form>
  );
}
