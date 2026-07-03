export interface TelemetryColumn {
  name: string;
  data_type: string;
  is_nullable: boolean;
}

export interface TelemetryTableSchema {
  table: string;
  columns: TelemetryColumn[];
}

export interface TelemetrySqlQuery {
  sql: string;
  limit?: number;
}

export interface TelemetrySqlQueryResult {
  columns: string[];
  rows: Record<string, unknown>[];
}
