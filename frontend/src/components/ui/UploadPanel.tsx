import { useRef, type ChangeEvent } from 'react';
import './ui.css';

type UploadSlot = {
  id: string;
  label: string;
  accept: string;
  optional?: boolean;
};

type UploadPanelProps = {
  slots: UploadSlot[];
  selectedFileName?: string;
  errorMessage?: string;
  onFilesSelected?: (slotId: string, file: File) => void;
  onRemove?: (slotId: string) => void;
};

export function UploadPanel({
  slots,
  selectedFileName,
  errorMessage,
  onFilesSelected,
  onRemove,
}: UploadPanelProps) {
  const inputRefs = useRef<Record<string, HTMLInputElement | null>>({});

  const handleChange = (slotId: string) => (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file && onFilesSelected) {
      onFilesSelected(slotId, file);
    }
  };

  return (
    <div className="upload-panel">
      {slots.map((slot) => (
        <div key={slot.id} className="upload-panel__slot">
          <div className="upload-panel__slot-header">
            <strong>{slot.label}</strong>
            {slot.optional && <span className="upload-panel__optional">Optional</span>}
          </div>
          <button
            type="button"
            className="upload-panel__dropzone"
            onClick={() => inputRefs.current[slot.id]?.click()}
          >
            <span>{selectedFileName ? selectedFileName : 'Click to select file'}</span>
            <span className="upload-panel__hint">{slot.accept}</span>
          </button>
          {selectedFileName && onRemove && (
            <button type="button" className="btn btn--ghost" onClick={() => onRemove(slot.id)}>
              Remove file
            </button>
          )}
          {errorMessage && <p className="document-slot__error">{errorMessage}</p>}
          <input
            ref={(el) => {
              inputRefs.current[slot.id] = el;
            }}
            type="file"
            accept={slot.accept}
            className="upload-panel__input"
            onChange={handleChange(slot.id)}
          />
        </div>
      ))}
    </div>
  );
}
