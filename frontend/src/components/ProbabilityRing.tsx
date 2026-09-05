/** ProbabilityRing — SVG ring gauge showing ML recovery probability */

import type { CSSProperties } from "react";

interface Props {
  probability: number;   // 0–1
  size?: number;
  strokeWidth?: number;
}

export default function ProbabilityRing({ probability, size = 120, strokeWidth = 10 }: Props) {
  const r = (size - strokeWidth) / 2;
  const circ = 2 * Math.PI * r;
  const dash = circ * probability;

  const cat = probability >= 0.75 ? "HIGH" : probability >= 0.60 ? "MEDIUM" : "LOW";
  const color =
    probability >= 0.75 ? "var(--prob-high)" :
    probability >= 0.60 ? "var(--prob-med)" :
    "var(--prob-low)";

  const style: CSSProperties = {
    "--ring-color": color,
  } as CSSProperties;

  return (
    <div className="ring-gauge" style={{ width: size, height: size }}>
      <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
        {/* track */}
        <circle
          cx={size / 2} cy={size / 2} r={r}
          fill="none"
          stroke="var(--surface-2)"
          strokeWidth={strokeWidth}
        />
        {/* fill */}
        <circle
          cx={size / 2} cy={size / 2} r={r}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={`${dash} ${circ}`}
          style={{ transition: "stroke-dasharray 1s cubic-bezier(0.4,0,0.2,1)" }}
        />
      </svg>
      <div className="ring-gauge-label" style={style}>
        <div className="ring-pct" style={{ color }}>
          {(probability * 100).toFixed(0)}%
        </div>
        <div className="ring-cat" style={{ color }}>
          {cat}
        </div>
      </div>
    </div>
  );
}
