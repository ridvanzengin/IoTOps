import { useState } from "react";
import type { TelemetryTableSchema } from "../types/telemetry";
import type { ConditionOperator, ConditionPayload, RuleOperator } from "../types/automater";
import "./SchemaBrowser.css";
import "./SchemaConditionBuilder.css";

const NUMERIC_TYPES = ["double precision", "integer", "smallint", "numeric", "real", "bigint"];
const NUMERIC_OPERATORS: ConditionOperator[] = ["==", "!=", ">", "<", ">=", "<="];
const TEXT_OPERATORS: ConditionOperator[] = ["==", "!="];

export function isNumericType(dataType: string): boolean {
  return NUMERIC_TYPES.includes(dataType.toLowerCase());
}

function badgeClassForType(dataType: string): string {
  const type = dataType.toLowerCase();
  if (type.includes("timestamp")) return "schema-browser__type-badge--time";
  if (type.includes("char") || type === "text") return "schema-browser__type-badge--text";
  if (isNumericType(type)) return "schema-browser__type-badge--number";
  return "schema-browser__type-badge--other";
}

interface SchemaConditionBuilderProps {
  schema: TelemetryTableSchema[];
  table: string;
  conditions: ConditionPayload[];
  onChange: (table: string, conditions: ConditionPayload[]) => void;
}

// Extends the read-only SchemaBrowser with per-column condition inputs.
// Checking a column adds it to `conditions`; since a Rule only ever
// evaluates against one table (see ROADMAP.md's no-cross-table-correlation
// decision), opening a different table's drawer cancels whatever was
// selected on the previous one (see handleToggle) rather than mixing
// tables. Takes `schema` as a prop (fetched once by the parent) rather
// than fetching its own, so the parent can also use it to validate
// identifiers/message placeholders against real column types.
export function SchemaConditionBuilder({ schema, table, conditions, onChange }: SchemaConditionBuilderProps) {
  // Which table's drawer is visually expanded -- separate from `table`
  // (which table has selected conditions) so collapsing a drawer doesn't
  // discard picks, but opening a *different* one still cancels them
  // immediately (below), not just once a checkbox happens to get clicked.
  const [expandedTable, setExpandedTable] = useState<string | null>(table || null);

  function handleToggle(tableName: string, willBeOpen: boolean) {
    if (willBeOpen) {
      setExpandedTable(tableName);
      if (tableName !== table) {
        onChange(tableName, []);
      }
    } else if (expandedTable === tableName) {
      setExpandedTable(null);
    }
  }

  function conditionFor(columnName: string): ConditionPayload | undefined {
    return conditions.find((c) => c.column === columnName);
  }

  // Conditions fold left-to-right at evaluation time (see rule.go), which
  // makes their *order* meaningful once AND/OR are mixed -- so the array
  // is always kept in the same order the columns are displayed (schema
  // order), not insertion order, so what the user reads top-to-bottom is
  // exactly what gets evaluated.
  function toggleColumn(columnNames: string[], columnName: string, dataType: string, checked: boolean) {
    if (!checked) {
      onChange(table, conditions.filter((c) => c.column !== columnName));
      return;
    }
    const defaultOperator: ConditionOperator = isNumericType(dataType) ? ">" : "==";
    const newCondition: ConditionPayload = {
      column: columnName,
      operator: defaultOperator,
      value: "",
      join: "AND",
    };
    const next = [...conditions, newCondition];
    next.sort((a, b) => columnNames.indexOf(a.column) - columnNames.indexOf(b.column));
    onChange(table, next);
  }

  function updateCondition(columnName: string, patch: Partial<ConditionPayload>) {
    onChange(
      table,
      conditions.map((c) => (c.column === columnName ? { ...c, ...patch } : c)),
    );
  }

  if (schema.length === 0) {
    return <p style={{ color: "var(--text)", fontSize: 13 }}>No telemetry tables found yet.</p>;
  }

  return (
    <div className="schema-browser">
      {schema.map((tableSchema) => {
        const columnNames = tableSchema.columns.map((c) => c.name);
        return (
          <details
            key={tableSchema.table}
            className="schema-browser__table"
            open={expandedTable === tableSchema.table}
            onToggle={(event) => handleToggle(tableSchema.table, event.currentTarget.open)}
          >
            <summary>
              {tableSchema.table}
              {tableSchema.table === table && conditions.length > 0 && (
                <span className="schema-condition__count">{conditions.length} selected</span>
              )}
            </summary>
            <table className="schema-condition__table">
              <thead>
                <tr>
                  <th className="schema-condition__table-col">Column</th>
                  <th>Type</th>
                  <th>Operator</th>
                  <th>Value</th>
                  <th>Combine with</th>
                </tr>
              </thead>
              <tbody>
                {tableSchema.columns.map((column) => {
                  const condition = tableSchema.table === table ? conditionFor(column.name) : undefined;
                  const checked = condition !== undefined;
                  const numeric = isNumericType(column.data_type);
                  const operators = numeric ? NUMERIC_OPERATORS : TEXT_OPERATORS;
                  return (
                    <tr key={column.name}>
                      <td className="schema-condition__table-col">
                        <label className="schema-condition__column">
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={(event) =>
                              toggleColumn(columnNames, column.name, column.data_type, event.target.checked)
                            }
                          />
                          {column.name}
                        </label>
                      </td>
                      <td>
                        <span className={`schema-browser__type-badge ${badgeClassForType(column.data_type)}`}>
                          {column.data_type}
                        </span>
                      </td>
                      <td>
                        <select
                          disabled={!checked}
                          value={condition?.operator ?? operators[0]}
                          onChange={(event) =>
                            updateCondition(column.name, { operator: event.target.value as ConditionOperator })
                          }
                        >
                          {operators.map((op) => (
                            <option key={op} value={op}>
                              {op}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td>
                        <input
                          type={numeric ? "number" : "text"}
                          step={numeric ? "any" : undefined}
                          disabled={!checked}
                          defaultValue={condition ? String(condition.value) : ""}
                          key={`${column.name}-${checked}`}
                          placeholder="value"
                          onBlur={(event) => {
                            const raw = event.target.value;
                            const numericValue = Number(raw);
                            const value =
                              raw.trim() !== "" && !Number.isNaN(numericValue) ? numericValue : raw;
                            updateCondition(column.name, { value });
                          }}
                        />
                      </td>
                      <td>
                        {/* Selectable even on the first checked condition -- its join
                            is simply unused at evaluation time (nothing precedes it),
                            not something worth blocking the user from touching. */}
                        <select
                          disabled={!checked}
                          value={condition?.join ?? "AND"}
                          onChange={(event) =>
                            updateCondition(column.name, { join: event.target.value as RuleOperator })
                          }
                        >
                          <option value="AND">AND</option>
                          <option value="OR">OR</option>
                        </select>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </details>
        );
      })}
    </div>
  );
}
