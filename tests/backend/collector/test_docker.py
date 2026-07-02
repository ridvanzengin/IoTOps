from pathlib import Path

import pytest
from docker.errors import NotFound

from app.collector.docker import CollectorDockerManager
from app.collector.models import Collector, InputPlugin, OutputPlugin
from app.shared.enums import CollectorStatus


class FakeContainer:
    def __init__(self, name: str, status: str = "created") -> None:
        self.name = name
        # Mirrors real docker-py: attrs on the object returned by
        # containers.run() are stale until reload() is called, since the
        # daemon has already transitioned the container to "running" by
        # the time run() returns.
        self.status = status
        self._live_status = "running" if status == "created" else status
        self.removed = False

    def reload(self) -> None:
        self.status = self._live_status

    def stop(self) -> None:
        self._live_status = "exited"
        self.status = "exited"

    def remove(self, force: bool = False) -> None:
        self.removed = True


class FakeContainerCollection:
    def __init__(self) -> None:
        self.containers: dict[str, FakeContainer] = {}
        self.run_calls: list[dict[str, object]] = []

    def run(self, image: str, **kwargs: object) -> FakeContainer:
        name = kwargs["name"]
        self.run_calls.append({"image": image, **kwargs})
        container = FakeContainer(str(name))
        self.containers[str(name)] = container
        return container

    def get(self, name: str) -> FakeContainer:
        try:
            return self.containers[name]
        except KeyError:
            raise NotFound(f"container {name} not found") from None


class FakeDockerClient:
    def __init__(self) -> None:
        self.containers = FakeContainerCollection()


def _collector() -> Collector:
    return Collector(
        name="Hive Collector",
        inputs=[InputPlugin(plugin_type="mqtt", name="hive-mqtt")],
        outputs=[OutputPlugin(plugin_type="timescaledb")],
    )


def _manager(tmp_path: Path, client: FakeDockerClient) -> CollectorDockerManager:
    return CollectorDockerManager(
        client=client,  # type: ignore[arg-type]
        runtime_dir=tmp_path / "runtime",
        host_runtime_dir=Path("/host/runtime"),
    )


def test_deploy_writes_config_and_starts_container(tmp_path: Path) -> None:
    client = FakeDockerClient()
    manager = _manager(tmp_path, client)
    collector = _collector()

    manager.deploy(collector, "toml contents")

    written = tmp_path / "runtime" / "collectors" / str(collector.id) / "telegraf.conf"
    assert written.read_text() == "toml contents"
    assert collector.docker is not None
    assert collector.docker.container_name == f"iotops-collector-{collector.id}"
    assert collector.status == CollectorStatus.RUNNING

    [run_call] = client.containers.run_calls
    assert run_call["network"] == "iotops"
    bind_source = next(iter(run_call["volumes"]))  # type: ignore[arg-type]
    assert bind_source == str(
        Path("/host/runtime") / "collectors" / str(collector.id) / "telegraf.conf"
    )


def test_deploy_removes_pre_existing_container_with_same_name(tmp_path: Path) -> None:
    client = FakeDockerClient()
    manager = _manager(tmp_path, client)
    collector = _collector()
    container_name = f"iotops-collector-{collector.id}"
    stale = FakeContainer(container_name)
    client.containers.containers[container_name] = stale

    manager.deploy(collector, "toml contents")

    assert stale.removed is True


def test_stop_updates_status(tmp_path: Path) -> None:
    client = FakeDockerClient()
    manager = _manager(tmp_path, client)
    collector = _collector()
    manager.deploy(collector, "toml contents")

    manager.stop(collector)

    assert collector.status == CollectorStatus.STOPPED


def test_stop_requires_prior_deployment(tmp_path: Path) -> None:
    client = FakeDockerClient()
    manager = _manager(tmp_path, client)
    collector = _collector()

    with pytest.raises(ValueError, match="has not been deployed"):
        manager.stop(collector)


def test_remove_is_a_no_op_when_never_deployed(tmp_path: Path) -> None:
    client = FakeDockerClient()
    manager = _manager(tmp_path, client)
    collector = _collector()

    manager.remove(collector)


def test_refresh_status_reflects_missing_container(tmp_path: Path) -> None:
    client = FakeDockerClient()
    manager = _manager(tmp_path, client)
    collector = _collector()
    manager.deploy(collector, "toml contents")
    client.containers.containers.clear()

    manager.refresh_status(collector)

    assert collector.status == CollectorStatus.STOPPED
