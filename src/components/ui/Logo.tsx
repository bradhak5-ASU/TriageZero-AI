interface LogoProps {
  size?: number;
  withText?: boolean;
}

export function Logo({ size = 30, withText = true }: LogoProps) {
  return (
    <>
      <svg
        width={size}
        height={size}
        viewBox="0 0 32 32"
        role="img"
        aria-label="TriageZero logo"
        style={{ flexShrink: 0 }}
      >
        <rect width="32" height="32" rx="7" fill="var(--bg-sunken)" stroke="var(--border-strong)" />
        <circle cx="16" cy="16" r="9" fill="none" stroke="var(--accent)" strokeWidth="2.2" />
        <circle cx="16" cy="16" r="2.6" fill="var(--accent)" />
        <path
          d="M16 4v5M16 23v5M4 16h5M23 16h5"
          stroke="var(--accent)"
          strokeWidth="2.2"
          strokeLinecap="round"
        />
      </svg>
      {withText && (
        <div className="brand-text">
          <div className="brand-name">TriageZero</div>
          <div className="brand-tagline">Autonomous Failure Intelligence</div>
        </div>
      )}
    </>
  );
}
