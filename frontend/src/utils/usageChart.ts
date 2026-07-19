export interface UsageChartPosition {
  x: number;
  y: number;
}

export function usageChartPosition(
  index: number,
  count: number,
  minutes: number,
  maxMinutes: number,
): UsageChartPosition {
  const x = count <= 1 ? 50 : 3 + (index / (count - 1)) * 94;
  const ratio = Math.max(0, Math.min(1, minutes / Math.max(1, maxMinutes)));
  return { x, y: 92 - ratio * 84 };
}

export function usageLineCoordinates(
  values: number[],
): string {
  const maximum = Math.max(1, ...values);
  return values
    .map((value, index) => {
      const point = usageChartPosition(index, values.length, value, maximum);
      return `${point.x},${point.y}`;
    })
    .join(" ");
}
