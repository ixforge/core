"""Every periodic task accepts the timestamp procrastinate passes when it defers it"""

import inspect

import pytest

import ixforge.tasks.maintenance  # noqa: F401  registers the periodic tasks
from ixforge.tasks import app

PERIODIC_TASKS = sorted(app.periodic_registry.periodic_tasks.values(), key=lambda p: p.task.name)


def test_the_maintenance_tasks_are_periodic():
    names = {periodic.task.name for periodic in PERIODIC_TASKS}

    assert {"cleanup_old_prefix_events", "cleanup_old_events", "cleanup_config_versions"} <= names


@pytest.mark.parametrize("periodic", PERIODIC_TASKS, ids=lambda p: p.task.name)
def test_a_periodic_task_accepts_the_defer_timestamp(periodic):
    # procrastinate defers each periodic job with task_kwargs={"timestamp": ...}
    inspect.signature(periodic.task.func).bind(timestamp=1_761_300_000)
