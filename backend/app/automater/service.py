from typing import Any
from uuid import UUID, uuid4

from urllib.parse import urlsplit

from app.automater.docker import AutomaterDockerManager
from app.automater.models import Automater, AutomaterInput, Rule
from app.automater.repository import AutomaterRepository
from app.collector.generator import generate_toml
from app.collector.models import Collector
from app.collector.service import CollectorService
from app.plugin.processors.rule import DeployedRule
from app.plugin.registry import PluginRegistry
from app.shared.exceptions import EntityNotFoundError, InvalidOperationError
from app.shared.models import InputPlugin, OutputPlugin, ProcessorPlugin

_RULE_PLUGIN_TYPE = "rule"
_CELERY_TASK_NAME = "automater.tasks.log_rule_match"
_HTTP_FORWARD_PLUGIN_TYPE = "http_forward"
_HTTP_INPUT_PLUGIN_TYPE = "http"


class AutomaterService:
    def __init__(
        self,
        repository: AutomaterRepository,
        registry: PluginRegistry,
        docker_manager: AutomaterDockerManager,
        collector_service: CollectorService,
    ) -> None:
        self._repository = repository
        self._registry = registry
        self._docker_manager = docker_manager
        self._collector_service = collector_service

    async def create(self, payload: AutomaterInput) -> Automater:
        automater = Automater(**payload.model_dump())
        self._validate_plugin_configurations(automater)
        return await self._repository.create(automater)

    async def create_rule(
        self,
        project_id: UUID,
        rule: Rule,
        automater_id: UUID | None,
        automater_name: str | None,
        automater_description: str,
        collector_id: UUID | None,
    ) -> Automater:
        if automater_id is not None:
            automater = await self._repository.get(automater_id)
            if automater.project_id != project_id:
                raise InvalidOperationError(
                    f"Automater {automater_id} does not belong to project {project_id}"
                )
            # An Automater can watch more than one table -- mirrors how a
            # Collector can already have more than one mqtt input. If this
            # Automater has no input for the new rule's table yet, add one
            # (derived from the given Collector) rather than deploying a
            # rule that can never match anything (the Go plugin only
            # evaluates a rule against metrics whose name equals its
            # table). Already-covered tables need no collector_id at all --
            # existing behavior, unchanged.
            if not self._has_input_for_table(automater, rule.table):
                if collector_id is None:
                    raise InvalidOperationError(
                        f"Automater {automater_id} has no input for table {rule.table!r} yet; "
                        "collector_id is required to add one"
                    )
                collector = await self._collector_service.get(collector_id)
                matched_input = self._find_input_for_table(collector, rule.table)
                automater.inputs.append(
                    InputPlugin(
                        plugin_type=matched_input.plugin_type,
                        name=matched_input.name,
                        enabled=True,
                        configuration=self._automater_scoped_configuration(matched_input.configuration),
                    )
                )
                await self._ensure_http_forwarding(collector, automater, matched_input)
            automater.rules.append(rule)
        else:
            if not automater_name:
                raise InvalidOperationError(
                    "automater_name is required when creating a new Automater"
                )
            if collector_id is None:
                raise InvalidOperationError(
                    "collector_id is required when creating a new Automater"
                )
            collector = await self._collector_service.get(collector_id)
            matched_input = self._find_input_for_table(collector, rule.table)

            automater = Automater(
                project_id=project_id,
                name=automater_name,
                description=automater_description,
                inputs=[
                    InputPlugin(
                        plugin_type=matched_input.plugin_type,
                        name=matched_input.name,
                        enabled=True,
                        configuration=self._automater_scoped_configuration(matched_input.configuration),
                    )
                ],
                rules=[rule],
                outputs=[
                    OutputPlugin(
                        plugin_type="celery",
                        enabled=True,
                        configuration={"task_name": _CELERY_TASK_NAME},
                    )
                ],
            )
            self._validate_plugin_configurations(automater)
            automater = await self._repository.create(automater)
            await self._ensure_http_forwarding(collector, automater, matched_input)

        return await self._redeploy_or_stop(automater)

    def _has_input_for_table(self, automater: Automater, table: str) -> bool:
        # Not scoped to any particular plugin_type -- an Automater's input
        # can be derived from any of a Collector's input plugins (mqtt,
        # kafka, http, amqp, ...), matched purely by which TimescaleDB
        # table it feeds. See iotops-workspace/ROADMAP.md's data-sources
        # note.
        return any(i.configuration.get("name_override") == table for i in automater.inputs)

    def _find_input_for_table(self, collector: Collector, table: str) -> InputPlugin:
        matched_input = next(
            (i for i in collector.inputs if i.configuration.get("name_override") == table),
            None,
        )
        if matched_input is None:
            raise InvalidOperationError(f"Collector {collector.id} has no input for table {table!r}")
        return matched_input

    def _automater_scoped_configuration(self, configuration: dict[str, Any]) -> dict[str, Any]:
        """Kafka consumer groups and AMQP queues are competing-consumer
        patterns, unlike MQTT's (and Kafka/AMQP's own, across *different*
        groups/queues) broadcast pub/sub -- if the Automater's derived
        input reused the Collector's exact consumer_group/queue verbatim,
        the two would split incoming messages between them (Kafka/AMQP
        both load-balance same-group/same-queue consumers) instead of
        each getting its own full copy, silently dropping ~50% of the
        data -- and matches -- on each side. Scoping these to a value
        distinct from the Collector's own gives the Automater an
        independent full copy of the same stream (a second queue bound to
        the same exchange, or a second consumer group on the same topic),
        the same effect MQTT/HTTP get for free since neither has a
        competing-consumer concept. A no-op for plugin types with neither
        field. See iotops-workspace/ROADMAP.md's data-sources note.

        http's `read_timeout`/`write_timeout` (HttpListenerConfig, default
        "10s" each) get bumped for a different, unrelated reason, live-
        verified while building the Collector-forwards-to-Automater fix
        (see ROADMAP.md's "Automater fan-out strategy" note): Go's
        net/http.Server falls back to ReadTimeout as its *idle keep-alive
        timeout* whenever IdleTimeout isn't set separately, and
        http_listener_v2 exposes no separate idle-timeout option
        (confirmed via `telegraf --usage http_listener_v2`). That default
        exactly matches this platform's fixed 10s flush_interval on the
        Collector's forwarding `outputs.http` -- a near-guaranteed race
        between the client reusing a pooled keep-alive connection and the
        server closing it as idle at the same moment, reproduced as a
        consistent (not occasional) `EOF`/`connection reset by
        peer`/`server closed idle connection` failure on every single
        forward. Bumped well clear of the flush interval so keep-alive
        connections comfortably survive many flush cycles.

        http's `data_format` is forced to "influx" for the same
        live-verification reason (see HttpOutputConfig's own comment,
        app/plugin/outputs/http.py): Telegraf's output JSON serializer and
        input JSON parser are different, non-interoperable shapes -- a
        "json"-configured listener silently receives well-formed-but-
        empty metrics from a forwarded request (no error anywhere, the
        expected fields/tags just never appear, so no rule can ever
        match). Safe to override unconditionally here because this
        listener's only sender is the Collector's forwarding output by
        design -- a real external webhook always targets the Collector's
        own URL, never the Automater's directly.

        Switching parsers means dropping the JSON-parser-only fields
        (`tag_keys`/`json_string_fields`/etc.) too, not just flipping
        `data_format` -- also live-verified: Telegraf's strict config
        validation crash-loops the container ("configuration specified
        the fields [...], but they were not used") if a field only
        `parsers.json` understands is still set once `data_format` no
        longer selects it. Not a loss: line protocol carries tags
        natively in the wire format, so `tag_keys`' JSON-object-key-to-tag
        promotion has nothing left to do once the Collector's own
        `outputs.http` (already influx-serializing the already-tagged
        metric) is what's sending it.
        """
        scoped = dict(configuration)
        suffix = uuid4().hex[:8]
        if "consumer_group" in scoped:
            scoped["consumer_group"] = f"{scoped['consumer_group']}-automater-{suffix}"
        if "queue" in scoped:
            scoped["queue"] = f"{scoped['queue']}-automater-{suffix}"
        if "read_timeout" in scoped:
            scoped["read_timeout"] = "60s"
        if "write_timeout" in scoped:
            scoped["write_timeout"] = "60s"
        if "service_address" in scoped:
            scoped["data_format"] = "influx"
            for json_parser_only_field in (
                "tag_keys",
                "json_string_fields",
                "json_time_key",
                "json_time_format",
                "json_timezone",
                "data_type",
            ):
                scoped.pop(json_parser_only_field, None)
        return scoped

    async def _ensure_http_forwarding(
        self, collector: Collector, automater: Automater, matched_input: InputPlugin
    ) -> None:
        """A webhook push has no broker to fan out to multiple independent
        listeners -- unlike mqtt/kafka/amqp, only one of the Collector's and
        Automater's own `http_listener_v2` instances would ever actually
        receive a given push. Fix: the Collector forwards a copy of what it
        received to the Automater's own listener via a new `outputs.http`
        block, rather than the Automater trying to listen for a push that
        will never reach it. A no-op for every other plugin_type, which
        already get a full independent copy via their broker's native
        fan-out. See iotops-workspace/ROADMAP.md's "Automater fan-out
        strategy" note.
        """
        if matched_input.plugin_type != _HTTP_INPUT_PLUGIN_TYPE:
            return
        forward_url = self._http_forward_url(automater.id, matched_input.configuration)
        # Keyed on (automater_id, url) rather than automater_id alone: a
        # multi-table Automater can derive two different http tables from
        # the same Collector, each necessarily on its own port (the
        # Collector itself couldn't start two http_listener_v2 inputs on
        # the same port either), so each needs its own forwarding output
        # rather than the second being silently skipped.
        already_forwarding = any(
            o.plugin_type == _HTTP_FORWARD_PLUGIN_TYPE
            and o.automater_id == automater.id
            and o.configuration.get("url") == forward_url
            for o in collector.outputs
        )
        if already_forwarding:
            return
        collector.outputs.append(
            OutputPlugin(
                plugin_type=_HTTP_FORWARD_PLUGIN_TYPE,
                automater_id=automater.id,
                configuration={"url": forward_url},
            )
        )
        await self._collector_service.redeploy_if_running(collector)

    def _http_forward_url(self, automater_id: UUID, http_input_configuration: dict[str, Any]) -> str:
        # Mirrors _container_name's convention in automater/docker.py --
        # containers reach each other by name on the shared docker network
        # regardless of published ports. The Automater's own copied
        # http_listener_v2 input carries an identical service_address/paths
        # (see _automater_scoped_configuration -- a no-op for http, no
        # consumer_group/queue to rewrite), so the Collector's own input
        # configuration this is derived from already reflects where the
        # Automater will actually be listening.
        service_address = http_input_configuration.get("service_address", "tcp://:8080")
        port = urlsplit(service_address).port or 8080
        path = (http_input_configuration.get("paths") or ["/telegraf"])[0]
        return f"http://iotops-automater-{automater_id}:{port}{path}"

    async def set_rule_enabled(self, automater_id: UUID, rule_id: UUID, enabled: bool) -> Automater:
        # Deliberately narrower than a full-rule replace: the only rule edit
        # exposed today is activate/deactivate, and a general-purpose "PUT
        # any field" endpoint would let `table` change without any of the
        # create_rule input-matching/validation logic running -- silently
        # deploying a rule that can never fire (see ROADMAP.md 2026-07-10,
        # "Multi-table Automaters"). Full rule-field editing, if it ships
        # later, needs that same validation built in from the start rather
        # than resurrecting this endpoint as-is.
        automater = await self._repository.get(automater_id)
        index = self._rule_index(automater, rule_id)
        automater.rules[index] = automater.rules[index].model_copy(update={"enabled": enabled})
        return await self._redeploy_or_stop(automater)

    async def delete_rule(self, automater_id: UUID, rule_id: UUID) -> Automater:
        automater = await self._repository.get(automater_id)
        index = self._rule_index(automater, rule_id)
        if len(automater.rules) == 1:
            raise InvalidOperationError(
                "Cannot delete an Automater's last rule -- delete the Automater itself instead"
            )
        del automater.rules[index]
        return await self._redeploy_or_stop(automater)

    def _rule_index(self, automater: Automater, rule_id: UUID) -> int:
        for i, rule in enumerate(automater.rules):
            if rule.id == rule_id:
                return i
        raise EntityNotFoundError("Rule", rule_id)

    async def _redeploy_or_stop(self, automater: Automater) -> Automater:
        automater = await self._repository.update(automater)
        if any(rule.enabled for rule in automater.rules):
            processors = [self._synthesize_rule_processor(automater)]
            toml_config = generate_toml(
                automater.inputs, processors, automater.outputs, self._registry
            )
            deployed = self._docker_manager.deploy(automater, toml_config)
            return await self._repository.update(deployed)
        if automater.docker is not None:
            stopped = self._docker_manager.stop(automater)
            return await self._repository.update(stopped)
        return automater

    async def get(self, automater_id: UUID) -> Automater:
        return await self._repository.get(automater_id)

    def _synthesize_rule_processor(self, automater: Automater) -> ProcessorPlugin:
        # The rule plugin instance is never persisted on Automater itself
        # (there's no `processors` field, only `rules`) -- it's built fresh
        # at deploy time from the rules the user actually authored. See
        # iotops-workspace/ROADMAP.md Phase B step 1.
        #
        # Each rule gets wrapped in a DeployedRule (adds automater_id/
        # project_id) here, not stored that way on Automater.rules itself --
        # a Rule's container is implicit via containment, duplicating it
        # onto every persisted Rule document would be redundant. The Go
        # plugin stamps these onto every matched metric (see rule.go's
        # annotate()) so the Celery event consumer can attribute an event
        # back to a project without a reverse DB lookup. See
        # iotops-workspace/ROADMAP.md's "Events sidebar" note.
        #
        # Defined before `list` below: a `list[Rule]` annotation on a method
        # that comes *after* a method literally named `list` in this same
        # class body would resolve `list` against the class namespace (where
        # it's already been rebound to that method), not the builtin.
        deployed_rules = [
            DeployedRule(
                **rule.model_dump(mode="json"),
                automater_id=automater.id,
                project_id=automater.project_id,
            )
            for rule in automater.rules
        ]
        configuration = self._registry.validate_configuration(
            _RULE_PLUGIN_TYPE,
            {"rules": [rule.model_dump(mode="json") for rule in deployed_rules]},
        )
        return ProcessorPlugin(plugin_type=_RULE_PLUGIN_TYPE, configuration=configuration)

    async def list(self) -> list[Automater]:
        return await self._repository.list()

    async def update(self, automater_id: UUID, payload: AutomaterInput) -> Automater:
        existing = await self._repository.get(automater_id)
        updated = existing.model_copy(
            update={
                "project_id": payload.project_id,
                "name": payload.name,
                "description": payload.description,
                "enabled": payload.enabled,
                "inputs": payload.inputs,
                "rules": payload.rules,
                "outputs": payload.outputs,
            }
        )
        self._validate_plugin_configurations(updated)
        return await self._repository.update(updated)

    async def delete(self, automater_id: UUID) -> None:
        automater = await self._repository.get(automater_id)
        await self._remove_http_forwarding(automater_id)
        self._docker_manager.remove(automater)
        await self._repository.delete(automater_id)

    async def _remove_http_forwarding(self, automater_id: UUID) -> None:
        # A Collector may have gained an http_forward output on this
        # Automater's behalf (see _ensure_http_forwarding) -- without this,
        # deleting the Automater would leave a permanent outputs.http block
        # retrying against a now-removed container. Not scoped to a single
        # Collector since an Automater's inputs (and thus the Collectors
        # they were derived from) aren't tracked back to their source once
        # copied -- cheap to scan given how rarely an Automater is deleted.
        for collector in await self._collector_service.list():
            remaining = [
                o for o in collector.outputs if o.automater_id != automater_id
            ]
            if len(remaining) != len(collector.outputs):
                collector.outputs = remaining
                await self._collector_service.redeploy_if_running(collector)

    async def deploy(self, automater_id: UUID) -> Automater:
        automater = await self._repository.get(automater_id)
        processors = [self._synthesize_rule_processor(automater)]
        toml_config = generate_toml(
            automater.inputs, processors, automater.outputs, self._registry
        )
        deployed = self._docker_manager.deploy(automater, toml_config)
        return await self._repository.update(deployed)

    async def stop(self, automater_id: UUID) -> Automater:
        automater = await self._repository.get(automater_id)
        stopped = self._docker_manager.stop(automater)
        return await self._repository.update(stopped)

    async def refresh_status(self, automater_id: UUID) -> Automater:
        automater = await self._repository.get(automater_id)
        refreshed = self._docker_manager.refresh_status(automater)
        return await self._repository.update(refreshed)

    def _validate_plugin_configurations(self, automater: Automater) -> None:
        for instance in (*automater.inputs, *automater.outputs):
            instance.configuration = self._registry.validate_configuration(
                instance.plugin_type, instance.configuration
            )
