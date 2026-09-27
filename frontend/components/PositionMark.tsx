"use client";

export function PositionMark({ position, compact = false }: { position: string; compact?: boolean }) {
  const pose = ["back", "left", "right", "sitting", "out_of_bed"].includes(position) ? position : "unknown";
  return (
    <div className={compact ? "bed bed-compact" : "bed"} aria-hidden="true">
      <span className={`body pose-${pose}`} />
    </div>
  );
}
