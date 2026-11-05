// Decorative traffic along the bottom of the screen: buses, CNGs, rickshaws, cars and bikes in both
// directions on a two-lane road. Pure CSS (no JS, no requests), behind all content, ignored by screen readers
// and not clickable. It stands still for people who ask their system to reduce motion (see globals.css).
// Slow, evenly spaced and few: gentle movement at the edge of vision, never a distraction.
const LANE_LEFT = [   // left-hand traffic: the near lane drives left → right
  { k: "bus", d: 64, delay: 0 },
  { k: "cng", d: 52, delay: -18 },
  { k: "rickshaw", d: 80, delay: -40 },
  { k: "car", d: 46, delay: -30 },
] as const;
const LANE_RIGHT = [
  { k: "car", d: 50, delay: -6 },
  { k: "bus", d: 70, delay: -35 },
  { k: "bike", d: 42, delay: -20 },
] as const;

function Vehicle({ k }: { k: string }) {
  // simple side views, 1 unit ≈ 10 cm; colours echo Dhaka's buses (green/red), CNGs (green) and rickshaws
  switch (k) {
    case "bus":
      return (
        <svg width="120" height="44" viewBox="0 0 120 44">
          <rect x="2" y="4" width="116" height="30" rx="6" fill="#0b6e4f" />
          <rect x="2" y="24" width="116" height="6" fill="#c0392b" />
          {[10, 30, 50, 70, 90].map((x) => (
            <rect key={x} x={x} y="9" width="16" height="11" rx="2" fill="#e6f4ee" />
          ))}
          <circle cx="24" cy="36" r="7" fill="#27272a" />
          <circle cx="96" cy="36" r="7" fill="#27272a" />
        </svg>
      );
    case "cng":
      return (
        <svg width="54" height="40" viewBox="0 0 54 40">
          <path d="M6 30 V14 Q8 4 24 4 H40 Q50 6 50 18 V30 Z" fill="#1f9d55" />
          <rect x="14" y="9" width="24" height="12" rx="2" fill="#e6f4ee" />
          <circle cx="12" cy="32" r="6" fill="#27272a" />
          <circle cx="44" cy="32" r="6" fill="#27272a" />
        </svg>
      );
    case "rickshaw":
      return (
        <svg width="62" height="46" viewBox="0 0 62 46">
          <path d="M30 8 Q42 0 54 8 L54 22 L30 22 Z" fill="#d97706" />
          <rect x="30" y="22" width="24" height="6" fill="#b45309" />
          <line x1="10" y1="34" x2="34" y2="26" stroke="#3f3f46" strokeWidth="3" />
          <circle cx="10" cy="36" r="8" fill="none" stroke="#27272a" strokeWidth="3" />
          <circle cx="46" cy="36" r="8" fill="none" stroke="#27272a" strokeWidth="3" />
        </svg>
      );
    case "bike":
      return (
        <svg width="46" height="36" viewBox="0 0 46 36">
          <path d="M10 26 L22 14 H32 L38 26" fill="none" stroke="#3f3f46" strokeWidth="4" />
          <circle cx="24" cy="8" r="5" fill="#2563eb" />
          <circle cx="9" cy="28" r="7" fill="none" stroke="#27272a" strokeWidth="3" />
          <circle cx="37" cy="28" r="7" fill="none" stroke="#27272a" strokeWidth="3" />
        </svg>
      );
    default:
      return (
        <svg width="70" height="34" viewBox="0 0 70 34">
          <path d="M4 24 V16 Q6 12 14 11 L22 4 H46 L56 11 Q66 12 66 18 V24 Z" fill="#64748b" />
          <path d="M25 7 H44 L51 12 H20 Z" fill="#e2e8f0" />
          <circle cx="17" cy="26" r="6" fill="#27272a" />
          <circle cx="53" cy="26" r="6" fill="#27272a" />
        </svg>
      );
  }
}

export default function TrafficBackground() {
  return (
    <div aria-hidden="true" className="traffic-bg pointer-events-none fixed inset-x-0 -z-10 h-36 overflow-hidden select-none">
      <div className="absolute inset-x-0 bottom-0 h-24 bg-zinc-200/60" />
      <div className="traffic-dashes absolute inset-x-0 bottom-12 h-1" />
      {LANE_RIGHT.map((v, i) => (
        <div key={`r${i}`} className="traffic-car traffic-rtl absolute bottom-14" style={{ animationDuration: `${v.d}s`, animationDelay: `${v.delay}s` }}>
          <div className="-scale-x-100">
            <Vehicle k={v.k} />
          </div>
        </div>
      ))}
      {LANE_LEFT.map((v, i) => (
        <div key={`l${i}`} className="traffic-car traffic-ltr absolute bottom-1" style={{ animationDuration: `${v.d}s`, animationDelay: `${v.delay}s` }}>
          <Vehicle k={v.k} />
        </div>
      ))}
    </div>
  );
}
