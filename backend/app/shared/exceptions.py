from uuid import UUID


class EntityNotFoundError(Exception):
    def __init__(self, entity: str, entity_id: UUID | str) -> None:
        self.entity = entity
        self.entity_id = entity_id
        super().__init__(f"{entity} {entity_id} not found")


class PluginConfigurationError(Exception):
    def __init__(self, plugin_type: str, message: str) -> None:
        self.plugin_type = plugin_type
        self.message = message
        super().__init__(f"Invalid configuration for plugin '{plugin_type}': {message}")


class InvalidQueryError(Exception):
    def __init__(self, sql: str) -> None:
        self.sql = sql
        super().__init__("Only single, read-only SELECT statements are allowed")


class DuplicateNameError(Exception):
    def __init__(self, entity: str, name: str) -> None:
        self.entity = entity
        self.name = name
        super().__init__(f"{entity} with name '{name}' already exists")


class AiGenerationError(Exception):
    # No blanket prefix here -- this covers every AI generation failure
    # (SQL generation AND Co-pilot chat/suggestions), and a hardcoded
    # "AI SQL generation failed" prefix was actively misleading for the
    # Co-pilot ones (e.g. an iteration-budget error had nothing to do with
    # SQL). Every call site already writes a complete, contextual message
    # of its own; the one site that's genuinely about SQL generation
    # (AiService._generate_sql_from_prompt's Ollama HTTP passthrough)
    # includes that framing itself instead.
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class QueryExecutionError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(f"Query failed: {message}")


class InvalidOperationError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class DemoModeError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)
