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
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(f"AI SQL generation failed: {message}")


class QueryExecutionError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(f"Query failed: {message}")
