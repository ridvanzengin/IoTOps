from enum import Enum


class CollectorStatus(str, Enum):
    CREATED = "created"
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    UNHEALTHY = "unhealthy"
    STOPPING = "stopping"
    ERROR = "error"


class PluginCategory(str, Enum):
    INPUT = "input"
    PROCESSOR = "processor"
    OUTPUT = "output"
