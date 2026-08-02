from sqlalchemy import Enum

from apps.metadata_service.models import Base, Job, JobStatus


def test_job_table_metadata() -> None:
    table = Job.__table__

    assert table.name == "jobs"
    assert Base.metadata.tables["jobs"] is table

    assert set(table.columns.keys()) == {
        "id",
        "input_path",
        "status",
        "error_message",
        "started_at",
        "completed_at",
        "created_at",
        "updated_at",
    }

    assert table.c.id.primary_key
    assert not table.c.input_path.nullable
    assert table.c.error_message.nullable
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