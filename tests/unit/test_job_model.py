from sqlalchemy import CheckConstraint, Enum

from apps.metadata_service.models import Base, Job, JobStatus


def test_job_table_metadata() -> None:
    table = Job.__table__

    assert table.name == "jobs"
    assert Base.metadata.tables["jobs"] is table

    assert set(table.columns.keys()) == {
        "id",
        "input_path",
        "incident_id",
        "status",
        "error_message",
        "attempt_count",
        "max_attempts",
        "claimed_by",
        "lease_expires_at",
        "scheduled_at",
        "started_at",
        "completed_at",
        "created_at",
        "updated_at",
    }

    assert table.c.id.primary_key
    assert not table.c.input_path.nullable
    assert table.c.error_message.nullable
    assert table.c.incident_id.nullable
    assert table.c.claimed_by.nullable
    assert table.c.lease_expires_at.nullable
    assert not table.c.attempt_count.nullable
    assert not table.c.max_attempts.nullable
    assert not table.c.scheduled_at.nullable
    assert table.c.started_at.nullable
    assert table.c.completed_at.nullable

    status_type = table.c.status.type
    assert isinstance(status_type, Enum)
    assert set(status_type.enums) == {
        "pending",
        "processing",
        "completed",
        "failed",
    }

    assert table.c.status.default is not None
    assert table.c.status.default.arg == JobStatus.PENDING
    assert table.c.status.server_default is not None

    constraint_names = {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert constraint_names == {
        "ck_jobs_attempt_count_nonnegative",
        "ck_jobs_max_attempts_positive",
        "ck_jobs_attempt_count_within_limit",
    }
