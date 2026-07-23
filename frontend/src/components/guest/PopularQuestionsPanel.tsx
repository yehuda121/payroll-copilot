import { useTranslation } from 'react-i18next';
import { POPULAR_QUESTIONS } from '../../data/popularQuestions';

type PopularQuestionsPanelProps = {
  disabled?: boolean;
  onSelect: (question: string) => void;
};

export function PopularQuestionsPanel({ disabled, onSelect }: PopularQuestionsPanelProps) {
  const { t } = useTranslation();
  const heading = t('landingChat.popularHeading');

  return (
    <aside className="popular-questions" aria-label={heading}>
      <h2 className="popular-questions__title">{heading}</h2>
      <ul className="popular-questions__list">
        {POPULAR_QUESTIONS.map((item) => {
          const question = t(item.questionKey);
          return (
            <li key={item.id}>
              <button
                type="button"
                className="popular-questions__item"
                disabled={disabled}
                onClick={() => {
                  onSelect(question);
                }}
              >
                <span className="popular-questions__text">{question}</span>
                <span className="popular-questions__count">{item.count}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </aside>
  );
}
