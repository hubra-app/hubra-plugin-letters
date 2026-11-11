"""Celery tasks: hand queued letters to Pingen, forget old addresses."""

from __future__ import annotations

from hubra.core.modules import per_tenant_job
from hubra.core.tasks import celery_app

from . import services


@celery_app.task(name="hubra_letters.tasks.post")
@per_tenant_job("letters")
def post() -> dict:
    from hubra.core.extensions import db

    done = services.post_queued()
    db.session.commit()
    return done


@celery_app.task(name="hubra_letters.tasks.forget")
@per_tenant_job("letters")
def forget() -> dict:
    from hubra.core.extensions import db

    n = services.forget_addresses()
    orphans = services.purge_orphans()
    db.session.commit()
    return {"forgotten": n, "orphans": orphans}
