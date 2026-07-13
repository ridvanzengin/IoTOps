import { createContext, useContext, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { getUnresolvedCounts, listOccurrences, subscribeToEvents } from "../api/event";
import { listDashboards } from "../api/dashboard";
import { listProjects, updateProject } from "../api/project";
import { reconcileOccurrence } from "../utils/occurrences";
import type { Occurrence } from "../types/event";
import type { Dashboard, Variable } from "../types/dashboard";
import type { Project } from "../types/project";

export type ActivePanel = { kind: "project"; projectId: string } | { kind: "copilot" } | null;

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
  activeDashboardVariables: ActiveDashboardVariables | null;
  openProjectPanel: (projectId: string) => void;
  openCopilotPanel: () => void;
  closePanel: () => void;
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
// open) and the occurrence list for whichever project's panel currently
// is open. See iotops-workspace/ROADMAP.md's "Events sidebar polish"
// note -- this replaces DashboardSidebar's old per-mount fetch/SSE
// effect, which only ever covered one project at a time.
export function EventsProvider({ children }: { children: ReactNode }) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [dashboardsByProject, setDashboardsByProject] = useState<Record<string, Dashboard[]>>({});
  const [unresolvedCounts, setUnresolvedCounts] = useState<Record<string, number>>({});
  const [activePanel, setActivePanel] = useState<ActivePanel>(null);
  const [occurrences, setOccurrences] = useState<Occurrence[]>([]);
  const [occurrencesLoading, setOccurrencesLoading] = useState(false);
  const [activeDashboardVariables, setActiveDashboardVariables] = useState<ActiveDashboardVariables | null>(null);
  const navigate = useNavigate();
  // Not state -- written by a click, read once by whichever dashboard's
  // registration effect fires next (there's an inherent gap between
  // triggering navigation and the destination dashboard's variables
  // actually registering), then cleared. No re-render needed for it on
  // its own.
  const pendingSelectionRef = useRef<{ dashboardId: string; identifiers: Record<string, string> } | null>(null);

  // Read inside the SSE callback/onopen instead of `activePanel` directly
  // -- the subscription effect below only runs once, on mount.
  const activePanelRef = useRef(activePanel);
  useEffect(() => {
    activePanelRef.current = activePanel;
  }, [activePanel]);

  function refetchUnresolvedCounts() {
    getUnresolvedCounts()
      .then((counts) => {
        const next: Record<string, number> = {};
        for (const count of counts) next[count.project_id] = count.count;
        setUnresolvedCounts(next);
      })
      .catch(() => undefined);
  }

  function refetchOpenPanel() {
    const panel = activePanelRef.current;
    if (!panel || panel.kind !== "project") return;
    listOccurrences(panel.projectId)
      .then(setOccurrences)
      .catch(() => undefined);
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
      setUnresolvedCounts((prev) => {
        // A match always starts a *new* occurrence (Go suppresses repeat
        // matches on an already-firing rule, so this never double-counts
        // an already-open one) and a clear always resolves exactly the
        // occurrence it paired with -- so +1/-1 here is the same pairing
        // invariant reconcileOccurrence uses, just without needing the
        // full occurrence list for every project.
        const delta = event.flag === "match" ? 1 : -1;
        const current = prev[event.project_id] ?? 0;
        return { ...prev, [event.project_id]: Math.max(0, current + delta) };
      });

      const panel = activePanelRef.current;
      if (panel && panel.kind === "project" && panel.projectId === event.project_id) {
        setOccurrences((prev) => reconcileOccurrence(prev, event));
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
    setOccurrencesLoading(true);
    listOccurrences(projectId)
      .then(setOccurrences)
      .catch(() => setOccurrences([]))
      .finally(() => setOccurrencesLoading(false));
  }

  function openCopilotPanel() {
    setActivePanel({ kind: "copilot" });
    setOccurrences([]);
  }

  function closePanel() {
    setActivePanel(null);
    setOccurrences([]);
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
        activeDashboardVariables,
        openProjectPanel,
        openCopilotPanel,
        closePanel,
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
