# IoTOps

Version: 0.1.0

---

# Vision

IoTOps is a self-hosted IoT Operations Platform that enables users to visually configure telemetry collection, automate event-driven workflows, and build interactive dashboards without manually writing Telegraf configuration files.

The platform abstracts infrastructure details behind a simple web interface while remaining extensible through a plugin-based architecture.

IoTOps is intended to support many different IoT domains including, but not limited to:

- Smart Beekeeping
- Industrial Monitoring
- Greenhouse Automation
- Weather Stations
- Smart Buildings
- Energy Monitoring
- Smart Home Systems

The platform itself is domain-agnostic. Domain-specific functionality should be implemented as reusable templates rather than hardcoded logic.

---

# Core Philosophy

The system is built around five principles.

## 1. Everything is a Model

Every object in the platform must have a corresponding Pydantic model.

Examples include:

- Data Collectors
- Dashboards
- Panels
- Queries
- Automation Rules
- Plugin Configurations
- Templates

Pydantic models are the source of truth.

The UI, API, Docker services, generated configuration files, and database documents are all derived from these models.

---

## 2. Infrastructure is an Implementation Detail

Users interact with Collectors.

Not Telegraf.

Users interact with Dashboards.

Not ECharts.

Users interact with Rules.

Not Telegraf processor plugins.

Internal technologies should remain hidden whenever possible.

---

## 3. Configuration Over Code

Users should configure the platform instead of programming it.

Examples:

✓ Build a Collector using forms.

✓ Create Dashboards visually.

✓ Build Automation Rules from UI components.

✓ Generate SQL using AI.

The user should rarely need to edit configuration files manually.

---

## 4. Modular Architecture

The platform consists of independent modules.

Current MVP modules:

- Collector
- Automater
- Visualizer

Future modules may include:

- Analytics
- Device Management
- User Management
- AI Assistant
- Template Marketplace

Modules should communicate through APIs, message queues, or databases rather than directly depending on each other's implementation.

---

## 5. Extensibility

IoTOps should be easy to extend.

New functionality should normally be implemented by:

- adding plugins
- adding templates
- adding dashboards
- adding automation actions

rather than modifying existing code.

---

# MVP Scope

This section predates [development-plan.md](development-plan.md)'s
phased v1/v1.1/v1.2 roadmap (that doc is the more current, authoritative
breakdown — check it for what's actually next). Restated in its terms:

**v1** (ship target — Collector + Telemetry + Dashboard, no automation, no AI):

- MQTT data collection
- Collector management
- Docker-based deployment
- TimescaleDB storage
- Dashboard management
- Interactive charts

**v1.1 fast-follow** (Automation Engine, not a v1 blocker):

- Rule-based event detection
- Celery event publishing

**v1.2 fast-follow** (AI Assistant, not a v1 blocker):

- SQL query editor
- AI-assisted SQL generation

Not included (no phase yet):

- Kubernetes
- Multi-user support
- Workspaces
- Complex event processing
- Window-based analytics
- Machine learning
- Device provisioning
- Authentication providers
- Remote agents
- Plugin marketplace

---

# Architecture Overview

The platform consists of three primary runtime modules.

## Collector

Responsible for telemetry collection.

Responsibilities:

- Generate Telegraf configuration
- Launch Docker container
- Subscribe to MQTT
- Write telemetry into TimescaleDB

---

## Automater

Responsible for event detection.

Responsibilities:

- Subscribe to MQTT
- Evaluate rule conditions
- Flag matching telemetry
- Publish events using custom Celery output plugin

The Automater intentionally performs only lightweight rule evaluation.

Complex analytics are outside the scope of the MVP.

---

## Visualizer

Responsible for presenting collected telemetry.

Responsibilities:

- Dashboard management
- SQL editor
- AI query generation
- Interactive charts
- Variables
- Time range controls

---

# Data Storage Philosophy

IoTOps intentionally separates operational data from configuration data.

## TimescaleDB

Stores only telemetry.

Examples:

- sensor measurements
- timestamps
- metric values

No application configuration should be stored here.

---

## MongoDB

Stores application objects.

Examples:

- Collectors
- Dashboards
- Panels
- Rules
- Templates
- Plugin configurations

MongoDB is considered the canonical storage for platform configuration.

---

# AI Philosophy

Artificial Intelligence assists the user.

It never replaces explicit configuration.

Examples:

✓ Generate SQL

✓ Explain SQL

✓ Suggest dashboards

✓ Generate collector configurations

AI should never silently modify platform configuration.

Users always approve generated changes.

---

# Design Principles

When implementing features, prefer:

- explicit models over dictionaries
- composition over inheritance
- validation over assumptions
- generated configuration over handwritten files
- small reusable services over monolithic code
- deterministic behavior over hidden automation

---

# Non-Goals

The platform is NOT intended to become:

- a SCADA system
- a PLC programming environment
- a distributed stream processing framework
- a machine learning platform
- a replacement for Kubernetes

These capabilities may integrate with IoTOps in the future but are outside the project's scope.

---

# Success Criteria

The MVP is considered successful when a user can:

1. Create an MQTT Collector from the UI.

2. Deploy the Collector as a Docker container.

3. Receive telemetry from MQTT.

4. Store telemetry in TimescaleDB.

5. Create an Automation Rule.

6. Trigger a Celery task when a rule matches.

7. Create a Dashboard.

8. Visualize telemetry.

9. Generate SQL using the local LLM.

10. Monitor an IoT system without manually editing configuration files.

---

# Long-Term Vision

IoTOps should become a reusable platform for building telemetry-driven applications.

Beekeeping is the first demonstration.

It should eventually be possible to deploy the same platform for many different industries by installing templates rather than writing new software.