import { resolveVariableOptions } from "../api/dashboard";
import type { Dashboard, Variable } from "../types/dashboard";
import type { Event } from "../types/event";

// Resolves variable values/options for variables[fromIndex..] in list order,
// since a variable's predicate may only reference a variable defined earlier
// in the list (enforced server-side) — later variables are re-resolved
// whenever an earlier one changes, cascading like Grafana's chained variables.
export async function resolveVariablesFrom(
  dashboardId: string,
  variables: Variable[],
  fromIndex: number,
  baseValues: Record<string, string>,
): Promise<{ values: Record<string, string>; options: Record<string, string[]> }> {
  const values = { ...baseValues };
  const options: Record<string, string[]> = {};

  for (let i = fromIndex; i < variables.length; i++) {
    const variable = variables[i];
    try {
      const result = await resolveVariableOptions(dashboardId, {
        table: variable.table,
        value_column: variable.value_column,
        predicate_column: variable.predicate_column,
        predicate_variable: variable.predicate_variable,
        variable_values: values,
      });
      options[variable.name] = result.options;
      const current = values[variable.name];
      values[variable.name] = current && result.options.includes(current) ? current : (result.options[0] ?? "");
    } catch {
      options[variable.name] = [];
      values[variable.name] = "";
    }
  }

  return { values, options };
}

// An overlay event should only be shown on a panel if it actually belongs
// to whatever the dashboard's variables currently have selected (e.g. a
// panel scoped to hive-1 shouldn't show hive-2's events just because both
// share a Rule) -- matched against the event's own tags by the variable's
// value_column, the same column name the panel's SQL filters on. A
// variable is only used to filter if the event actually carries that tag
// at all -- a Rule's identifiers don't necessarily include every
// dashboard variable's column, and an event that's silent on a given
// column shouldn't be excluded for not matching something it never had
// an opinion on.
export function filterEventsByVariables(
  events: Event[],
  variables: Variable[],
  variableValues: Record<string, string>,
): Event[] {
  const activeFilters = variables
    .map((variable) => ({ column: variable.value_column, value: variableValues[variable.name] }))
    .filter((filter): filter is { column: string; value: string } => Boolean(filter.value));

  if (activeFilters.length === 0) return events;

  return events.filter((event) =>
    activeFilters.every((filter) => {
      const tagValue = event.tags[filter.column];
      return tagValue === undefined || tagValue === filter.value;
    }),
  );
}

export function referencesVariableToken(sql: string, name: string): boolean {
  return new RegExp(`\\$${name}\\b`).test(sql);
}

// References to $oldName elsewhere in the dashboard that would silently stop
// working if this variable is renamed or removed — surfaced as a confirmation
// rather than auto-rewritten, since guessing at intent here is riskier than
// asking. A predicate_variable reference is safe to auto-repair (see
// removeVariableAt below) since it's a plain field, not free-text SQL — only
// panel SQL text can't be rewritten automatically.
export function findVariableReferences(dashboard: Dashboard, oldName: string, ownIndex: number): string[] {
  const affected: string[] = [];
  dashboard.variables.forEach((variable, index) => {
    if (index !== ownIndex && variable.predicate_variable === oldName) {
      affected.push(`variable "${variable.label}"`);
    }
  });
  dashboard.panels.forEach((panel) => {
    if (referencesVariableToken(panel.query.sql, oldName)) {
      affected.push(`panel "${panel.title}"`);
    }
  });
  return affected;
}

// Removes the variable at `index` and nulls out any other variable's
// predicate that referenced it, so the dashboard doesn't fail server-side
// validation (a predicate_variable must reference an existing, earlier
// variable) on the very save that just removed it.
export function removeVariableAt(dashboard: Dashboard, index: number): Variable[] {
  const removedName = dashboard.variables[index].name;
  return dashboard.variables
    .filter((_, i) => i !== index)
    .map((variable) =>
      variable.predicate_variable === removedName
        ? { ...variable, predicate_column: null, predicate_variable: null }
        : variable,
    );
}
