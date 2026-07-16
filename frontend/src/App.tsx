import { useEffect, useRef } from "react";
import type { RefObject } from "react";
import { BrowserRouter, Route, Routes, useLocation } from "react-router-dom";
import { Home } from "./pages/Home";
import { AutomaterList } from "./pages/AutomaterList";
import { AutomaterEditor } from "./pages/AutomaterEditor";
import { QueryRuleList } from "./pages/QueryRuleList";
import { QueryRuleEditor } from "./pages/QueryRuleEditor";
import { CollectorList } from "./pages/CollectorList";
import { CollectorEditor } from "./pages/CollectorEditor";
import { ProjectList } from "./pages/ProjectList";
import { ProjectForm } from "./pages/ProjectForm";
import { DashboardList } from "./pages/DashboardList";
import { DashboardForm } from "./pages/DashboardForm";
import { DashboardEditor } from "./pages/DashboardEditor";
import { PanelBuilder } from "./pages/PanelBuilder";
import { VariableBuilder } from "./pages/VariableBuilder";
import { VariableList } from "./pages/VariableList";
import { Docs } from "./pages/Docs";
import { Sidebar } from "./components/Sidebar";
import { ActivityBar } from "./components/ActivityBar";
import { EventsPanel } from "./components/EventsPanel";
import { Toast } from "./components/Toast";
import { DemoModeProvider } from "./context/DemoModeContext";
import { EventsProvider } from "./context/EventsContext";
import { ThemeProvider } from "./context/ThemeContext";
import "./App.css";

// .app-content (not window) is the app's actual scrollable region -- see
// App.css's .app-shell (fixed height, overflow: hidden). Resets scroll on
// every route change (e.g. switching which project's dashboard is shown
// via ActivityBar) since there's no window scroll position for React
// Router's own <ScrollRestoration> (data-router only, this app uses a
// plain BrowserRouter) to restore in the first place. Must render inside
// <BrowserRouter> to call useLocation() -- App()'s own body executes
// outside the Router context, since App() is what returns <BrowserRouter>.
function ScrollToTopOnNavigate({ containerRef }: { containerRef: RefObject<HTMLDivElement | null> }) {
  const { pathname } = useLocation();
  useEffect(() => {
    containerRef.current?.scrollTo(0, 0);
  }, [pathname]);
  return null;
}

function App() {
  const appContentRef = useRef<HTMLDivElement>(null);
  return (
    <BrowserRouter>
      <ThemeProvider>
        <EventsProvider>
          <DemoModeProvider>
            <ScrollToTopOnNavigate containerRef={appContentRef} />
            <div className="app-shell">
              <Sidebar />
              <div className="app-content" ref={appContentRef}>
                <Routes>
                  <Route path="/" element={<Home />} />
                  <Route path="/projects" element={<ProjectList />} />
                  <Route path="/projects/new" element={<ProjectForm />} />
                  <Route path="/projects/:id/edit" element={<ProjectForm />} />
                  <Route path="/collectors" element={<CollectorList />} />
                  <Route path="/collectors/new" element={<CollectorEditor />} />
                  <Route path="/automaters" element={<AutomaterList />} />
                  <Route path="/automaters/new" element={<AutomaterEditor />} />
                  <Route path="/query-rules" element={<QueryRuleList />} />
                  <Route path="/query-rules/new" element={<QueryRuleEditor />} />
                  <Route path="/dashboards" element={<DashboardList />} />
                  <Route path="/dashboards/new" element={<DashboardForm />} />
                  <Route path="/dashboards/:id" element={<DashboardEditor />} />
                  <Route path="/dashboards/:dashboardId/panels/new" element={<PanelBuilder />} />
                  <Route path="/dashboards/:dashboardId/panels/:panelId/edit" element={<PanelBuilder />} />
                  <Route path="/dashboards/:dashboardId/variables" element={<VariableList />} />
                  <Route path="/dashboards/:dashboardId/variables/new" element={<VariableBuilder />} />
                  <Route
                    path="/dashboards/:dashboardId/variables/:variableName/edit"
                    element={<VariableBuilder />}
                  />
                  <Route path="/docs" element={<Docs />} />
                </Routes>
              </div>
              <EventsPanel />
              <ActivityBar />
            </div>
            <Toast />
          </DemoModeProvider>
        </EventsProvider>
      </ThemeProvider>
    </BrowserRouter>
  );
}

export default App;
