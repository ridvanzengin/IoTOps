from typing import Literal

from pydantic import BaseModel, Field


class MqttConsumerConfig(BaseModel):
    servers: list[str] = Field(default=["tcp://mosquitto:1883"], min_length=1)
    topics: list[str] = Field(default=["telemetry/#"], min_length=1)
    qos: Literal[0, 1, 2] = 0
    data_format: Literal["influx", "json", "value"] = "json"
