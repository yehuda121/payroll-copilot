import { useTranslation } from 'react-i18next';
import { APP_NAME } from '../../config/brand';
import { useAppLocale } from '../../hooks/useAppLocale';
import { SparklesIcon } from '../ui/icons';

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
  /** Full i18n keys for suggestion chips. */
  suggestionKeys?: readonly string[];
  /** When provided, suggestions become clickable quick-starts. */
  onSuggestionSelect?: (text: string) => void;
  disabled?: boolean;
};

/**
 * Premium empty-state welcome for AI chat surfaces.
 * Copy and direction follow i18n; layout is language-agnostic.
 */
export function ChatWelcome({
  namespace = 'landingChat.welcome',
  suggestionKeys = LANDING_SUGGESTIONS,
  onSuggestionSelect,
  disabled = false,
}: ChatWelcomeProps = {}) {
  const { t } = useTranslation();
  const { dir } = useAppLocale();

  return (
    <div className="chat-welcome" dir={dir}>
      <div className="chat-welcome__orb" aria-hidden="true">
        <span className="chat-welcome__orb-glow" />
        <span className="chat-welcome__orb-core">
          <SparklesIcon size={28} />
        </span>
      </div>

      <p className="chat-welcome__brand">
        <bdi>{APP_NAME}</bdi>
        <span className="chat-welcome__online" aria-hidden="true" />
        <span className="chat-welcome__online-label">{t('assistant.online')}</span>
      </p>

      <p className="chat-welcome__greeting">{t(`${namespace}.greeting`)}</p>
      <h2 className="chat-welcome__title">
        <span className="chat-welcome__title-text">{t(`${namespace}.title`)}</span>
      </h2>
      <p className="chat-welcome__intro" dir="auto">
        {t(`${namespace}.intro`)}
      </p>

      <div className="chat-welcome__chips" role="list">
        {suggestionKeys.map((key) => {
          const label = t(key);
          if (onSuggestionSelect) {
            return (
              <button
                key={key}
                type="button"
                role="listitem"
                className="chat-welcome__chip"
                disabled={disabled}
                onClick={() => onSuggestionSelect(label)}
              >
                <span dir="auto">{label}</span>
              </button>
            );
          }
          return (
            <span key={key} role="listitem" className="chat-welcome__chip chat-welcome__chip--static">
              <span dir="auto">{label}</span>
            </span>
          );
        })}
      </div>

      <p className="chat-welcome__hint">{t(`${namespace}.hint`)}</p>
    </div>
  );
}
