import { createContext, useContext, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { getOccurrenceCounts, getUnresolvedCounts, listOccurrences, subscribeToEvents } from "../api/event";
import { listDashboards } from "../api/dashboard";
import { listProjects, updateProject } from "../api/project";
import { DEFAULT_TIME_RANGE } from "../constants/timeRanges";
import { debounce } from "../utils/debounce";
import type { EventRuleCount, Occurrence } from "../types/event";
import type { Dashboard, Variable } from "../types/dashboard";
import type { Project } from "../types/project";

export type ActivePanel = { kind: "project"; projectId: string } | { kind: "copilot" } | null;

// What EventsPanel's filter chips can narrow the occurrence list to. Kept
// here (not local component state) because applying a filter changes what
// EventsContext fetches.
export type OccurrenceFilter = { kind: "rule"; ruleId: string } | { kind: "unresolved" };

export const OCCURRENCES_PAGE_SIZE = 20;

// Registered by DashboardEditor while it's mounted (see its own
// registerDashboardVariables effect) so the globally-mounted events
// panel/occurrence cards can offer "click an identifier to set the
// matching dashboard variable(s)" -- only meaningful when a dashboard
// for the *same project* actually happens to be open at the same time,
// since the events panel itself isn't scoped to one (see
// iotops-workspace/ROADMAP.md's AI Co-pilot design notes for the deeper
// "why" behind identifier-key vs. variable-column matching being
// name-based, not guaranteed).
export interface ActiveDashboardVariables {
  dashboardId: string;
  projectId: string;
  variables: Variable[];
  // Applies every identifier in the dict that matches one of this
  // dashboard's variables (by value_column), all at once -- not just a
  // single key/value pair -- re-resolving the predicate chain starting
  // from the *earliest* affected variable so a later variable's options
  // reflect an earlier one's new value in the same click (e.g. Hive's
  // options narrow to the newly-selected Apiary before Hive itself is
  // validated against them, instead of failing because Hive was checked
  // against the *old* Apiary's options). Any identifier with no
  // matching variable is silently ignored, same as any value that still
  // doesn't resolve after the cascade -- see DashboardEditor's
  // implementation for the graceful (fall back to the first available
  // option, don't error) fallback already built into resolveVariablesFrom.
  selectIdentifiers: (identifiers: Record<string, string>) => void;
}

interface EventsContextValue {
  projects: Project[];
  dashboardsByProject: Record<string, Dashboard[]>;
  unresolvedCounts: Record<string, number>;
  activePanel: ActivePanel;
  occurrences: Occurrence[];
  occurrencesLoading: boolean;
  occurrencesTotal: number;
  occurrencesOffset: number;
  occurrenceFilter: OccurrenceFilter | null;
  timeRange: string;
  searchQuery: string;
  // Rules matching the current time range/search, each with its occurrence
  // count *within that same window* -- also refetched (debounced) on every
  // live match/clear SSE event for the open project, so a chip's count
  // never goes stale while the panel is open. See getOccurrenceCounts.
  ruleCounts: EventRuleCount[];
  // The panel's "Active" filter chip's count -- like unresolvedCounts (the
  // ActivityBar badge), deliberately NOT time-windowed, so the two can
  // never structurally disagree just because an occurrence is older than
  // the panel's current range. Still scoped by `search`, unlike the badge.
  // See its state comment and the backend's own matching comment on
  // GET /api/event/occurrences.
  activeCount: number;
  activeDashboardVariables: ActiveDashboardVariables | null;
  openProjectPanel: (projectId: string) => void;
  openCopilotPanel: () => void;
  closePanel: () => void;
  setOccurrenceFilter: (filter: OccurrenceFilter | null) => void;
  setTimeRange: (range: string) => void;
  setSearchQuery: (text: string) => void;
  loadOccurrencesPage: (offset: number) => void;
  setDefaultDashboard: (projectId: string, dashboardId: string) => Promise<void>;
  registerDashboardVariables: (context: ActiveDashboardVariables) => void;
  clearDashboardVariables: (dashboardId: string) => void;
  // Navigates to projectId's default dashboard (or its first one, if no
  // default is set) and applies `identifiers` once that dashboard
  // registers -- for clicking an occurrence card identifier when no
  // dashboard (or a different project's) is currently open. Returns a
  // result rather than throwing so the caller can show an inline
  // message on the "this project has no dashboard at all" edge case.
  openDashboardAndSelectIdentifiers: (
    projectId: string,
    identifiers: Record<string, string>,
  ) => { ok: true } | { ok: false; message: string };
}

const EventsContext = createContext<EventsContextValue | null>(null);

// Owns the one session-wide EventSource (opened once here, at the app
// shell root) plus the state it feeds: every project's unresolved-match
// badge count (always live, regardless of which/whether a panel is
// open) and the occurrence list/counts for whichever project's panel
// currently is open, both scoped to a time range + optional search text.
// See iotops-workspace/ROADMAP.md's "Events sidebar polish" note.
export function EventsProvider({ children }: { children: ReactNode }) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [dashboardsByProject, setDashboardsByProject] = useState<Record<string, Dashboard[]>>({});
  const [unresolvedCounts, setUnresolvedCounts] = useState<Record<string, number>>({});
  const [activePanel, setActivePanel] = useState<ActivePanel>(null);
  const [occurrences, setOccurrences] = useState<Occurrence[]>([]);
  const [occurrencesLoading, setOccurrencesLoading] = useState(false);
  const [occurrencesTotal, setOccurrencesTotal] = useState(0);
  const [occurrencesOffset, setOccurrencesOffset] = useState(0);
  const [occurrenceFilter, setOccurrenceFilterState] = useState<OccurrenceFilter | null>(null);
  // Sticky across project switches (a user who picked "24h" almost
  // certainly wants that kept, not silently reset to 1h when they click a
  // different project) -- unlike filter/search, which reset per project.
  const [timeRange, setTimeRangeState] = useState(DEFAULT_TIME_RANGE);
  const [searchQuery, setSearchQueryState] = useState("");
  const [ruleCounts, setRuleCounts] = useState<EventRuleCount[]>([]);
  // Kept as its own fetch (not reused from unresolvedCounts) because it's
  // scoped by `search`, unlike the badge -- but the backend ignores
  // `range` for status=active queries specifically, so age never makes
  // this drift from unresolvedCounts the way it used to.
  const [activeCount, setActiveCount] = useState(0);
  const [activeDashboardVariables, setActiveDashboardVariables] = useState<ActiveDashboardVariables | null>(null);
  const navigate = useNavigate();
  // Not state -- written by a click, read once by whichever dashboard's
  // registration effect fires next (there's an inherent gap between
  // triggering navigation and the destination dashboard's variables
  // actually registering), then cleared. No re-render needed for it on
  // its own.
  const pendingSelectionRef = useRef<{ dashboardId: string; identifiers: Record<string, string> } | null>(null);

  // Read inside the SSE callback/onopen instead of the corresponding state
  // directly -- the subscription effect below only runs once, on mount.
  const activePanelRef = useRef(activePanel);
  useEffect(() => {
    activePanelRef.current = activePanel;
  }, [activePanel]);

  const occurrenceFilterRef = useRef(occurrenceFilter);
  useEffect(() => {
    occurrenceFilterRef.current = occurrenceFilter;
  }, [occurrenceFilter]);

  const timeRangeRef = useRef(timeRange);
  useEffect(() => {
    timeRangeRef.current = timeRange;
  }, [timeRange]);

  const searchQueryRef = useRef(searchQuery);
  useEffect(() => {
    searchQueryRef.current = searchQuery;
  }, [searchQuery]);

  const occurrencesOffsetRef = useRef(occurrencesOffset);
  useEffect(() => {
    occurrencesOffsetRef.current = occurrencesOffset;
  }, [occurrencesOffset]);

  function refetchUnresolvedCounts() {
    getUnresolvedCounts()
      .then((counts) => {
        const next: Record<string, number> = {};
        for (const count of counts) next[count.project_id] = count.count;
        setUnresolvedCounts(next);
      })
      .catch(() => undefined);
  }

  // The single fetch behind the panel's occurrence list, at any filter/
  // time range/search/page combination -- always asks the backend for
  // exactly what's being viewed (scoped by rule_id/status/range/search/
  // offset) instead of client-side-filtering an unrelated, differently-
  // scoped fetch. `total` (from the same query) is what drives pagination
  // and is guaranteed consistent with `items`, since both come from one
  // server-side computation. See ListOccurrencesOptions.
  function fetchOccurrences(
    projectId: string,
    filter: OccurrenceFilter | null,
    range: string,
    search: string,
    offset: number,
  ) {
    setOccurrencesLoading(true);
    listOccurrences(projectId, {
      limit: OCCURRENCES_PAGE_SIZE,
      offset,
      range,
      search: search || undefined,
      ruleIds: filter?.kind === "rule" ? [filter.ruleId] : undefined,
      status: filter?.kind === "unresolved" ? "active" : undefined,
    })
      .then((page) => {
        setOccurrences(page.items);
        setOccurrencesTotal(page.total);
        setOccurrencesOffset(offset);
      })
      .catch(() => {
        setOccurrences([]);
        setOccurrencesTotal(0);
      })
      .finally(() => setOccurrencesLoading(false));
  }

  function fetchCounts(projectId: string, range: string, search: string) {
    getOccurrenceCounts(projectId, range, search || undefined)
      .then(setRuleCounts)
      .catch(() => setRuleCounts([]));
    // limit=0 -- only `total` is wanted here (the exact count the "Active"
    // chip's click-through will load), not the items themselves. Same
    // query the click-through itself issues (status=active, same
    // range/search), so the two can't structurally disagree.
    listOccurrences(projectId, { status: "active", range, search: search || undefined, limit: 0, offset: 0 })
      .then((page) => setActiveCount(page.total))
      .catch(() => setActiveCount(0));
  }

  // Stable across renders (created once) -- both debounced wrappers only
  // ever call fetchOccurrences/fetchCounts with explicit arguments and
  // the always-stable setX state setters, so capturing the first render's
  // versions is safe; recreating a "debounced" function on every render
  // would defeat the debouncing (each call would get its own fresh timer).
  const debouncedSearchFetch = useRef(
    debounce((projectId: string, filter: OccurrenceFilter | null, range: string, search: string) => {
      fetchOccurrences(projectId, filter, range, search, 0);
      fetchCounts(projectId, range, search);
    }, 300),
  ).current;

  // Ground-truth refetch, not a client-side +1/-1 patch -- the old patch
  // assumed a match always opens exactly one new occurrence and a clear
  // always resolves exactly the one it paired with, which doesn't
  // strictly hold (the backend's own _pair_occurrences docstring notes a
  // duplicate match while one's already open is handled defensively,
  // i.e. ignored server-side -- a client blindly incrementing on that
  // same event would drift 1 high until the next SSE reconnect forced a
  // resync). Debounced so a noisy rule firing repeatedly doesn't trigger
  // one request per event.
  const debouncedUnresolvedCountsRefetch = useRef(debounce(refetchUnresolvedCounts, 400)).current;

  // A burst of live events (a noisy rule firing repeatedly) shouldn't
  // trigger one refetch per event.
  const debouncedLiveRefetch = useRef(
    debounce((projectId: string) => {
      fetchOccurrences(
        projectId,
        occurrenceFilterRef.current,
        timeRangeRef.current,
        searchQueryRef.current,
        occurrencesOffsetRef.current,
      );
      fetchCounts(projectId, timeRangeRef.current, searchQueryRef.current);
    }, 400),
  ).current;

  function refetchOpenPanel() {
    const panel = activePanelRef.current;
    if (!panel || panel.kind !== "project") return;
    fetchOccurrences(
      panel.projectId,
      occurrenceFilterRef.current,
      timeRangeRef.current,
      searchQueryRef.current,
      occurrencesOffsetRef.current,
    );
    fetchCounts(panel.projectId, timeRangeRef.current, searchQueryRef.current);
  }

  useEffect(() => {
    listProjects()
      .then(setProjects)
      .catch(() => undefined);
    // Grouped client-side, same convention Home.tsx already uses for its
    // own project_id -> dashboard lookup -- GET /api/dashboard has no
    // project_id filter, it always returns everything.
    listDashboards()
      .then((dashboards) => {
        const grouped: Record<string, Dashboard[]> = {};
        for (const dashboard of dashboards) {
          (grouped[dashboard.project_id] ??= []).push(dashboard);
        }
        setDashboardsByProject(grouped);
      })
      .catch(() => undefined);
    refetchUnresolvedCounts();

    const source = subscribeToEvents((event) => {
      // This badge is intentionally NOT time-windowed (unlike the panel's
      // own counts) -- it means "currently unresolved, regardless of
      // age", so a still-broken issue from outside the panel's time
      // range doesn't silently disappear from it.
      debouncedUnresolvedCountsRefetch();

      const panel = activePanelRef.current;
      if (panel && panel.kind === "project" && panel.projectId === event.project_id) {
        debouncedLiveRefetch(event.project_id);
      }
    });

    // Reconnect-refetch: closes the Redis Pub/Sub no-buffering gap -- a
    // message published while nobody was subscribed is simply gone, so
    // this is the only way to catch back up after a reconnect (onopen
    // fires on every reconnect, including the browser's own automatic
    // retry).
    source.onopen = () => {
      refetchUnresolvedCounts();
      refetchOpenPanel();
    };

    return () => source.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function openProjectPanel(projectId: string) {
    setActivePanel({ kind: "project", projectId });
    setOccurrenceFilterState(null);
    setSearchQueryState("");
    fetchOccurrences(projectId, null, timeRange, "", 0);
    fetchCounts(projectId, timeRange, "");
  }

  function openCopilotPanel() {
    setActivePanel({ kind: "copilot" });
    setOccurrences([]);
    setOccurrencesTotal(0);
    setOccurrencesOffset(0);
    setRuleCounts([]);
  }

  function closePanel() {
    setActivePanel(null);
    setOccurrences([]);
    setOccurrencesTotal(0);
    setOccurrencesOffset(0);
    setRuleCounts([]);
    setOccurrenceFilterState(null);
    setSearchQueryState("");
  }

  function setOccurrenceFilter(filter: OccurrenceFilter | null) {
    setOccurrenceFilterState(filter);
    const panel = activePanelRef.current;
    if (panel && panel.kind === "project") {
      fetchOccurrences(panel.projectId, filter, timeRange, searchQuery, 0);
    }
  }

  function setTimeRange(range: string) {
    setTimeRangeState(range);
    const panel = activePanelRef.current;
    if (panel && panel.kind === "project") {
      fetchOccurrences(panel.projectId, occurrenceFilter, range, searchQuery, 0);
      fetchCounts(panel.projectId, range, searchQuery);
    }
  }

  function setSearchQuery(text: string) {
    setSearchQueryState(text);
    const panel = activePanelRef.current;
    if (panel && panel.kind === "project") {
      debouncedSearchFetch(panel.projectId, occurrenceFilter, timeRange, text);
    }
  }

  function loadOccurrencesPage(offset: number) {
    const panel = activePanelRef.current;
    if (!panel || panel.kind !== "project") return;
    fetchOccurrences(panel.projectId, occurrenceFilter, timeRange, searchQuery, offset);
  }

  async function setDefaultDashboard(projectId: string, dashboardId: string): Promise<void> {
    const project = projects.find((p) => p.id === projectId);
    if (!project) return;
    const updated = await updateProject(projectId, {
      name: project.name,
      description: project.description,
      default_dashboard_id: dashboardId,
    });
    setProjects((prev) => prev.map((p) => (p.id === projectId ? updated : p)));
  }

  function registerDashboardVariables(context: ActiveDashboardVariables) {
    setActiveDashboardVariables(context);
    const pending = pendingSelectionRef.current;
    if (pending && pending.dashboardId === context.dashboardId) {
      pendingSelectionRef.current = null;
      context.selectIdentifiers(pending.identifiers);
    }
  }

  // Guards against a stale unmount clobbering a newer registration --
  // e.g. navigating from dashboard A to dashboard B can run B's
  // registration effect before A's own cleanup effect fires, depending
  // on exact timing; only clear if the id passed in still matches
  // what's currently registered.
  function clearDashboardVariables(dashboardId: string) {
    setActiveDashboardVariables((current) => (current?.dashboardId === dashboardId ? null : current));
  }

  function openDashboardAndSelectIdentifiers(
    projectId: string,
    identifiers: Record<string, string>,
  ): { ok: true } | { ok: false; message: string } {
    const candidates = dashboardsByProject[projectId] ?? [];
    if (candidates.length === 0) {
      return { ok: false, message: "This project has no dashboard to open." };
    }
    const project = projects.find((p) => p.id === projectId);
    const target = candidates.find((d) => d.id === project?.default_dashboard_id) ?? candidates[0];
    pendingSelectionRef.current = { dashboardId: target.id, identifiers };
    navigate(`/dashboards/${target.id}`);
    return { ok: true };
  }

  return (
    <EventsContext.Provider
      value={{
        projects,
        dashboardsByProject,
        unresolvedCounts,
        activePanel,
        occurrences,
        occurrencesLoading,
        occurrencesTotal,
        occurrencesOffset,
        occurrenceFilter,
        timeRange,
        searchQuery,
        ruleCounts,
        activeCount,
        activeDashboardVariables,
        openProjectPanel,
        openCopilotPanel,
        closePanel,
        setOccurrenceFilter,
        setTimeRange,
        setSearchQuery,
        loadOccurrencesPage,
        setDefaultDashboard,
        registerDashboardVariables,
        clearDashboardVariables,
        openDashboardAndSelectIdentifiers,
      }}
    >
      {children}
    </EventsContext.Provider>
  );
}

export function useEvents(): EventsContextValue {
  const context = useContext(EventsContext);
  if (!context) throw new Error("useEvents must be used within an EventsProvider");
  return context;
}
