import { createContext, useContext, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { getUnresolvedCounts, listOccurrences, subscribeToEvents } from "../api/event";
import { listDashboards } from "../api/dashboard";
import { listProjects, updateProject } from "../api/project";
import { reconcileOccurrence } from "../utils/occurrences";
import type { Occurrence } from "../types/event";
import type { Dashboard } from "../types/dashboard";
import type { Project } from "../types/project";

export type ActivePanel = { kind: "project"; projectId: string } | { kind: "copilot" } | null;

interface EventsContextValue {
  projects: Project[];
  dashboardsByProject: Record<string, Dashboard[]>;
  unresolvedCounts: Record<string, number>;
  activePanel: ActivePanel;
  occurrences: Occurrence[];
  occurrencesLoading: boolean;
  openProjectPanel: (projectId: string) => void;
  openCopilotPanel: () => void;
  closePanel: () => void;
  setDefaultDashboard: (projectId: string, dashboardId: string) => Promise<void>;
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

  return (
    <EventsContext.Provider
      value={{
        projects,
        dashboardsByProject,
        unresolvedCounts,
        activePanel,
        occurrences,
        occurrencesLoading,
        openProjectPanel,
        openCopilotPanel,
        closePanel,
        setDefaultDashboard,
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
