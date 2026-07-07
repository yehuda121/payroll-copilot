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

export function GuestWorkspace({ mode, assistantContext, onFollowUp }: GuestWorkspaceProps) {
  return (
    <div className="guest-workspace">
      {mode === 'assistant' ? (
        <GuestChatPanel
          title="Payroll Assistant"
          intro="Ask payroll and employee-rights questions using approved internal sources only."
          validationRunId={assistantContext?.validationRunId}
          documentIds={assistantContext?.documentIds ?? []}
        />
      ) : (
        <ValidationWizard onAskFollowUp={onFollowUp} />
      )}
    </div>
  );
}
