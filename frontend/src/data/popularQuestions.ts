export const POPULAR_QUESTIONS = [
  {
    id: 'pq-1',
    questionKey: 'landingChat.popular.pq1',
    count: 842,
  },
  {
    id: 'pq-2',
    questionKey: 'landingChat.popular.pq2',
    count: 731,
  },
  {
    id: 'pq-3',
    questionKey: 'landingChat.popular.pq3',
    count: 615,
  },
  {
    id: 'pq-4',
    questionKey: 'landingChat.popular.pq4',
    count: 504,
  },
  {
    id: 'pq-5',
    questionKey: 'landingChat.popular.pq5',
    count: 389,
  },
] as const;

export type PopularQuestionItem = (typeof POPULAR_QUESTIONS)[number];
