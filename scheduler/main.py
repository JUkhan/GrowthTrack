"""Scheduler process entrypoint (inbound adapter, AD-5).

A separate container from ``api/`` so a web-tier crash or redeploy never
silently drops a scheduled run. Runs its own in-process APScheduler
(AD-2) — no Redis/Celery in Phase 1.
"""

import logging
import pathlib
import signal

from apscheduler.schedulers.blocking import BlockingScheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

HEARTBEAT_PATH = pathlib.Path("/tmp/scheduler.heartbeat")


def _heartbeat() -> None:
    HEARTBEAT_PATH.touch()


def main() -> None:
    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(_heartbeat, "interval", seconds=30, id="heartbeat")

    def _handle_sigterm(signum: int, frame: object) -> None:
        # `docker stop` / a redeploy sends SIGTERM to PID 1. Python does not
        # turn that into KeyboardInterrupt/SystemExit by default, so without
        # this handler the process dies immediately mid-job — exactly what
        # running the scheduler as its own container exists to prevent
        # (AD-5). Shut down gracefully instead.
        logger.info("SIGTERM received, shutting down scheduler gracefully")
        scheduler.shutdown(wait=True)

    signal.signal(signal.SIGTERM, _handle_sigterm)

    logger.info("scheduler starting")
    _heartbeat()

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    main()
