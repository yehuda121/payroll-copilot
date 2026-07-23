import { useTranslation } from 'react-i18next';

const SUGGESTION_KEYS = [
  'landingChat.welcome.suggestions.laborLaw',
  'landingChat.welcome.suggestions.payslipReview',
  'landingChat.welcome.suggestions.salaryComponents',
  'landingChat.welcome.suggestions.employeeRights',
  'landingChat.welcome.suggestions.leaveOvertime',
  'landingChat.welcome.suggestions.documents',
] as const;

type ChatWelcomeProps = {
  onSuggestionSelect?: (text: string) => void;
};

/**
 * Empty-state welcome block for AI chat surfaces.
 * Suggestions are listed as plain bullets (optional prompts, not required).
 */
export function ChatWelcome(_props: ChatWelcomeProps = {}) {
  const { t } = useTranslation();

  return (
    <div className="chat-welcome">
      <p className="chat-welcome__greeting">{t('landingChat.welcome.greeting')}</p>
      <h2 className="chat-welcome__title">{t('landingChat.welcome.title')}</h2>
      <p className="chat-welcome__intro">{t('landingChat.welcome.intro')}</p>
      <ul className="chat-welcome__list">
        {SUGGESTION_KEYS.map((key) => (
          <li key={key}>{t(key)}</li>
        ))}
      </ul>
      <p className="chat-welcome__hint">{t('landingChat.welcome.hint')}</p>
    </div>
  );
}
