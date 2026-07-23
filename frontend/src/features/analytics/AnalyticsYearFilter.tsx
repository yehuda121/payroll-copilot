type AnalyticsYearFilterProps = {
  id?: string;
  label: string;
  year: number;
  years: number[];
  onChange: (year: number) => void;
  disabled?: boolean;
};

export function AnalyticsYearFilter({
  id = 'analytics-year',
  label,
  year,
  years,
  onChange,
  disabled = false,
}: AnalyticsYearFilterProps) {
  const options = Array.from(new Set([...years, year])).sort((a, b) => b - a);

  return (
    <label className="analytics-year-filter" htmlFor={id}>
      <span>{label}</span>
      <select
        id={id}
        value={year}
        disabled={disabled}
        onChange={(event) => onChange(Number(event.target.value))}
      >
        {options.map((item) => (
          <option key={item} value={item}>
            {item}
          </option>
        ))}
      </select>
    </label>
  );
}
