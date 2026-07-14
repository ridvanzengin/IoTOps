import { NavLink } from "react-router-dom";
import { AutomaterIcon, CollectorIcon, HomeIcon, ProjectIcon, ScheduleIcon, VisualizerIcon } from "./icons";
import type { ComponentType } from "react";
import type { SVGProps } from "react";
import "./Sidebar.css";

interface NavItem {
  label: string;
  to?: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  end?: boolean;
  disabled?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { label: "Overview", to: "/", icon: HomeIcon, end: true },
  { label: "Projects", to: "/projects", icon: ProjectIcon },
  { label: "Data Ingestion", to: "/collectors", icon: CollectorIcon },
  { label: "Automation", to: "/automaters", icon: AutomaterIcon },
  { label: "Scheduled Rules", to: "/query-rules", icon: ScheduleIcon },
  { label: "Dashboards", to: "/dashboards", icon: VisualizerIcon },
];

export function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="sidebar__brand">
        <span className="sidebar__brand-mark">I</span>
        <span>IoTOps</span>
      </div>
      <nav className="sidebar__nav">
        {NAV_ITEMS.map((item) => {
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
