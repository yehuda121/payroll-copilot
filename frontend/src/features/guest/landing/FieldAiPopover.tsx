import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import './landing-chat.css';

type FieldAiPopoverProps = {
  explanation: string;
  label: string;
};

type PanelCoords = {
  top: number;
  left: number;
  maxWidth: number;
};

function isRtlDocument(): boolean {
  if (typeof document === 'undefined') return false;
  return document.documentElement.getAttribute('dir') === 'rtl';
}

function computePanelPosition(
  trigger: DOMRect,
  panelWidth: number,
  panelHeight: number,
): PanelCoords {
  const gap = 8;
  const viewportPad = 8;
  const maxWidth = Math.min(16 * 16, window.innerWidth - viewportPad * 2);
  const width = Math.min(panelWidth || maxWidth, maxWidth);

  let top = trigger.bottom + gap;
  if (top + panelHeight > window.innerHeight - viewportPad) {
    top = Math.max(viewportPad, trigger.top - panelHeight - gap);
  }

  const rtl = isRtlDocument();
  let left = rtl ? trigger.right - width : trigger.left;
  if (left < viewportPad) left = viewportPad;
  if (left + width > window.innerWidth - viewportPad) {
    left = Math.max(viewportPad, window.innerWidth - width - viewportPad);
  }

  return { top, left, maxWidth };
}

/** Tiny local popover — does not send a chat message or call the LLM. */
export function FieldAiPopover({ explanation, label }: FieldAiPopoverProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [coords, setCoords] = useState<PanelCoords | null>(null);
  const rootRef = useRef<HTMLSpanElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const panelRef = useRef<HTMLSpanElement | null>(null);
  const panelId = useId();

  const updatePosition = useCallback(() => {
    const trigger = triggerRef.current?.getBoundingClientRect();
    if (!trigger) return;
    const panelRect = panelRef.current?.getBoundingClientRect();
    const next = computePanelPosition(
      trigger,
      panelRect?.width ?? 16 * 16,
      panelRect?.height ?? 80,
    );
    setCoords(next);
  }, []);

  useLayoutEffect(() => {
    if (!open) {
      setCoords(null);
      return;
    }
    updatePosition();
    // Second pass after panel mounts with real dimensions.
    const frame = window.requestAnimationFrame(updatePosition);
    return () => window.cancelAnimationFrame(frame);
  }, [open, updatePosition]);

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: MouseEvent) => {
      const target = event.target as Node;
      if (rootRef.current?.contains(target) || panelRef.current?.contains(target)) return;
      setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    const onReposition = () => updatePosition();
    document.addEventListener('mousedown', onPointer);
    document.addEventListener('keydown', onKey);
    window.addEventListener('resize', onReposition);
    window.addEventListener('scroll', onReposition, true);
    return () => {
      document.removeEventListener('mousedown', onPointer);
      document.removeEventListener('keydown', onKey);
      window.removeEventListener('resize', onReposition);
      window.removeEventListener('scroll', onReposition, true);
    };
  }, [open, updatePosition]);

  if (!explanation.trim()) return null;

  return (
    <span className="field-ai-popover" ref={rootRef}>
      <button
        ref={triggerRef}
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
      {open &&
        createPortal(
          <span
            ref={panelRef}
            id={panelId}
            role="tooltip"
            className="field-ai-popover__panel field-ai-popover__panel--portal"
            style={
              coords
                ? {
                    top: coords.top,
                    left: coords.left,
                    maxWidth: coords.maxWidth,
                  }
                : { visibility: 'hidden', top: 0, left: 0 }
            }
          >
            <span className="field-ai-popover__label">{t('landingChat.aiExplanation')}</span>
            {explanation}
          </span>,
          document.body,
        )}
    </span>
  );
}
