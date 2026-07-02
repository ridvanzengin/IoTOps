import shutil
from pathlib import Path

import docker
from docker.errors import NotFound
from docker.models.containers import Container

from app.collector.models import Collector, DockerConfig
from app.shared.enums import CollectorStatus

_CONTAINER_STATE_MAP = {
    "created": CollectorStatus.CREATED,
    "running": CollectorStatus.RUNNING,
    "paused": CollectorStatus.STOPPED,
    "restarting": CollectorStatus.STARTING,
    "removing": CollectorStatus.STOPPING,
    "exited": CollectorStatus.STOPPED,
    "dead": CollectorStatus.ERROR,
}


def _container_name(collector: Collector) -> str:
    return f"iotops-collector-{collector.id}"


class CollectorDockerManager:
    def __init__(
        self,
        client: docker.DockerClient,
        runtime_dir: Path,
        host_runtime_dir: Path,
        network: str = "iotops",
        telegraf_image: str = "telegraf:1.32-alpine",
    ) -> None:
        self._client = client
        self._runtime_dir = runtime_dir
        self._host_runtime_dir = host_runtime_dir
        self._network = network
        self._telegraf_image = telegraf_image

    def deploy(self, collector: Collector, toml_config: str) -> Collector:
        config_path = self._write_config(collector, toml_config)
        container_name = _container_name(collector)
        self._remove_container(container_name)

        container = self._client.containers.run(
            self._telegraf_image,
            name=container_name,
            detach=True,
            network=self._network,
            restart_policy={"Name": "unless-stopped"},
            volumes={str(config_path): {"bind": "/etc/telegraf/telegraf.conf", "mode": "ro"}},
        )

        collector.docker = DockerConfig(
            image=self._telegraf_image,
            container_name=container_name,
            network=self._network,
            restart_policy="unless-stopped",
            volumes=[f"{config_path}:/etc/telegraf/telegraf.conf:ro"],
        )
        container.reload()
        collector.status = _CONTAINER_STATE_MAP.get(container.status, CollectorStatus.ERROR)
        return collector

    def stop(self, collector: Collector) -> Collector:
        container = self._get_container(collector)
        container.stop()
        collector.status = CollectorStatus.STOPPED
        return collector

    def remove(self, collector: Collector) -> None:
        if collector.docker is None:
            return
        self._remove_container(collector.docker.container_name)
        self._delete_config_dir(collector)

    def refresh_status(self, collector: Collector) -> Collector:
        container = self._get_container(collector, required=False)
        if container is None:
            collector.status = CollectorStatus.STOPPED
            return collector
        container.reload()
        collector.status = _CONTAINER_STATE_MAP.get(container.status, CollectorStatus.ERROR)
        return collector

    def _get_container(self, collector: Collector, required: bool = True) -> Container | None:
        if collector.docker is None:
            if required:
                raise ValueError(f"Collector {collector.id} has not been deployed")
            return None
        try:
            return self._client.containers.get(collector.docker.container_name)
        except NotFound:
            if required:
                raise
            return None

    def _remove_container(self, container_name: str) -> None:
        try:
            container = self._client.containers.get(container_name)
        except NotFound:
            return
        container.remove(force=True)

    def _write_config(self, collector: Collector, toml_config: str) -> Path:
        local_dir = self._runtime_dir / "collectors" / str(collector.id)
        local_dir.mkdir(parents=True, exist_ok=True)
        (local_dir / "telegraf.conf").write_text(toml_config)
        return self._host_runtime_dir / "collectors" / str(collector.id) / "telegraf.conf"

    def _delete_config_dir(self, collector: Collector) -> None:
        local_dir = self._runtime_dir / "collectors" / str(collector.id)
        shutil.rmtree(local_dir, ignore_errors=True)
