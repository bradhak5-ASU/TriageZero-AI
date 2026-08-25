interface StackBarProps {
  segments: Array<{ name: string; count: number; color: string }>;
  ariaLabel: string;
}

export function StackBar({ segments, ariaLabel }: StackBarProps) {
  const total = segments.reduce((sum, s) => sum + s.count, 0) || 1;
  const visible = segments.filter((s) => s.count > 0);
  return (
    <div>
      <div className="stackbar" role="img" aria-label={ariaLabel}>
        {visible.map((s) => (
          <span
            key={s.name}
            style={{ width: `${(s.count / total) * 100}%`, background: s.color }}
            title={`${s.name}: ${s.count}`}
          />
        ))}
      </div>
      <div className="legend">
        {segments.map((s) => (
          <span key={s.name} className="legend__item">
            <span className="legend__swatch" style={{ background: s.color }} />
            {s.name} · {s.count}
          </span>
        ))}
      </div>
    </div>
  );
}
