"""Celery task: hand queued letters to Pingen."""

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
