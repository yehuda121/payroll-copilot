import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';
import { ANALYTICS_CHART_COLORS } from '../chartColors';

type DonutChartCardProps = {
  title: string;
  data: Array<{ name: string; value: number }>;
  nameKey?: string;
  valueKey?: string;
};

export function DonutChartCard({
  title,
  data,
  nameKey = 'name',
  valueKey = 'value',
}: DonutChartCardProps) {
  return (
    <section className="analytics-chart-card" aria-label={title}>
      <h2>{title}</h2>
      <div className="analytics-chart-card__body">
        <ResponsiveContainer width="100%" height="100%" minHeight={240}>
          <PieChart>
            <Pie
              data={data}
              dataKey={valueKey}
              nameKey={nameKey}
              cx="50%"
              cy="50%"
              innerRadius={55}
              outerRadius={90}
              paddingAngle={2}
            >
              {data.map((entry, index) => (
                <Cell
                  key={`${entry.name}-${index}`}
                  fill={ANALYTICS_CHART_COLORS.series[index % ANALYTICS_CHART_COLORS.series.length]}
                />
              ))}
            </Pie>
            <Tooltip />
            <Legend />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
