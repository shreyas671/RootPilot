from pathlib import Path

import pytest

from apps.metadata_service.services.evaluation_loader import (
    load_evaluation_dataset,
)


def test_load_default_evaluation_dataset() -> None:
    dataset = load_evaluation_dataset()

    assert [
        case.case_id
        for case in dataset.retrieval_cases
    ] == [
        "RET-DB-001",
        "RET-KAFKA-001",
    ]
    assert [
        case.case_id
        for case in dataset.assessment_cases
    ] == [
        "RCA-DB-001",
        "RCA-KAFKA-001",
    ]


def test_load_evaluation_dataset_rejects_invalid_json(
    tmp_path: Path,
) -> None:
    dataset_path = tmp_path / "invalid.json"
    dataset_path.write_text("{invalid", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="Evaluation dataset contains invalid JSON",
    ):
        load_evaluation_dataset(dataset_path)
