"""Celery tasks: post through Pingen, build the print PDF, forget old data."""

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
    pdfs = services.drop_old_pdfs()
    db.session.commit()
    return {"forgotten": n, "orphans": orphans, "pdfs": pdfs}


@celery_app.task(name="hubra_letters.tasks.build_pdf")
def build_pdf(letter_id: int) -> str:
    """Queued from a request, so it runs in that club (core sets the schema)."""
    from hubra.core.extensions import db

    status = services.build_pdf(int(letter_id))
    db.session.commit()
    return status
