"""Scheduler process entrypoint (inbound adapter, AD-5).

A separate container from ``api/`` so a web-tier crash or redeploy never
silently drops a scheduled run. Runs its own in-process APScheduler
(AD-2) — no Redis/Celery in Phase 1.
"""

import logging
import pathlib

from apscheduler.schedulers.blocking import BlockingScheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

HEARTBEAT_PATH = pathlib.Path("/tmp/scheduler.heartbeat")


def _heartbeat() -> None:
    HEARTBEAT_PATH.touch()


def main() -> None:
    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(_heartbeat, "interval", seconds=30, id="heartbeat")

    logger.info("scheduler starting")
    _heartbeat()

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    main()
