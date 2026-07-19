from apscheduler.schedulers.blocking import BlockingScheduler

from scheduler import main as scheduler_main


def test_register_jobs_registers_heartbeat_and_nightly_import():
    scheduler = BlockingScheduler(timezone="UTC")

    scheduler_main._register_jobs(scheduler)

    assert scheduler.get_job("heartbeat") is not None
    nightly_import = scheduler.get_job("nightly_import")
    assert nightly_import is not None
    settings = scheduler_main.get_settings()
    trigger_fields = {field.name: str(field) for field in nightly_import.trigger.fields}
    assert trigger_fields["hour"] == str(settings.nightly_import_cron_hour)
    assert trigger_fields["minute"] == str(settings.nightly_import_cron_minute)


def test_run_nightly_import_swallows_exceptions_instead_of_crashing_the_scheduler(monkeypatch):
    async def _raising_async() -> None:
        raise RuntimeError("simulated pipeline crash")

    monkeypatch.setattr(scheduler_main, "_run_nightly_import_async", _raising_async)

    scheduler_main._run_nightly_import()  # must not raise


async def test_run_nightly_import_async_wires_the_service_and_commits(monkeypatch):
    calls: list[str] = []

    class _FakeService:
        def __init__(self, **kwargs) -> None:
            calls.append("constructed")

        async def run(self):
            calls.append("run")

    class _FakeSession:
        async def commit(self) -> None:
            calls.append("commit")

        async def __aenter__(self) -> "_FakeSession":
            return self

        async def __aexit__(self, *exc_info) -> None:
            return None

    def _fake_session_factory():
        return _FakeSession()

    monkeypatch.setattr(scheduler_main, "create_session_factory", lambda: _fake_session_factory)
    monkeypatch.setattr(scheduler_main, "SourceSystemImportService", _FakeService)

    await scheduler_main._run_nightly_import_async()

    assert calls == ["constructed", "run", "commit"]
