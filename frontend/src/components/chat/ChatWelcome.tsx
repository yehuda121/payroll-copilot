import { useTranslation } from 'react-i18next';
import { useAppLocale } from '../../hooks/useAppLocale';

const LANDING_SUGGESTIONS = [
  'landingChat.welcome.suggestions.laborLaw',
  'landingChat.welcome.suggestions.payslipReview',
  'landingChat.welcome.suggestions.salaryComponents',
  'landingChat.welcome.suggestions.employeeRights',
  'landingChat.welcome.suggestions.leaveOvertime',
  'landingChat.welcome.suggestions.documents',
] as const;

export const EMPLOYEE_CHAT_SUGGESTIONS = [
  'employee.chat.welcome.suggestions.payslips',
  'employee.chat.welcome.suggestions.salaryComponents',
  'employee.chat.welcome.suggestions.documents',
  'employee.chat.welcome.suggestions.leaveOvertime',
  'employee.chat.welcome.suggestions.laborLaw',
  'employee.chat.welcome.suggestions.validation',
] as const;

type ChatWelcomeProps = {
  /** i18n prefix containing greeting/title/intro/hint. Defaults to landing. */
  namespace?: string;
  /** Full i18n keys for bullet suggestions. */
  suggestionKeys?: readonly string[];
};

/**
 * Empty-state welcome block for AI chat surfaces.
 * Copy is driven by i18n namespace so Landing and Employee can share the visual.
 * Text direction follows locale; physical chat placement is controlled by parents.
 */
export function ChatWelcome({
  namespace = 'landingChat.welcome',
  suggestionKeys = LANDING_SUGGESTIONS,
}: ChatWelcomeProps = {}) {
  const { t } = useTranslation();
  const { dir } = useAppLocale();

  return (
    <div className="chat-welcome" dir={dir}>
      <p className="chat-welcome__greeting">{t(`${namespace}.greeting`)}</p>
      <h2 className="chat-welcome__title">{t(`${namespace}.title`)}</h2>
      <p className="chat-welcome__intro">{t(`${namespace}.intro`)}</p>
      <ul className="chat-welcome__list">
        {suggestionKeys.map((key) => (
          <li key={key}>{t(key)}</li>
        ))}
      </ul>
      <p className="chat-welcome__hint">{t(`${namespace}.hint`)}</p>
    </div>
  );
}
