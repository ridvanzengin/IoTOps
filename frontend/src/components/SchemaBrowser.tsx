import { useEffect, useState } from "react";
import { ApiError } from "../api/client";
import { getTelemetrySchema } from "../api/telemetry";
import type { TelemetryTableSchema } from "../types/telemetry";
import "./SchemaBrowser.css";

function badgeClassForType(dataType: string): string {
  const type = dataType.toLowerCase();
  if (type.includes("timestamp")) return "schema-browser__type-badge--time";
  if (type.includes("char") || type === "text") return "schema-browser__type-badge--text";
  if (type.includes("double") || type.includes("numeric") || type.includes("real") || type.includes("int")) {
    return "schema-browser__type-badge--number";
  }
  return "schema-browser__type-badge--other";
}

interface SchemaBrowserProps {
  onSelect?: (token: string) => void;
}

export function SchemaBrowser({ onSelect }: SchemaBrowserProps = {}) {
  const [schema, setSchema] = useState<TelemetryTableSchema[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getTelemetrySchema()
      .then(setSchema)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load schema."));
  }, []);

  if (error) {
    return <p className="collector-page__error">{error}</p>;
  }

  if (schema.length === 0) {
    return <p style={{ color: "var(--text)", fontSize: 13 }}>No telemetry tables found yet.</p>;
  }

  return (
    <div className="schema-browser">
      {schema.map((table) => (
        <details key={table.table} className="schema-browser__table">
          <summary>{table.table}</summary>
          <table className="schema-browser__columns">
            <tbody>
              {table.columns.map((column) => (
                <tr key={column.name}>
                  <td>
                    {onSelect ? (
                      <button
                        type="button"
                        className="schema-browser__column-button"
                        onClick={() => onSelect(`${table.table}.${column.name}`)}
                      >
                        {column.name}
                      </button>
                    ) : (
                      column.name
                    )}
                  </td>
                  <td>
                    <span className={`schema-browser__type-badge ${badgeClassForType(column.data_type)}`}>
                      {column.data_type}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      ))}
    </div>
  );
}
