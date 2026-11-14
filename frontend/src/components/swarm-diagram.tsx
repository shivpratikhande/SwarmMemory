"use client";

/**
 * Hero illustration: three agents around the shared memory core, with the
 * publish → verify → buy flows animated along the edges.
 */
const NODES = [
  { x: 70, y: 74, ly: -42, letter: "A", label: "Research", from: "oklch(0.74 0.15 60)", to: "oklch(0.62 0.17 38)" },
  { x: 336, y: 96, ly: -42, letter: "B", label: "Verify", from: "oklch(0.72 0.13 165)", to: "oklch(0.55 0.12 175)" },
  { x: 108, y: 262, ly: 50, letter: "C", label: "Build", from: "oklch(0.68 0.13 285)", to: "oklch(0.52 0.15 270)" },
];
const CORE = { x: 210, y: 170 };
const EDGE_LABEL = ["publish", "verify", "buy"];

export function SwarmDiagram() {
  return (
    <div className="relative mx-auto w-full max-w-[440px]" aria-hidden>
      <svg viewBox="0 0 400 330" className="w-full overflow-visible">
        <defs>
          {NODES.map((n) => (
            <linearGradient key={n.letter} id={`g-${n.letter}`} x1="0" y1="0" x2="1" y2="1">
              <stop offset="0" stopColor={n.from} />
              <stop offset="1" stopColor={n.to} />
            </linearGradient>
          ))}
          <linearGradient id="g-core" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="oklch(0.72 0.16 55)" />
            <stop offset="1" stopColor="oklch(0.6 0.18 35)" />
          </linearGradient>
          <radialGradient id="g-glow">
            <stop offset="0" stopColor="oklch(0.7 0.17 50)" stopOpacity=".35" />
            <stop offset="1" stopColor="oklch(0.7 0.17 50)" stopOpacity="0" />
          </radialGradient>
        </defs>

        <circle cx={CORE.x} cy={CORE.y} r="120" fill="url(#g-glow)" />
        <circle cx={CORE.x} cy={CORE.y} r="88" fill="none" stroke="var(--border)" strokeDasharray="2 6" />

        {NODES.map((n, i) => {
          const mx = n.x + (CORE.x - n.x) * 0.5;
          const my = n.y + (CORE.y - n.y) * 0.5;
          return (
            <g key={`e-${n.letter}`}>
              <line x1={n.x} y1={n.y} x2={CORE.x} y2={CORE.y} stroke="var(--border)" strokeWidth="2" />
              <line x1={n.x} y1={n.y} x2={CORE.x} y2={CORE.y} stroke={n.to} strokeWidth="2" strokeDasharray="4 8" strokeLinecap="round" className="animate-flow" style={{ animationDelay: `${i * 0.4}s`, animationDirection: i === 2 ? "reverse" : "normal" }} />
              <g transform={`translate(${mx} ${my})`}>
                <rect x="-28" y="-11" width="56" height="22" rx="11" fill="var(--card)" stroke="var(--border)" />
                <text textAnchor="middle" dy="4" fontSize="10.5" fontWeight="500" fill="var(--muted-foreground)" fontFamily="var(--font-sans)">
                  {EDGE_LABEL[i]}
                </text>
              </g>
            </g>
          );
        })}

        {/* memory core: honeycomb */}
        <g transform={`translate(${CORE.x} ${CORE.y})`}>
          <path d="M0 -46 40 -23 40 23 0 46 -40 23 -40 -23Z" fill="url(#g-core)" />
          <path d="M0 -46 40 -23 40 23 0 46 -40 23 -40 -23Z" fill="none" stroke="white" strokeOpacity=".35" />
          <path d="M0 -20 17 -10 17 10 0 20 -17 10 -17 -10Z" fill="white" fillOpacity=".92" />
          <text textAnchor="middle" y="-60" fontSize="12" fontWeight="600" fill="var(--foreground)" fontFamily="var(--font-display)">
            Shared memory
          </text>
        </g>

        {NODES.map((n) => (
          <g key={n.letter} transform={`translate(${n.x} ${n.y})`}>
            <circle r="30" fill="var(--card)" stroke="var(--border)" />
            <circle r="23" fill={`url(#g-${n.letter})`} />
            <text textAnchor="middle" dy="5.5" fontSize="16" fontWeight="700" fill="white" fontFamily="var(--font-display)">
              {n.letter}
            </text>
            <text textAnchor="middle" y={n.ly} fontSize="11.5" fontWeight="500" fill="var(--muted-foreground)" fontFamily="var(--font-sans)">
              Agent {n.letter} · {n.label}
            </text>
          </g>
        ))}

        {/* NEAR settlement chip */}
        <g transform="translate(318 262)">
          <rect x="-58" y="-17" width="116" height="34" rx="17" fill="var(--card)" stroke="var(--border)" />
          <circle cx="-38" cy="0" r="9" fill="var(--chain)" fillOpacity=".15" />
          <text x="-38" dy="4" textAnchor="middle" fontSize="11" fontWeight="700" fill="var(--chain)">
            Ⓝ
          </text>
          <text x="-23" dy="4" fontSize="11" fontWeight="500" fill="var(--foreground)" fontFamily="var(--font-sans)">
            Settled on-chain
          </text>
        </g>
        <line x1={CORE.x + 40} y1={CORE.y + 23} x2="275" y2="248" stroke="var(--chain)" strokeOpacity=".5" strokeWidth="1.5" strokeDasharray="3 5" />
      </svg>
    </div>
  );
}
