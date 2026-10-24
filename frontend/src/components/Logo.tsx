import { cx } from './ui'

/** Typographic wordmark: "AR&MS" with a teal bar, product name underneath. */
export function Logo({ inverted, compact }: { inverted?: boolean; compact?: boolean }) {
  return (
    <div className="flex items-center gap-2.5 select-none">
      <svg viewBox="0 0 64 64" className="size-8 shrink-0" aria-hidden>
        <rect width="64" height="64" rx="14" fill={inverted ? '#ffffff' : '#0F1E3A'} fillOpacity={inverted ? 0.08 : 1} />
        <text x="32" y="38" textAnchor="middle" fontSize="23" fontWeight="800" fill="#fff"
          fontFamily="Inter, 'Segoe UI', Arial, sans-serif" letterSpacing="-0.5">AR</text>
        <rect x="18" y="45" width="28" height="4" rx="2" fill="#14B8A6" />
      </svg>
      {!compact && (
        <div className="leading-tight">
          <p className={cx('text-sm font-bold tracking-wide', inverted ? 'text-white' : 'text-ink')}>
            AR&amp;MS <span className="font-semibold text-[#14B8A6]">HCM Lite</span>
          </p>
          <p className={cx('text-[10px] uppercase tracking-[0.14em]', inverted ? 'text-white/60' : 'text-muted')}>
            Management Company
          </p>
        </div>
      )}
    </div>
  )
}
