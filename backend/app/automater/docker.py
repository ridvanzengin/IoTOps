import shutil
from pathlib import Path

import docker
from docker.errors import NotFound
from docker.models.containers import Container

from app.automater.models import Automater
from app.shared.enums import CollectorStatus
from app.shared.models import DockerConfig

_CONTAINER_STATE_MAP = {
    "created": CollectorStatus.CREATED,
    "running": CollectorStatus.RUNNING,
    "paused": CollectorStatus.STOPPED,
    "restarting": CollectorStatus.STARTING,
    "removing": CollectorStatus.STOPPING,
    "exited": CollectorStatus.STOPPED,
    "dead": CollectorStatus.ERROR,
}


def _container_name(automater: Automater) -> str:
    return f"iotops-automater-{automater.id}"


class AutomaterDockerManager:
    def __init__(
        self,
        client: docker.DockerClient,
        runtime_dir: Path,
        host_runtime_dir: Path,
        network: str = "iotops",
        telegraf_image: str = "custom-telegraf:latest",
    ) -> None:
        self._client = client
        self._runtime_dir = runtime_dir
        self._host_runtime_dir = host_runtime_dir
        self._network = network
        self._telegraf_image = telegraf_image

    def deploy(self, automater: Automater, toml_config: str) -> Automater:
        config_path = self._write_config(automater, toml_config)
        container_name = _container_name(automater)
        self._remove_container(container_name)

        container = self._client.containers.run(
            self._telegraf_image,
            name=container_name,
            detach=True,
            network=self._network,
            restart_policy={"Name": "unless-stopped"},
            volumes={str(config_path): {"bind": "/etc/telegraf/telegraf.conf", "mode": "ro"}},
        )

        automater.docker = DockerConfig(
            image=self._telegraf_image,
            container_name=container_name,
            network=self._network,
            restart_policy="unless-stopped",
            volumes=[f"{config_path}:/etc/telegraf/telegraf.conf:ro"],
        )
        container.reload()
        automater.status = _CONTAINER_STATE_MAP.get(container.status, CollectorStatus.ERROR)
        return automater

    def stop(self, automater: Automater) -> Automater:
        container = self._get_container(automater)
        container.stop()
        automater.status = CollectorStatus.STOPPED
        return automater

    def remove(self, automater: Automater) -> None:
        if automater.docker is None:
            return
        self._remove_container(automater.docker.container_name)
        self._delete_config_dir(automater)

    def refresh_status(self, automater: Automater) -> Automater:
        container = self._get_container(automater, required=False)
        if container is None:
            automater.status = CollectorStatus.STOPPED
            return automater
        container.reload()
        automater.status = _CONTAINER_STATE_MAP.get(container.status, CollectorStatus.ERROR)
        return automater

    def _get_container(self, automater: Automater, required: bool = True) -> Container | None:
        if automater.docker is None:
            if required:
                raise ValueError(f"Automater {automater.id} has not been deployed")
            return None
        try:
            return self._client.containers.get(automater.docker.container_name)
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

    def _write_config(self, automater: Automater, toml_config: str) -> Path:
        local_dir = self._runtime_dir / "automaters" / str(automater.id)
        local_dir.mkdir(parents=True, exist_ok=True)
        (local_dir / "telegraf.conf").write_text(toml_config)
        return self._host_runtime_dir / "automaters" / str(automater.id) / "telegraf.conf"

    def _delete_config_dir(self, automater: Automater) -> None:
        local_dir = self._runtime_dir / "automaters" / str(automater.id)
        shutil.rmtree(local_dir, ignore_errors=True)
