import { GuestLandingChat } from '../../features/guest/landing/GuestLandingChat';
import '../../features/guest/guest.css';
import '../../layouts/PublicLayout.css';

/**
 * Public landing — single AI-first conversation.
 * Document upload, extraction review, confirmation, and validation all happen in-chat.
 * ValidationWizard remains available elsewhere but is not linked from this page.
 */
export function LandingPage() {
  return (
    <div className="landing landing--chat-first">
      <GuestLandingChat />
    </div>
  );
}
