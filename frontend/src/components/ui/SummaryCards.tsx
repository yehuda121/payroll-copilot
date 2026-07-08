type SummaryCardItem = {
  id: string;
  label: string;
  value: string;
  tone?: 'passed' | 'unable' | 'issue' | 'neutral';
};

type SummaryCardsProps = {
  title: string;
  items: SummaryCardItem[];
};

export function SummaryCards({ title, items }: SummaryCardsProps) {
  return (
    <section className="summary-cards" aria-label={title}>
      <h3 className="summary-cards__heading">{title}</h3>
      <div className="summary-cards__grid">
        {items.map((item) => (
          <article key={item.id} className={`summary-card ${item.tone ? `summary-card--${item.tone}` : ''}`}>
            <p className="summary-card__label">{item.label}</p>
            <p className="summary-card__value">{item.value}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
