import { useMemo } from "react";

function seeded(n: number): () => number {
  let s = n % 2147483647;
  if (s <= 0) s += 2147483646;
  return () => (s = (s * 16807) % 2147483647) / 2147483647;
}

interface Props {
  seed?: number;
  w?: number;
  h?: number;
  playing?: boolean;
  dense?: number;
}

export function Waveform({ seed = 1, w = 220, h = 34, playing = false, dense = 120 }: Props) {
  const d = useMemo(() => {
    const rand = seeded(seed * 9301 + 49297);
    const pts: number[] = [];
    let env = 0;
    for (let i = 0; i <= dense; i++) {
      const t = i / dense;
      const target =
        0.25 +
        0.75 * Math.abs(Math.sin(t * Math.PI * (1.2 + (seed % 5)))) * (0.4 + rand());
      env += (target - env) * 0.5;
      const a = env * (0.4 + rand() * 0.6);
      pts.push(a);
    }
    const mid = h / 2;
    const step = w / dense;
    let path = `M 0 ${mid}`;
    pts.forEach((a, i) => {
      const x = (i * step).toFixed(1);
      path += ` L ${x} ${(mid - a * mid * 0.92).toFixed(1)}`;
    });
    for (let i = pts.length - 1; i >= 0; i--) {
      const x = (i * step).toFixed(1);
      path += ` L ${x} ${(mid + pts[i] * mid * 0.92).toFixed(1)}`;
    }
    return path;
  }, [seed, w, h, dense]);
  const mid = h / 2;
  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      width={w}
      height={h}
      preserveAspectRatio="none"
      className={playing ? "wave playing" : "wave"}
    >
      <line x1="0" y1={mid} x2={w} y2={mid} stroke="rgba(51,255,102,0.18)" strokeWidth="1" />
      <path d={d} fill="rgba(51,255,102,0.10)" stroke="#33ff66" strokeWidth="1" />
      {playing && (
        <rect className="wave-scan" x="0" y="0" width="2" height={h} fill="rgba(245,166,35,0.9)">
          <animate attributeName="x" from="0" to={w} dur="2.4s" repeatCount="indefinite" />
        </rect>
      )}
    </svg>
  );
}
