from typing import Literal

from app.plugin.common import CommonOpts, advanced_field


class HttpOutputConfig(CommonOpts):
    """`outputs.http` -- forwards a copy of what a Collector received to
    an Automater's own `http_listener_v2` input, since a webhook push has
    no broker to fan out to multiple listeners on its own. See
    iotops-workspace/ROADMAP.md's "Automater fan-out strategy" note.
    """

    url: str
    method: Literal["POST", "PUT", "PATCH"] = advanced_field(default="POST")
    # "influx" (Telegraf's own default for outputs.http), not "json" --
    # Telegraf's *output* JSON serializer wraps metrics in its own
    # {"metrics": [{"fields": ..., "tags": ..., ...}]} envelope, which is
    # not the same shape parsers.json (the *input* parser
    # HttpListenerConfig uses) expects -- a flat object of field/tag
    # values, the shape a real external webhook sends. Line protocol is
    # the one format both a Telegraf output and a Telegraf input parse
    # losslessly, with no shape mismatch. AutomaterService scopes its
    # copied HttpListenerConfig's own data_format to "influx" to match
    # (see _automater_scoped_configuration) -- safe only because that
    # listener's sole sender is this forwarding output by design (real
    # external traffic always targets the Collector's URL, never the
    # Automater's directly).
    data_format: Literal["influx", "json"] = "influx"
    timeout: str = advanced_field(default="5s")
