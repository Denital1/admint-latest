export const durationUnits = ["minutes", "hours", "days", "weeks", "months", "years"] as const;
export type DurationUnit = (typeof durationUnits)[number];

const minutesPerUnit: Record<DurationUnit, number> = {
  minutes: 1, hours: 60, days: 1440, weeks: 10080, months: 43200, years: 525600,
};

// Durations have minute precision; months and years use fixed lengths, not calendar dates.
export function durationMinutes(value: string, unit: DurationUnit): number | null {
  if (!/^\d+(?:\.\d*)?$/.test(value) || value.length > 16 || !durationUnits.includes(unit)) return null;
  const [whole, fraction = ""] = value.split(".");
  const scale = 10n ** BigInt(fraction.length);
  const exact = (BigInt(whole) * scale + BigInt(fraction || "0")) * BigInt(minutesPerUnit[unit]);
  const rounded = (exact + scale / 2n) / scale;
  if (rounded < 1n || rounded > BigInt(Number.MAX_SAFE_INTEGER)) return null;
  return Number(rounded);
}

export function formatDuration(value: string, unit: DurationUnit): string | null {
  let remaining = durationMinutes(value, unit);
  if (remaining === null) return null;
  const breakdown: DurationUnit[] = unit === "minutes" ? ["minutes"] : unit === "hours" ? ["hours", "minutes"] : unit === "days" ? ["days", "hours", "minutes"] : [unit, "days", "hours", "minutes"];
  const parts: string[] = [];
  for (const part of breakdown) {
    const count = Math.floor(remaining / minutesPerUnit[part]);
    remaining %= minutesPerUnit[part];
    if (count) parts.push(`${count} ${count === 1 ? part.slice(0, -1) : part}`);
  }
  const formatted = parts.length < 2 ? parts[0] : `${parts.slice(0, -1).join(", ")} and ${parts.at(-1)}`;
  return formatted.length <= 80 ? formatted : null;
}
