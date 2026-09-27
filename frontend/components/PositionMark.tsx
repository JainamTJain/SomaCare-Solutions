"use client";

export function PositionMark({ position }: { position: string }) {
  const pose = ["back", "left", "right", "sitting", "out_of_bed"].includes(position) ? position : "unknown";
  return (
    <div className="bed" aria-hidden="true">
      <span className={`body pose-${pose}`} />
    </div>
  );
}
