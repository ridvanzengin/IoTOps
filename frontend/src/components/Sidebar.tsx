import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import { useEvents } from "../context/EventsContext";
import {
  AutomaterIcon,
  ChevronIcon,
  CollectorIcon,
  CopilotIcon,
  DocumentationIcon,
  GithubIcon,
  HomeIcon,
  ProjectIcon,
  ScheduleIcon,
  VisualizerIcon,
} from "./icons";
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

interface ExternalNavItem {
  label: string;
  href: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
}

// Documentation is a real in-app route (renders inside the same app shell
// -- Sidebar + ActivityBar/EventsPanel stay visible), so it's a NavLink
// like the primary nav items, just grouped visually under "Reference".
const REFERENCE_NAV_ITEMS: NavItem[] = [{ label: "Documentation", to: "/docs", icon: DocumentationIcon }];

// Source Code leaves the app entirely -- a plain external link, not a route.
const EXTERNAL_LINKS: ExternalNavItem[] = [
  {
    label: "Source Code",
    href: "https://github.com/ridvanzengin/IoTOps",
    icon: GithubIcon,
  },
];

const COLLAPSED_STORAGE_KEY = "iotops:sidebar-collapsed";

function loadStoredCollapsed(): boolean {
  return typeof window !== "undefined" && window.localStorage.getItem(COLLAPSED_STORAGE_KEY) === "1";
}

function renderNavItem(item: NavItem, collapsed: boolean) {
  const Icon = item.icon;
  const title = collapsed ? item.label : undefined;
  if (item.disabled) {
    return (
      <span key={item.label} className="sidebar__link sidebar__link--disabled" title={title}>
        <Icon className="sidebar__icon" />
        {!collapsed && item.label}
        {!collapsed && <span className="sidebar__badge">Soon</span>}
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
        title={title}
      >
        <Icon className="sidebar__icon" />
        {!collapsed && item.label}
      </button>
    );
  }
  return (
    <NavLink
      key={item.label}
      to={item.to!}
      end={item.end}
      className={({ isActive }) => `sidebar__link${isActive ? " sidebar__link--active" : ""}`}
      title={title}
    >
      <Icon className="sidebar__icon" />
      {!collapsed && item.label}
    </NavLink>
  );
}

export function Sidebar() {
  const { activePanel, openCopilotPanel, closePanel } = useEvents();
  const copilotOpen = activePanel?.kind === "copilot";
  const [collapsed, setCollapsed] = useState(loadStoredCollapsed);

  useEffect(() => {
    window.localStorage.setItem(COLLAPSED_STORAGE_KEY, collapsed ? "1" : "0");
  }, [collapsed]);

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
    <aside className={`sidebar${collapsed ? " sidebar--collapsed" : ""}`}>
      <div className="sidebar__header">
        <NavLink to="/" end className="sidebar__brand" title={collapsed ? "IoTOps" : undefined}>
          <span className="sidebar__brand-mark">I</span>
          {!collapsed && <span>IoTOps</span>}
        </NavLink>
        <button
          type="button"
          className="sidebar__collapse-btn"
          onClick={() => setCollapsed((value) => !value)}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          <ChevronIcon className="sidebar__collapse-icon" />
        </button>
      </div>
      <nav className="sidebar__nav">
        {navItems.map((item) => renderNavItem(item, collapsed))}

        {!collapsed && <p className="sidebar__section-label">Reference</p>}
        {REFERENCE_NAV_ITEMS.map((item) => renderNavItem(item, collapsed))}
        {EXTERNAL_LINKS.map((item) => {
          const Icon = item.icon;
          return (
            <a
              key={item.label}
              href={item.href}
              target="_blank"
              rel="noopener noreferrer"
              className="sidebar__link"
              title={collapsed ? item.label : undefined}
            >
              <Icon className="sidebar__icon" />
              {!collapsed && item.label}
            </a>
          );
        })}
      </nav>
      <div className="sidebar__footer">
        <a
          href="https://ridvanzengin.github.io/"
          target="_blank"
          rel="noopener noreferrer"
          className="sidebar__attribution"
          title={collapsed ? "Built by Rıdvan Zengin" : undefined}
        >
          {collapsed ? "RZ" : "Built by Rıdvan Zengin"}
        </a>
      </div>
    </aside>
  );
}
