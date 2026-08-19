import json
from pathlib import Path

from apps.metadata_service.schemas.evaluation import (
    EvaluationDataset,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_EVALUATION_DATASET = (
    PROJECT_ROOT
    / "data"
    / "evaluations"
    / "mvp_cases.json"
)


def load_evaluation_dataset(
    path: Path = DEFAULT_EVALUATION_DATASET,
) -> EvaluationDataset:
    path = Path(path)

    try:
        raw_dataset = json.loads(
            path.read_text(encoding="utf-8")
        )
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Evaluation dataset contains invalid JSON: "
            f"{path}"
        ) from exc

    return EvaluationDataset.model_validate(
        raw_dataset
    )
