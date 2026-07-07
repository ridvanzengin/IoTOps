export interface RefreshIntervalOption {
  code: string;
  label: string;
  ms: number;
}

export const REFRESH_INTERVALS: RefreshIntervalOption[] = [
  { code: "off", label: "Off", ms: 0 },
  { code: "10s", label: "10s", ms: 10_000 },
  { code: "30s", label: "30s", ms: 30_000 },
  { code: "1m", label: "1m", ms: 60_000 },
  { code: "5m", label: "5m", ms: 300_000 },
];

export const DEFAULT_REFRESH_INTERVAL = "10s";
