import { useEffect, useId, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import './landing-chat.css';

type FieldAiPopoverProps = {
  explanation: string;
  label: string;
};

/** Tiny local popover — does not send a chat message or call the LLM. */
export function FieldAiPopover({ explanation, label }: FieldAiPopoverProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLSpanElement | null>(null);
  const panelId = useId();

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onPointer);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onPointer);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  if (!explanation.trim()) return null;

  return (
    <span className="field-ai-popover" ref={rootRef}>
      <button
        type="button"
        className="field-ai-popover__trigger"
        aria-label={t('landingChat.aiExplainAria', { field: label })}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={(event) => {
          event.preventDefault();
          event.stopPropagation();
          setOpen((prev) => !prev);
        }}
      >
        <span aria-hidden="true">✦</span>
      </button>
      {open && (
        <span
          id={panelId}
          role="tooltip"
          className="field-ai-popover__panel"
        >
          <span className="field-ai-popover__label">{t('landingChat.aiExplanation')}</span>
          {explanation}
        </span>
      )}
    </span>
  );
}
