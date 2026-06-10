"""Tests para el comando worker del CLI."""

from ixforge import cli


class FakeSchemaManager:
    """Doble del schema manager que registra si la app estaba abierta"""

    def __init__(self, app: "FakeApp") -> None:
        self._app = app
        self.applied_while_open = False

    async def apply_schema_async(self) -> None:
        self.applied_while_open = self._app.opened


class FakeApp:
    """Doble de la app de procrastinate que registra el ciclo open/run"""

    def __init__(self) -> None:
        self.opened = False
        self.worker_ran_while_open = False
        self.received_kwargs: dict[str, object] | None = None
        self.schema_manager = FakeSchemaManager(self)

    def open_async(self):
        fake = self

        class _Ctx:
            async def __aenter__(self):
                fake.opened = True
                return fake

            async def __aexit__(self, *exc: object) -> bool:
                fake.opened = False
                return False

        return _Ctx()

    async def run_worker_async(self, **kwargs: object) -> None:
        self.worker_ran_while_open = self.opened
        self.received_kwargs = kwargs


def test_run_worker_abre_la_app_antes_de_correr(monkeypatch):
    # procrastinate 3.x lanza AppNotOpen si el worker corre sin abrir la app
    fake = FakeApp()
    monkeypatch.setattr("ixforge.tasks.app", fake)

    cli._run_worker()

    assert fake.worker_ran_while_open
    assert fake.received_kwargs == {}


def test_run_worker_pasa_las_queues(monkeypatch):
    fake = FakeApp()
    monkeypatch.setattr("ixforge.tasks.app", fake)

    cli._run_worker(queues=["config", "maintenance"])

    assert fake.worker_ran_while_open
    assert fake.received_kwargs == {"queues": ["config", "maintenance"]}


def test_run_server_pasa_reload_segun_debug(monkeypatch):
    captured: dict[str, object] = {}

    class FakeSettings:
        debug = True

    def fake_run(app: str, **kwargs: object) -> None:
        captured["app"] = app
        captured.update(kwargs)

    monkeypatch.setattr("uvicorn.run", fake_run)
    monkeypatch.setattr("ixforge.config.get_settings", lambda: FakeSettings())

    cli._run_server()

    assert captured["app"] == "ixforge.main:app"
    assert captured["reload"] is True


def test_apply_procrastinate_schema_abre_la_app(monkeypatch):
    fake = FakeApp()
    monkeypatch.setattr("ixforge.tasks.app", fake)

    cli._apply_procrastinate_schema()

    assert fake.schema_manager.applied_while_open
