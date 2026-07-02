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
