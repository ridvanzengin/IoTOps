from celery import Celery

from app.config import settings

# Single Celery app shared by every task module in this backend --
# real-time rule matches (app/automater/tasks.py) and scheduled Query
# Rule evaluation (app/query_rule/tasks.py) both register onto this one
# instance rather than each running its own broker connection.
celery_app = Celery("automater", broker=settings.redis_uri)

# Imported here (not by importing each other) purely for their
# @celery_app.task/beat_schedule registration side effects -- both task
# modules need `celery_app`, and if automater/tasks.py imported
# query_rule/tasks.py directly (or vice versa) to trigger that
# registration, the two would form a circular import the moment either
# needs something the other defines. Routing through this dependency-free
# module breaks the cycle. `celery -A app.celery_app worker`/`beat`
# (docker-compose.yml) import this module, which pulls in both.
from app.automater import tasks as _automater_tasks  # noqa: E402,F401
from app.query_rule import tasks as _query_rule_tasks  # noqa: E402,F401
