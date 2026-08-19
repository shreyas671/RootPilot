from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from apps.metadata_service.database import get_db_session
from apps.metadata_service.main import app
from apps.metadata_service.models.investigation_report import (
    InvestigationReport,
    InvestigationReportStatus,
)
from apps.metadata_service.models.investigation_review_event import (
    InvestigationReviewEvent,
)


class FakeSession:
    def __init__(self) -> None:
        self.report_to_return: (
            InvestigationReport | None
        ) = None
        self.raise_on_get = False
        self.added_review_event: (
            InvestigationReviewEvent | None
        ) = None
        self.review_events: list[
            InvestigationReviewEvent
        ] = []
        self.committed = False
        self.rolled_back = False
        self.used_row_lock = False

    def add(
        self,
        event: InvestigationReviewEvent,
    ) -> None:
        assert isinstance(
            event,
            InvestigationReviewEvent,
        )
        self.added_review_event = event

    async def get(
        self,
        model: type[InvestigationReport],
        report_id: UUID,
        *,
        with_for_update: bool = False,
    ) -> InvestigationReport | None:
        assert model is InvestigationReport

        self.used_row_lock = with_for_update

        if self.raise_on_get:
            raise SQLAlchemyError(
                "Database unavailable"
            )

        if self.report_to_return is None:
            return None

        if self.report_to_return.id != report_id:
            return None

        return self.report_to_return

    async def flush(self) -> None:
        now = datetime.now(UTC)

        if self.report_to_return is not None:
            self.report_to_return.updated_at = now

        if self.added_review_event is not None:
            self.added_review_event.id = uuid4()
            self.added_review_event.created_at = now
            self.review_events.append(
                self.added_review_event
            )

    async def execute(self, statement: object) -> object:
        class FakeScalarResult:
            def __init__(
                self,
                events: list[InvestigationReviewEvent],
            ) -> None:
                self.events = events

            def scalars(self) -> "FakeScalarResult":
                return self

            def all(
                self,
            ) -> list[InvestigationReviewEvent]:
                return self.events

        return FakeScalarResult(self.review_events)

    async def refresh(
        self,
        report: InvestigationReport,
    ) -> None:
        assert report is self.report_to_return

    async def commit(self) -> None:
        self.committed = True
        self.rolled_back = False

    async def rollback(self) -> None:
        self.committed = False
        self.rolled_back = True


@pytest.fixture
def client_and_session() -> Iterator[
    tuple[TestClient, FakeSession]
]:
    fake_session = FakeSession()

    async def override_get_db_session() -> (
        AsyncIterator[FakeSession]
    ):
        yield fake_session

    app.dependency_overrides[
        get_db_session
    ] = override_get_db_session

    try:
        with TestClient(app) as client:
            yield client, fake_session
    finally:
        app.dependency_overrides.pop(
            get_db_session,
            None,
        )


def make_report(
    report_status: InvestigationReportStatus,
) -> InvestigationReport:
    now = datetime.now(UTC)

    return InvestigationReport(
        id=uuid4(),
        job_id=uuid4(),
        incident_id="INC-DB-001",
        root_cause="Database connection exhaustion",
        supporting_evidence=[
            "Connection usage reached its maximum.",
        ],
        recommended_actions=[
            "Reduce idle database connections.",
        ],
        verification_steps=[
            "Verify connection usage returns to normal.",
        ],
        confidence=0.92,
        citation_ids=[
            "RB-DB-001#connection-exhaustion",
        ],
        status=report_status,
        reviewed_by=None,
        reviewer_feedback=None,
        reviewed_at=None,
        created_at=now,
        updated_at=now,
    )


def test_get_report_returns_existing_report(
    client_and_session: tuple[
        TestClient,
        FakeSession,
    ],
) -> None:
    client, session = client_and_session
    report = make_report(
        InvestigationReportStatus.PENDING_REVIEW
    )
    session.report_to_return = report

    response = client.get(
        f"/investigation-reports/{report.id}"
    )

    assert response.status_code == 200

    body = response.json()

    assert body["id"] == str(report.id)
    assert body["job_id"] == str(report.job_id)
    assert body["incident_id"] == "INC-DB-001"
    assert body["status"] == "pending_review"
    assert body["reviewed_by"] is None


def test_get_report_returns_404_when_missing(
    client_and_session: tuple[
        TestClient,
        FakeSession,
    ],
) -> None:
    client, session = client_and_session

    response = client.get(
        f"/investigation-reports/{uuid4()}"
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Investigation report not found"
    }
    assert session.rolled_back is True


def test_get_report_rejects_invalid_uuid(
    client_and_session: tuple[
        TestClient,
        FakeSession,
    ],
) -> None:
    client, _ = client_and_session

    response = client.get(
        "/investigation-reports/not-a-uuid"
    )

    assert response.status_code == 422


