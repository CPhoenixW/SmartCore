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

export function usageSmoothPath(values: number[], maxValue?: number): string {
  if (!values.length) return "";
  const maximum = Math.max(1, maxValue ?? 0, ...values);
  const points = values.map((value, index) => usageChartPosition(index, values.length, value, maximum));
  const first = points[0];
  if (!first) return "";
  if (points.length === 1) return `M ${first.x} ${first.y}`;
  return points.slice(1).reduce((path, point, index) => {
    const previous = points[index];
    if (!previous) return path;
    const midpoint = (previous.x + point.x) / 2;
    return `${path} C ${midpoint} ${previous.y}, ${midpoint} ${point.y}, ${point.x} ${point.y}`;
  }, `M ${first.x} ${first.y}`);
}
