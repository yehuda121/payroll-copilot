import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { ANALYTICS_CHART_COLORS } from '../chartColors';

export type LineSeriesConfig = {
  dataKey: string;
  name: string;
  color?: string;
  strokeDasharray?: string;
};

type LineChartCardProps = {
  title: string;
  data: Array<Record<string, string | number | null>>;
  xKey: string;
  series: LineSeriesConfig[];
  yLabel?: string;
};

export function LineChartCard({ title, data, xKey, series, yLabel }: LineChartCardProps) {
  return (
    <section className="analytics-chart-card" aria-label={title}>
      <h2>{title}</h2>
      <div className="analytics-chart-card__body">
        <ResponsiveContainer width="100%" height="100%" minHeight={240}>
          <LineChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(102,112,133,0.25)" />
            <XAxis dataKey={xKey} tick={{ fontSize: 12 }} />
            <YAxis
              tick={{ fontSize: 12 }}
              label={
                yLabel
                  ? { value: yLabel, angle: -90, position: 'insideLeft', style: { fontSize: 11 } }
                  : undefined
              }
            />
            <Tooltip />
            <Legend />
            {series.map((item, index) => (
              <Line
                key={item.dataKey}
                type="monotone"
                dataKey={item.dataKey}
                name={item.name}
                stroke={item.color ?? ANALYTICS_CHART_COLORS.series[index % ANALYTICS_CHART_COLORS.series.length]}
                strokeWidth={2}
                strokeDasharray={item.strokeDasharray}
                connectNulls={false}
                dot={{ r: 3 }}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
