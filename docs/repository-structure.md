# Repository Structure

Version: 0.1.0

---

# Philosophy

The repository is organized around business domains rather than technologies.

Avoid structures like

backend/
    routes/
    models/
    services/

Instead prefer

backend/
    collector/
    automater/
    dashboard/
    plugins/

Each module owns its API, models, services and business logic.

---

# Repository Layout

iotops/

│

├── backend/

├── frontend/

├── plugins/

├── runtime/

├── docs/

├── scripts/

├── docker/

├── examples/

├── tests/

├── docker-compose.yml

├── README.md

└── .env.example

---

# Backend Layout

backend/

    app/

        main.py

        config.py

        dependencies.py

        database.py

        docker.py

        ai/

        collector/

        automater/

        dashboard/

        plugin/

        shared/

Each directory represents a domain.

---

# Collector Module

collector/

    api.py

    models.py

    service.py

    repository.py

    generator.py

    docker.py

Responsibilities

- collector CRUD

- generate telegraf.conf

- docker lifecycle

- validation

---

# Automater Module

automater/

    api.py

    models.py

    service.py

    repository.py

Responsibilities

- rule management

- automater CRUD

- deployment

---

# Dashboard Module

dashboard/

    api.py

    models.py

    service.py

    repository.py

Responsibilities

- dashboards

- panels

- variables

- layouts

---

# Plugin Module

plugin/

    api.py

    models.py

    registry.py

    generator.py

Responsibilities

- plugin registry

- plugin metadata

- schema lookup

- TOML generation

---

# AI Module

ai/

    api.py

    service.py

    prompts.py

Responsibilities

- SQL generation

- SQL explanation

Future

- dashboard generation

- collector generation

---

# Shared Module

shared/

contains reusable components.

Examples

exceptions.py

responses.py

enums.py

validators.py

utils.py

logging.py

---

# Frontend Layout

frontend/

    src/

        api/

        components/

        pages/

        hooks/

        stores/

        layouts/

        charts/

        types/

        utils/

---

# Pages

pages/

CollectorList

CollectorEditor

AutomaterList

AutomaterEditor

DashboardList

DashboardEditor

Settings

Home

---

# Components

Reusable UI only.

Examples

Button

Card

Table

Dialog

CodeEditor

PluginForm

PanelEditor

ChartPreview

---

# API Layer

Every HTTP request belongs here.

api/

collector.ts

dashboard.ts

automater.ts

ai.ts

Never make HTTP requests directly from components.

---

# Types

Contains TypeScript models.

These should mirror backend Pydantic models whenever practical.

---

# Runtime Directory

runtime/

collectors/

automater/

Generated configuration files live here.

Nothing inside runtime should be committed to Git.

---

# Plugins Directory

plugins/

telegraf/

processor/

output/

Contains source code for custom Telegraf plugins.

Examples

rule_processor/

celery_output/

Each plugin should have its own README.

---

# Scripts

scripts/

development

build

cleanup

generate

Used for developer tooling only.

No application logic belongs here.

---

# Docker

docker/

backend/

frontend/

plugins/

Contains Dockerfiles only.

No compose files.

---

# Tests

tests/

backend/

frontend/

integration/

fixtures/

tests should mirror the source tree.

---

# Naming Conventions

Directories

lowercase

singular

collector

dashboard

plugin

Files

snake_case.py

collector_service.py

panel_models.py

Classes

PascalCase

Collector

Dashboard

RuleProcessor

Functions

snake_case

generate_config()

deploy_container()

validate_rule()

Variables

snake_case

collector_id

dashboard_name

plugin_type

Constants

UPPER_CASE

DEFAULT_TIMEOUT

DEFAULT_TOPIC

---

# API Conventions

REST endpoints

/api/collector

/api/dashboard

/api/automater

/api/plugin

Never use verbs.

Correct

POST /collector

DELETE /collector/{id}

Incorrect

/createCollector

/deleteCollector

---

# Database Rules

Mongo stores

configuration

Timescale stores

telemetry

Never mix them.

---

# Business Rules

Every domain owns

models

repository

service

api

Avoid cross-domain imports whenever possible.

Use services instead.

---

# Docker Rules

Only the backend controls Docker.

Frontend never communicates with Docker directly.

Generated configuration files should never be edited manually.

---

# Logging

Use Python logging.

Never use print().

Logs should include

timestamp

service

level

message

---

# Error Handling

Raise exceptions.

Never return None to indicate failure.

Convert exceptions into HTTP responses in the API layer.

---

# Configuration

Environment variables belong in

.env

Configuration loading belongs in

config.py

Never access os.environ directly outside config.py.

---

# Pydantic

Every object crossing an API boundary must have a Pydantic model.

Never accept arbitrary dictionaries.

---

# Mongo

Repositories return models.

Not dictionaries.

---

# Frontend

Pages own state.

Components receive props.

Avoid business logic inside components.

---

# Rule

Whenever adding a new feature ask

Which module owns this?

If the answer is unclear

the architecture is probably wrong.