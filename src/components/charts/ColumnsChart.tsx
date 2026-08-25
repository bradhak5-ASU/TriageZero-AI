interface ColumnsChartProps {
  data: Array<{ label: string; count: number }>;
  ariaLabel: string;
}

export function ColumnsChart({ data, ariaLabel }: ColumnsChartProps) {
  const max = Math.max(...data.map((d) => d.count), 1);
  return (
    <div className="columns-chart" role="img" aria-label={ariaLabel}>
      {data.map((d) => (
        <div key={d.label} className="columns-chart__col">
          <span className="columns-chart__value">{d.count}</span>
          <span
            className="columns-chart__bar"
            style={{ height: `${Math.max((d.count / max) * 100, 4)}%` }}
            title={`${d.label}: ${d.count}`}
          />
          <span className="columns-chart__label">{d.label}</span>
        </div>
      ))}
    </div>
  );
}
