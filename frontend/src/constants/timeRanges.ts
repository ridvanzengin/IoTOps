export interface TimeRangeOption {
  code: string;
  label: string;
}

export const TIME_RANGES: TimeRangeOption[] = [
  { code: "15m", label: "Last 15m" },
  { code: "1h", label: "Last 1h" },
  { code: "6h", label: "Last 6h" },
  { code: "24h", label: "Last 24h" },
  { code: "7d", label: "Last 7d" },
];

export const DEFAULT_TIME_RANGE = "1h";
