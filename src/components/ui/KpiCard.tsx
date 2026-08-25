import { Minus, TrendingDown, TrendingUp } from 'lucide-react';

interface KpiCardProps {
  label: string;
  value: string;
  caption: string;
  tooltip: string;
  icon: React.ReactNode;
  trend?: { direction: 'up' | 'down' | 'flat'; text: string; positive?: boolean };
}

export function KpiCard({ label, value, caption, tooltip, icon, trend }: KpiCardProps) {
  const TrendIcon =
    trend?.direction === 'up' ? TrendingUp : trend?.direction === 'down' ? TrendingDown : Minus;
  const trendClass =
    !trend || trend.direction === 'flat'
      ? 'trend--flat'
      : trend.positive
        ? 'trend--up'
        : 'trend--down';

  return (
    <div className="card kpi tip" data-tip={tooltip} tabIndex={0}>
      <div className="kpi__top">
        <span>{label}</span>
        {icon}
      </div>
      <div className="kpi__value">{value}</div>
      <div className="kpi__meta">
        {trend && (
          <span className={`trend ${trendClass}`}>
            <TrendIcon size={12} aria-hidden />
            {trend.text}
          </span>
        )}
        <span>{caption}</span>
      </div>
    </div>
  );
}
