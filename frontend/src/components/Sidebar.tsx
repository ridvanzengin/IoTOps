import { NavLink } from "react-router-dom";
import { useEvents } from "../context/EventsContext";
import { AutomaterIcon, CollectorIcon, CopilotIcon, HomeIcon, ProjectIcon, ScheduleIcon, VisualizerIcon } from "./icons";
import type { ComponentType } from "react";
import type { SVGProps } from "react";
import "./Sidebar.css";

interface NavItem {
  label: string;
  to?: string;
  // For an item with no route of its own (AI Co-pilot -- it opens the
  // app-shell's EventsPanel in "copilot" mode, same as the ActivityBar's
  // own Co-pilot icon, not a page).
  onClick?: () => void;
  active?: boolean;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  end?: boolean;
  disabled?: boolean;
}

export function Sidebar() {
  const { activePanel, openCopilotPanel, closePanel } = useEvents();
  const copilotOpen = activePanel?.kind === "copilot";

  const navItems: NavItem[] = [
    { label: "Overview", to: "/", icon: HomeIcon, end: true },
    { label: "Projects", to: "/projects", icon: ProjectIcon },
    { label: "Data Ingestion", to: "/collectors", icon: CollectorIcon },
    { label: "Automation", to: "/automaters", icon: AutomaterIcon },
    { label: "Scheduled Rules", to: "/query-rules", icon: ScheduleIcon },
    { label: "Dashboards", to: "/dashboards", icon: VisualizerIcon },
    {
      label: "AI Co-pilot",
      icon: CopilotIcon,
      active: copilotOpen,
      onClick: () => (copilotOpen ? closePanel() : openCopilotPanel()),
    },
  ];

  return (
    <aside className="sidebar">
      <div className="sidebar__brand">
        <span className="sidebar__brand-mark">I</span>
        <span>IoTOps</span>
      </div>
      <nav className="sidebar__nav">
        {navItems.map((item) => {
          const Icon = item.icon;
          if (item.disabled) {
            return (
              <span key={item.label} className="sidebar__link sidebar__link--disabled">
                <Icon className="sidebar__icon" />
                {item.label}
                <span className="sidebar__badge">Soon</span>
              </span>
            );
          }
          if (item.onClick) {
            return (
              <button
                key={item.label}
                type="button"
                className={`sidebar__link sidebar__link--button${item.active ? " sidebar__link--active" : ""}`}
                onClick={item.onClick}
              >
                <Icon className="sidebar__icon" />
                {item.label}
              </button>
            );
          }
          return (
            <NavLink
              key={item.label}
              to={item.to!}
              end={item.end}
              className={({ isActive }) =>
                `sidebar__link${isActive ? " sidebar__link--active" : ""}`
              }
            >
              <Icon className="sidebar__icon" />
              {item.label}
            </NavLink>
          );
        })}
      </nav>
    </aside>
  );
}
