from pydantic import BaseModel


class TimescaleDBOutputConfig(BaseModel):
    connection: str = "postgresql://iotops:iotops@timescaledb:5432/iotops"
    table: str = "telemetry"