def test_review_approves_pending_report(
    client_and_session: tuple[
        TestClient,
        FakeSession,
    ],
) -> None:
    client, session = client_and_session
    report = make_report(
        InvestigationReportStatus.PENDING_REVIEW
    )
    session.report_to_return = report

    response = client.patch(
        f"/investigation-reports/{report.id}/review",
        json={
            "status": "approved",
            "reviewed_by": "operator@example.com",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["status"] == "approved"
    assert body["reviewed_by"] == (
        "operator@example.com"
    )
    assert body["reviewed_at"] is not None
    assert session.used_row_lock is True
    assert session.committed is True
    assert session.added_review_event is not None


def test_get_review_events(
    client_and_session: tuple[
        TestClient,
        FakeSession,
    ],
) -> None:
    client, session = client_and_session
    report = make_report(
        InvestigationReportStatus.APPROVED
    )
    session.report_to_return = report
    event = InvestigationReviewEvent(
        id=uuid4(),
        report_id=report.id,
        previous_status=(
            InvestigationReportStatus.PENDING_REVIEW
        ),
        new_status=InvestigationReportStatus.APPROVED,
        reviewed_by="operator@example.com",
        reviewer_feedback=None,
        created_at=datetime.now(UTC),
    )
    session.review_events = [event]

    response = client.get(
        f"/investigation-reports/{report.id}/review-events"
    )

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": str(event.id),
            "report_id": str(report.id),
            "previous_status": "pending_review",
            "new_status": "approved",
            "reviewed_by": "operator@example.com",
            "reviewer_feedback": None,
            "created_at": event.created_at.isoformat().replace(
                "+00:00",
                "Z",
            ),
        }
    ]


def test_get_review_events_returns_404_when_missing(
    client_and_session: tuple[
        TestClient,
        FakeSession,
    ],
) -> None:
    client, session = client_and_session

    response = client.get(
        f"/investigation-reports/{uuid4()}/review-events"
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Investigation report not found"
    }
    assert session.rolled_back is True


def test_get_review_events_handles_database_error(
    client_and_session: tuple[
        TestClient,
        FakeSession,
    ],
) -> None:
    client, session = client_and_session
    session.raise_on_get = True

    response = client.get(
        f"/investigation-reports/{uuid4()}/review-events"
    )

    assert response.status_code == 500
    assert response.json() == {
        "detail": "Unable to retrieve review events"
    }
    assert session.rolled_back is True


def test_review_rejects_pending_report(
    client_and_session: tuple[
        TestClient,
        FakeSession,
    ],
) -> None:
    client, session = client_and_session
    report = make_report(
        InvestigationReportStatus.PENDING_REVIEW
    )
    session.report_to_return = report

    response = client.patch(
        f"/investigation-reports/{report.id}/review",
        json={
            "status": "rejected",
            "reviewed_by": "operator@example.com",
            "reviewer_feedback": (
                "The evidence is insufficient."
            ),
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert response.json()["reviewer_feedback"] == (
        "The evidence is insufficient."
    )
    assert session.committed is True


def test_review_rejects_second_decision(
    client_and_session: tuple[
        TestClient,
        FakeSession,
    ],
) -> None:
    client, session = client_and_session
    report = make_report(
        InvestigationReportStatus.APPROVED
    )
    session.report_to_return = report

    response = client.patch(
        f"/investigation-reports/{report.id}/review",
        json={
            "status": "rejected",
            "reviewed_by": "operator@example.com",
            "reviewer_feedback": (
                "Changed my decision."
            ),
        },
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": (
            f"Investigation report {report.id} "
            "has already been approved"
        )
    }
    assert session.rolled_back is True


def test_rejection_requires_feedback(
    client_and_session: tuple[
        TestClient,
        FakeSession,
    ],
) -> None:
    client, session = client_and_session
    report = make_report(
        InvestigationReportStatus.PENDING_REVIEW
    )
    session.report_to_return = report

    response = client.patch(
        f"/investigation-reports/{report.id}/review",
        json={
            "status": "rejected",
            "reviewed_by": "operator@example.com",
        },
    )

    assert response.status_code == 422
    assert report.status is (
        InvestigationReportStatus.PENDING_REVIEW
    )
    assert session.committed is False


def test_get_report_handles_database_error(
    client_and_session: tuple[
        TestClient,
        FakeSession,
    ],
) -> None:
    client, session = client_and_session
    session.raise_on_get = True

    response = client.get(
        f"/investigation-reports/{uuid4()}"
    )

    assert response.status_code == 500
    assert response.json() == {
        "detail": (
            "Unable to retrieve investigation report"
        )
    }
    assert session.rolled_back is True
