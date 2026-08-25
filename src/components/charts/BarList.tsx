interface BarListProps {
  items: Array<{ name: string; count: number; color?: string }>;
  ariaLabel: string;
}

export function BarList({ items, ariaLabel }: BarListProps) {
  const max = Math.max(...items.map((i) => i.count), 1);
  return (
    <div className="barlist" role="img" aria-label={ariaLabel}>
      {items.map((item) => (
        <div key={item.name} className="barlist__row">
          <span className="name" title={item.name}>
            {item.name}
          </span>
          <span className="barlist__track">
            <span
              className="barlist__fill"
              style={{
                width: `${(item.count / max) * 100}%`,
                background: item.color ?? 'var(--accent)',
              }}
            />
          </span>
          <span className="barlist__count">{item.count}</span>
        </div>
      ))}
    </div>
  );
}
