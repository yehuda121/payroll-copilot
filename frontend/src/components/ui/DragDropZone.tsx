import { useRef, useState, type ChangeEvent, type DragEvent } from 'react';
import { useTranslation } from 'react-i18next';
import './ui.css';

type DragDropZoneProps = {
  accept: string;
  selectedFileName?: string;
  errorMessage?: string;
  onFileSelected: (file: File) => void;
  onRemove?: () => void;
  title?: string;
  hint?: string;
};

export function DragDropZone({
  accept,
  selectedFileName,
  errorMessage,
  onFileSelected,
  onRemove,
  title,
  hint,
}: DragDropZoneProps) {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  const handleFiles = (files: FileList | null) => {
    const file = files?.[0];
    if (file) {
      onFileSelected(file);
    }
  };

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDragging(false);
    handleFiles(event.dataTransfer.files);
  };

  const onChange = (event: ChangeEvent<HTMLInputElement>) => {
    handleFiles(event.target.files);
    event.target.value = '';
  };

  const zoneTitle = title ?? t('validate.dragTitle');
  const zoneHint = hint ?? t('validate.dragHint');

  return (
    <div className="drag-drop">
      <div
        className={`drag-drop__zone ${isDragging ? 'is-dragging' : ''} ${selectedFileName ? 'has-file' : ''}`}
        role="button"
        tabIndex={0}
        aria-label={selectedFileName ? `${zoneTitle}: ${selectedFileName}` : zoneTitle}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            inputRef.current?.click();
          }
        }}
        onClick={() => inputRef.current?.click()}
        onDragEnter={(event) => {
          event.preventDefault();
          setIsDragging(true);
        }}
        onDragOver={(event) => {
          event.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={(event) => {
          if (event.currentTarget.contains(event.relatedTarget as Node)) return;
          setIsDragging(false);
        }}
        onDrop={onDrop}
      >
        <strong>{selectedFileName ?? zoneTitle}</strong>
        <span>{zoneHint}</span>
        <span className="btn btn--secondary">{t('validate.browse')}</span>
      </div>
      {selectedFileName && onRemove && (
        <button type="button" className="btn btn--ghost" onClick={onRemove}>
          {t('common.removeFile')}
        </button>
      )}
      {errorMessage && <p className="drag-drop__error">{errorMessage}</p>}
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        className="drag-drop__input"
        onChange={onChange}
      />
    </div>
  );
}
