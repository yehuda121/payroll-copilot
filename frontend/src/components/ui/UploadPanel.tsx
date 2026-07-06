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
  onFilesSelected?: (slotId: string, file: File) => void;
};

export function UploadPanel({ slots, onFilesSelected }: UploadPanelProps) {
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
            <span>Click to select file</span>
            <span className="upload-panel__hint">{slot.accept}</span>
          </button>
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
