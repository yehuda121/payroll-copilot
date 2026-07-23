import { POPULAR_QUESTIONS } from '../../data/popularQuestions';

type PopularQuestionsPanelProps = {
  disabled?: boolean;
  onSelect: (question: string) => void;
};

export function PopularQuestionsPanel({ disabled, onSelect }: PopularQuestionsPanelProps) {
  return (
    <aside className="popular-questions" aria-label="שאלות נפוצות">
      <h2 className="popular-questions__title">שאלות נפוצות</h2>
      <ul className="popular-questions__list">
        {POPULAR_QUESTIONS.map((item) => (
          <li key={item.id}>
            <button
              type="button"
              className="popular-questions__item"
              disabled={disabled}
              onClick={() => {
                onSelect(item.question);
              }}
            >
              <span className="popular-questions__text">{item.question}</span>
              <span className="popular-questions__count">{item.count}</span>
            </button>
          </li>
        ))}
      </ul>
    </aside>
  );
}
