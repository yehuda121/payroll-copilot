export const POPULAR_QUESTIONS = [
  {
    id: 'pq-1',
    question: 'למה ירד לי מס הכנסה?',
    count: 842,
  },
  {
    id: 'pq-2',
    question: 'איך מחשבים שעות נוספות?',
    count: 731,
  },
  {
    id: 'pq-3',
    question: 'כמה ימי חופשה נשארו לי?',
    count: 615,
  },
  {
    id: 'pq-4',
    question: 'למה לא קיבלתי נסיעות?',
    count: 504,
  },
  {
    id: 'pq-5',
    question: 'מה המשמעות של רכיב בתלוש השכר?',
    count: 389,
  },
] as const;

export type PopularQuestionItem = (typeof POPULAR_QUESTIONS)[number];
