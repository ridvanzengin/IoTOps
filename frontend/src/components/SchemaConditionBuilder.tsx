import type { TelemetryTableSchema } from "../types/telemetry";
import type { ConditionOperator, ConditionPayload } from "../types/automater";
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
// decision), checking a column on a different table than the one currently
// selected replaces the whole condition set rather than mixing tables.
// Takes `schema` as a prop (fetched once by the parent) rather than
// fetching its own, so the parent can also use it to validate identifiers/
// message placeholders against real column types.
export function SchemaConditionBuilder({ schema, table, conditions, onChange }: SchemaConditionBuilderProps) {
  function conditionFor(columnName: string): ConditionPayload | undefined {
    return conditions.find((c) => c.column === columnName);
  }

  function toggleColumn(tableName: string, columnName: string, dataType: string, checked: boolean) {
    if (!checked) {
      onChange(table, conditions.filter((c) => c.column !== columnName));
      return;
    }
    const defaultOperator = isNumericType(dataType) ? ">" : "==";
    const newCondition: ConditionPayload = { column: columnName, operator: defaultOperator, value: "" };
    if (tableName !== table) {
      // Switching tables: this rule can only target one, so the new
      // selection replaces whatever was picked on the previous table.
      onChange(tableName, [newCondition]);
    } else {
      onChange(table, [...conditions, newCondition]);
    }
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
      {schema.map((tableSchema) => (
        <details key={tableSchema.table} className="schema-browser__table" open={tableSchema.table === table}>
          <summary>
            {tableSchema.table}
            {tableSchema.table === table && conditions.length > 0 && (
              <span className="schema-condition__count">{conditions.length} selected</span>
            )}
          </summary>
          <table className="schema-condition__table">
            <thead>
              <tr>
                <th>Column</th>
                <th>Type</th>
                <th>Operator</th>
                <th>Value</th>
              </tr>
            </thead>
            <tbody>
              {tableSchema.columns.map((column) => {
                const condition = tableSchema.table === table ? conditionFor(column.name) : undefined;
                const checked = condition !== undefined;
                const operators = isNumericType(column.data_type) ? NUMERIC_OPERATORS : TEXT_OPERATORS;
                return (
                  <tr key={column.name}>
                    <td>
                      <label className="schema-condition__column">
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={(event) =>
                            toggleColumn(tableSchema.table, column.name, column.data_type, event.target.checked)
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
                        {operators.map((operator) => (
                          <option key={operator} value={operator}>
                            {operator}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td>
                      <input
                        disabled={!checked}
                        defaultValue={condition ? String(condition.value) : ""}
                        key={`${column.name}-${checked}`}
                        placeholder="value"
                        onBlur={(event) => {
                          const raw = event.target.value;
                          const numeric = Number(raw);
                          const value = raw.trim() !== "" && !Number.isNaN(numeric) ? numeric : raw;
                          updateCondition(column.name, { value });
                        }}
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </details>
      ))}
    </div>
  );
}
