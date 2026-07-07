import { apiRequest } from "./client";
import type {
  TelemetrySqlQuery,
  TelemetrySqlQueryResult,
  TelemetryTableSchema,
} from "../types/telemetry";

export function listTelemetryTables(): Promise<string[]> {
  return apiRequest<string[]>("/api/telemetry/tables");
}

export function getTelemetrySchema(): Promise<TelemetryTableSchema[]> {
  return apiRequest<TelemetryTableSchema[]>("/api/telemetry/schema");
}

export function queryTelemetrySql(query: TelemetrySqlQuery): Promise<TelemetrySqlQueryResult> {
  return apiRequest<TelemetrySqlQueryResult>("/api/telemetry/query", {
    method: "POST",
    body: JSON.stringify(query),
  });
}
