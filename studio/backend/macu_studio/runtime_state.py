"""Trivial in-process tracking of which slug owns which job_id.

Lets the SSE proxy tag events back to the originating episode when needed.
Lost on process restart — that's fine.
"""
_JOB_SLUG: dict[str, str] = {}


def remember_job(job_id: str, slug: str) -> None:
    _JOB_SLUG[job_id] = slug


def slug_for_job(job_id: str) -> str | None:
    return _JOB_SLUG.get(job_id)
