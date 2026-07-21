import type { ComponentType, SVGProps } from "react";
import {
  AutomaterIcon,
  BellIcon,
  CollectorIcon,
  CopilotIcon,
  HomeIcon,
  ProjectIcon,
  ScheduleIcon,
  VisualizerIcon,
} from "../components/icons";
import "./Docs.css";

interface Feature {
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  title: string;
  route: string;
  body: React.ReactNode;
}

const FEATURES: Feature[] = [
  {
    icon: HomeIcon,
    title: "Overview",
    route: "/",
    body: (
      <p className="docs-p">
        A live operations summary across every Project: counts of Projects, Collectors, Automaters, Scheduled
        Rules, Dashboards, and unresolved Events, plus a System Health panel (collector/automater/scheduled-check
        status at a glance) and AI-generated suggestions for new rules, panels, or automations based on what's
        actually being ingested.
      </p>
    ),
  },
  {
    icon: ProjectIcon,
    title: "Projects",
    route: "/projects",
    body: (
      <p className="docs-p">
        The operational boundary that groups a set of Collectors, Rules, and Dashboards under one deployment
        (e.g. one physical site, one customer, one showcase). Most other pages are scoped to a Project.
      </p>
    ),
  },
  {
    icon: CollectorIcon,
    title: "Data Ingestion (Collectors)",
    route: "/collectors",
    body: (
      <>
        <p className="docs-p">
          Build a Collector visually — pick an input (<code className="docs-code">MQTT</code>,{" "}
          <code className="docs-code">HTTP</code>, <code className="docs-code">Kafka</code>, or{" "}
          <code className="docs-code">AMQP</code>), map its payload fields/tags, and IoTOps generates the Telegraf
          TOML and launches it as a Docker container writing into TimescaleDB. No manually-written config files.
        </p>
        <ul className="docs-list">
          <li>
            <strong>Live preview</strong> — see the generated TOML before deploying.
          </li>
          <li>
            <strong>Docker lifecycle</strong> — start/stop/restart and container health surfaced in the UI.
          </li>
        </ul>
      </>
    ),
  },
  {
    icon: AutomaterIcon,
    title: "Automation (real-time Rules)",
    route: "/automaters",
    body: (
      <>
        <p className="docs-p">
          An Automater reuses a Collector's input stream and evaluates Rules against every incoming message in
          real time, using a custom Telegraf processor plugin (<code className="docs-code">processors/rule</code>).
          Rules are AND/OR groups of field/tag comparisons, evaluated independently (not first-match-wins).
        </p>
        <ul className="docs-list">
          <li>
            <strong>Redis-backed dedup</strong> — a match fires once, stays suppressed until it clears or a TTL
            expires.
          </li>
          <li>
            <strong>Celery event publishing</strong> — matches are enqueued via a custom output plugin (
            <code className="docs-code">outputs/celery</code>) and land in the persisted Events store.
          </li>
        </ul>
      </>
    ),
  },
  {
    icon: ScheduleIcon,
    title: "Scheduled Rules (Query Rules)",
    route: "/query-rules",
    body: (
      <p className="docs-p">
        For checks a per-message stream processor can't express — correlating across tables, aggregating over a
        time window, comparing to a historical baseline — Query Rules run a SQL check against TimescaleDB on a
        timer (via Celery Beat) instead of evaluating one metric at a time.
      </p>
    ),
  },
  {
    icon: VisualizerIcon,
    title: "Dashboards",
    route: "/dashboards",
    body: (
      <>
        <p className="docs-p">
          A drag-resizable grid of Panels (time series, gauge, dual-axis, and more) backed by hand-written or
          AI-generated SQL against TimescaleDB.
        </p>
        <ul className="docs-list">
          <li>
            <strong>Variable Builder</strong> — dashboard-level filters that templatize a Panel's SQL.
          </li>
          <li>
            <strong>Event overlays</strong> — Rule match/clear occurrences render directly on top of the relevant
            chart's timeline.
          </li>
          <li>
            <strong>AI SQL builder</strong> — describe what you want in natural language; Google Gemini (the
            default backend) or Anthropic Claude drafts the query.
          </li>
        </ul>
      </>
    ),
  },
  {
    icon: CopilotIcon,
    title: "AI Co-pilot",
    route: "panel, all pages",
    body: (
      <p className="docs-p">
        A chat panel (not a separate page) for natural-language Q&amp;A, SQL generation/explanation, and
        automation/dashboard-panel/dashboard suggestions grounded in your live telemetry. Runs on Google
        Gemini by default (a free tier keeps the public demo's AI features running at no cost); Anthropic
        Claude is also supported as a self-hosted alternative backend. It drafts changes; it never applies
        them without explicit user approval.
      </p>
    ),
  },
  {
    icon: BellIcon,
    title: "Events",
    route: "sidebar, all pages",
    body: (
      <p className="docs-p">
        Every Rule match/clear is persisted (MongoDB) and streamed live (SSE) into an activity-bar sidebar
        available from any page — searchable, paginated, filterable by time range, with either auto-clear or
        manual-resolve semantics depending on the Rule.
      </p>
    ),
  },
];

export function Docs() {
  return (
    <div className="page">
      <div className="docs-page">
        <div className="docs-header">
          <h1 className="docs-title">Documentation</h1>
          <p className="docs-subtitle">
            IoTOps — a self-hosted IoT Operations Platform: visually configure telemetry collection, automate
            event-driven workflows, build dashboards, and get AI-assisted answers and suggestions — all
            without hand-writing Telegraf configuration files.
          </p>
        </div>

        <section className="docs-section">
          <h2 className="docs-section-title">About the Project</h2>
          <p className="docs-p">
            IoTOps abstracts Telegraf, MQTT/Kafka/AMQP brokers, Redis, and Celery behind a small set of domain
            objects — <strong>Collectors</strong>, <strong>Rules</strong>, and <strong>Dashboards</strong> — that
            users configure through forms instead of hand-editing config files. Every one of those objects is a
            Pydantic model; the UI, the generated Telegraf TOML, the Docker containers, and the MongoDB documents
            are all derived from the same source of truth. An AI Co-pilot sits across all of it — grounded in
            each project's own live telemetry, automation, dashboards, and event history.
          </p>
          <p className="docs-p">
            The platform is domain-agnostic — three showcases ship today (smart beekeeping over MQTT, solar
            farm monitoring over HTTP, and Kafka-based manufacturing telemetry), and the same
            Collector/Rule/Dashboard primitives apply just as well to any other telemetry-driven domain.
          </p>

          <div className="docs-stat-grid">
            <div className="docs-stat">
              <span className="docs-stat-value">4</span>
              <span className="docs-stat-label">
                Data source types
                <br />
                MQTT · HTTP · Kafka · AMQP
              </span>
            </div>
            <div className="docs-stat">
              <span className="docs-stat-value">2</span>
              <span className="docs-stat-label">
                Custom Telegraf plugins
                <br />
                rule processor · celery output
              </span>
            </div>
            <div className="docs-stat">
              <span className="docs-stat-value">550+</span>
              <span className="docs-stat-label">
                Backend tests
                <br />
                pytest, Python
              </span>
            </div>
            <div className="docs-stat">
              <span className="docs-stat-value">v1.2</span>
              <span className="docs-stat-label">
                Current milestone
                <br />
                AI Assistant
              </span>
            </div>
          </div>
        </section>

        <section className="docs-section">
          <h2 className="docs-section-title">Features</h2>
          <div className="docs-features-grid">
            {FEATURES.map((feature) => {
              const Icon = feature.icon;
              return (
                <div className="docs-feature-card" key={feature.title}>
                  <div className="docs-feature-header">
                    <Icon className="docs-feature-icon" />
                    <h3 className="docs-feature-title">{feature.title}</h3>
                    <span className="docs-feature-route">{feature.route}</span>
                  </div>
                  {feature.body}
                </div>
              );
            })}
          </div>
        </section>

        <section className="docs-section">
          <h2 className="docs-section-title">Technical Overview</h2>
          <table className="docs-table">
            <thead>
              <tr>
                <th>Layer</th>
                <th>Technology</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Backend API</td>
                <td>FastAPI (Python), Pydantic models as the canonical domain representation</td>
              </tr>
              <tr>
                <td>Frontend</td>
                <td>React + TypeScript + Vite</td>
              </tr>
              <tr>
                <td>Telemetry storage</td>
                <td>TimescaleDB (continuous numeric data only)</td>
              </tr>
              <tr>
                <td>Config storage</td>
                <td>MongoDB (Collectors, Rules, Dashboards, Events)</td>
              </tr>
              <tr>
                <td>Messaging</td>
                <td>MQTT (Mosquitto), Kafka, AMQP (RabbitMQ), Redis (Celery broker)</td>
              </tr>
              <tr>
                <td>Runtime</td>
                <td>Docker containers running a custom Telegraf build (Collector + Automater services)</td>
              </tr>
              <tr>
                <td>Async tasks</td>
                <td>Celery workers + Celery Beat (scheduled Query Rules)</td>
              </tr>
              <tr>
                <td>AI</td>
                <td>Google Gemini (default) or Anthropic API (Claude) — SQL generation/explanation, Co-pilot Q&amp;A and suggestions</td>
              </tr>
              <tr>
                <td>Custom Telegraf plugins</td>
                <td>
                  <a href="https://github.com/ridvanzengin/custom-telegraf" target="_blank" rel="noopener noreferrer">
                    custom-telegraf
                  </a>{" "}
                  — <code className="docs-code">processors/rule</code>,{" "}
                  <code className="docs-code">outputs/celery</code>, a separate Go repo consumed only as a built
                  Docker image
                </td>
              </tr>
            </tbody>
          </table>
        </section>

        <section className="docs-section">
          <h2 className="docs-section-title">Getting Started</h2>
          <p className="docs-p">Clone the repo, copy the env template, and bring the stack up:</p>
          <pre className="docs-block">{"cp .env.example .env\ndocker compose up"}</pre>
          <ul className="docs-list">
            <li>
              Backend health: <code className="docs-code">http://localhost:8000/health</code>
            </li>
            <li>
              Frontend: <code className="docs-code">http://localhost:5173</code>
            </li>
          </ul>
          <p className="docs-p">
            For architecture, domain model, and repository-layout detail, see the{" "}
            <a
              href="https://github.com/ridvanzengin/IoTOps/tree/main/docs"
              target="_blank"
              rel="noopener noreferrer"
            >
              docs/
            </a>{" "}
            folder in the repo — <code className="docs-code">vision.md</code>,{" "}
            <code className="docs-code">architecture.md</code>, <code className="docs-code">domain-models.md</code>,{" "}
            <code className="docs-code">repository-structure.md</code>, and{" "}
            <code className="docs-code">development-plan.md</code> for the phased roadmap.
          </p>
        </section>

        <div className="docs-footer">
          <a href="https://github.com/ridvanzengin/IoTOps/blob/main/LICENSE" target="_blank" rel="noopener noreferrer">
            MIT Licensed
          </a>
        </div>
      </div>
    </div>
  );
}
