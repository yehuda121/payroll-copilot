import { GuestChatPanel } from '../../components/guest/GuestChatPanel';
import { ValidationWizard } from './validation/ValidationWizard';
import './guest.css';

export type GuestWorkspaceMode = 'assistant' | 'validate';

export type AssistantFollowUpContext = {
  validationRunId: string;
  documentIds: string[];
};

type GuestWorkspaceProps = {
  mode: GuestWorkspaceMode;
  assistantContext?: AssistantFollowUpContext;
  onFollowUp?: (context: AssistantFollowUpContext) => void;
};

/** Dedicated workspace shell for validate flow (and optional isolated chat). */
export function GuestWorkspace({ mode, assistantContext, onFollowUp }: GuestWorkspaceProps) {
  return (
    <div className="guest-workspace">
      {mode === 'assistant' ? (
        <GuestChatPanel
          validationRunId={assistantContext?.validationRunId}
          documentIds={assistantContext?.documentIds ?? []}
        />
      ) : (
        <ValidationWizard onAskFollowUp={onFollowUp} />
      )}
    </div>
  );
}
