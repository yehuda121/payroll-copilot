import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { ANALYTICS_CHART_COLORS } from '../chartColors';

export type BarSeriesConfig = {
  dataKey: string;
  name: string;
  color?: string;
  stackId?: string;
};

type BarChartCardProps = {
  title: string;
  data: Array<Record<string, string | number | null>>;
  xKey: string;
  series: BarSeriesConfig[];
  layout?: 'horizontal' | 'vertical';
};

export function BarChartCard({
  title,
  data,
  xKey,
  series,
  layout = 'horizontal',
}: BarChartCardProps) {
  const isVertical = layout === 'vertical';

  return (
    <section className="analytics-chart-card" aria-label={title}>
      <h2>{title}</h2>
      <div className="analytics-chart-card__body">
        <ResponsiveContainer width="100%" height="100%" minHeight={240}>
          <BarChart
            data={data}
            layout={isVertical ? 'vertical' : 'horizontal'}
            margin={{ top: 8, right: 12, left: 8, bottom: 0 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(102,112,133,0.25)" />
            {isVertical ? (
              <>
                <XAxis type="number" tick={{ fontSize: 12 }} />
                <YAxis type="category" dataKey={xKey} width={110} tick={{ fontSize: 11 }} />
              </>
            ) : (
              <>
                <XAxis dataKey={xKey} tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} />
              </>
            )}
            <Tooltip />
            <Legend />
            {series.map((item, index) => (
              <Bar
                key={item.dataKey}
                dataKey={item.dataKey}
                name={item.name}
                stackId={item.stackId}
                fill={item.color ?? ANALYTICS_CHART_COLORS.series[index % ANALYTICS_CHART_COLORS.series.length]}
                radius={item.stackId ? 0 : [4, 4, 0, 0]}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
