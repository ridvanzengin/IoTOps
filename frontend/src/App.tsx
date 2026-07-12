import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Home } from "./pages/Home";
import { AutomaterList } from "./pages/AutomaterList";
import { AutomaterEditor } from "./pages/AutomaterEditor";
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
import { Sidebar } from "./components/Sidebar";
import { ActivityBar } from "./components/ActivityBar";
import { EventsPanel } from "./components/EventsPanel";
import { EventsProvider } from "./context/EventsContext";
import "./App.css";

function App() {
  return (
    <BrowserRouter>
      <EventsProvider>
        <div className="app-shell">
          <Sidebar />
          <div className="app-content">
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/projects" element={<ProjectList />} />
              <Route path="/projects/new" element={<ProjectForm />} />
              <Route path="/projects/:id/edit" element={<ProjectForm />} />
              <Route path="/collectors" element={<CollectorList />} />
              <Route path="/collectors/new" element={<CollectorEditor />} />
              <Route path="/automaters" element={<AutomaterList />} />
              <Route path="/automaters/new" element={<AutomaterEditor />} />
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
            </Routes>
          </div>
          <EventsPanel />
          <ActivityBar />
        </div>
      </EventsProvider>
    </BrowserRouter>
  );
}

export default App;
