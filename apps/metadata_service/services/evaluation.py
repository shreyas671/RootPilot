from collections.abc import Mapping, Sequence

from apps.metadata_service.schemas.assessment import (
    IncidentAssessment,
)
from apps.metadata_service.schemas.evaluation import (
    AssessmentEvaluationCase,
    AssessmentEvaluationResult,
    AssessmentEvaluationSummary,
    EvaluationDataset,
    PipelineEvaluationSummary,
    RetrievalEvaluationCase,
    RetrievalEvaluationResult,
    RetrievalEvaluationSummary,
)
from apps.metadata_service.schemas.incident import (
    IncidentEvidence,
)
from apps.metadata_service.schemas.retrieval import (
    RetrievedRunbookSection,
)
from apps.metadata_service.services.analyst import (
    IncidentAnalyst,
)
from apps.metadata_service.services.investigation_graph import (
    build_investigation_graph,
)
from apps.metadata_service.services.retriever import (
    RunbookRetriever,
)


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def _get_incident(
    incidents: Mapping[str, IncidentEvidence],
    incident_id: str,
) -> IncidentEvidence:
    try:
        return incidents[incident_id]
    except KeyError as exc:
        raise ValueError(
            "Evaluation references an unknown incident: "
            f"{incident_id}"
        ) from exc


def _term_coverage(
    required_terms: Sequence[str],
    text: str,
) -> float:
    normalized_text = text.casefold()
    matches = sum(
        term.casefold() in normalized_text
        for term in required_terms
    )

    return matches / len(required_terms)


async def evaluate_retrieval_case(
    case: RetrievalEvaluationCase,
    incident: IncidentEvidence,
    retriever: RunbookRetriever,
) -> RetrievalEvaluationResult:
    results = await retriever.retrieve(
        incident=incident,
        limit=case.retrieval_limit,
    )
    relevant_results = [
        result
        for result in results
        if result.score >= case.minimum_relevance_score
    ]
    retrieved_ids = [
        result.section.citation_id
        for result in relevant_results
    ]
    expected_ids = set(case.expected_citation_ids)
    retrieved_expected_ids = (
        expected_ids.intersection(retrieved_ids)
    )
    recall_at_k = (
        len(retrieved_expected_ids) / len(expected_ids)
    )
    reciprocal_rank = 0.0

    for rank, citation_id in enumerate(
        retrieved_ids,
        start=1,
    ):
        if citation_id in expected_ids:
            reciprocal_rank = 1.0 / rank
            break

    return RetrievalEvaluationResult(
        case_id=case.case_id,
        incident_id=case.incident_id,
        expected_citation_ids=(
            case.expected_citation_ids
        ),
        retrieved_citation_ids=retrieved_ids,
        recall_at_k=recall_at_k,
        reciprocal_rank=reciprocal_rank,
        passed=recall_at_k == 1.0,
    )


async def evaluate_retrieval_cases(
    cases: Sequence[RetrievalEvaluationCase],
    incidents: Mapping[str, IncidentEvidence],
    retriever: RunbookRetriever,
) -> RetrievalEvaluationSummary:
    results = []

    for case in cases:
        incident = _get_incident(
            incidents,
            case.incident_id,
        )
        results.append(
            await evaluate_retrieval_case(
                case=case,
                incident=incident,
                retriever=retriever,
            )
        )

    return RetrievalEvaluationSummary(
        cases=results,
        mean_recall_at_k=_mean(
            [result.recall_at_k for result in results]
        ),
        mean_reciprocal_rank=_mean(
            [
                result.reciprocal_rank
                for result in results
            ]
        ),
        pass_rate=_mean(
            [float(result.passed) for result in results]
        ),
    )


def evaluate_assessment_case(
    case: AssessmentEvaluationCase,
    assessment: IncidentAssessment,
    retrieved_sections: Sequence[
        RetrievedRunbookSection
    ],
) -> AssessmentEvaluationResult:
    retrieved_ids = {
        result.section.citation_id
        for result in retrieved_sections
    }
    assessment_ids = set(assessment.citation_ids)
    expected_ids = set(case.expected_citation_ids)

    incident_id_matches = (
        assessment.incident_id == case.incident_id
    )
    citations_grounded = assessment_ids.issubset(
        retrieved_ids
    )
    expected_citation_recall = (
        len(expected_ids.intersection(assessment_ids))
        / len(expected_ids)
    )
    root_cause_term_coverage = _term_coverage(
        case.required_root_cause_terms,
        assessment.root_cause,
    )
    action_term_coverage = _term_coverage(
        case.required_action_terms,
        "\n".join(assessment.recommended_actions),
    )
    confidence_acceptable = (
        assessment.confidence >= case.minimum_confidence
    )
    passed = all(
        (
            incident_id_matches,
            citations_grounded,
            expected_citation_recall == 1.0,
            root_cause_term_coverage == 1.0,
            action_term_coverage == 1.0,
            confidence_acceptable,
        )
    )

    return AssessmentEvaluationResult(
        case_id=case.case_id,
        incident_id=case.incident_id,
        incident_id_matches=incident_id_matches,
        citations_grounded=citations_grounded,
        expected_citation_recall=(
            expected_citation_recall
        ),
        root_cause_term_coverage=(
            root_cause_term_coverage
        ),
        action_term_coverage=action_term_coverage,
        confidence_acceptable=confidence_acceptable,
        passed=passed,
    )


def summarize_assessment_results(
    results: Sequence[AssessmentEvaluationResult],
) -> AssessmentEvaluationSummary:
    return AssessmentEvaluationSummary(
        cases=list(results),
        mean_expected_citation_recall=_mean(
            [
                result.expected_citation_recall
                for result in results
            ]
        ),
        mean_root_cause_term_coverage=_mean(
            [
                result.root_cause_term_coverage
                for result in results
            ]
        ),
        mean_action_term_coverage=_mean(
            [
                result.action_term_coverage
                for result in results
            ]
        ),
        pass_rate=_mean(
            [float(result.passed) for result in results]
        ),
    )


async def run_pipeline_evaluation(
    dataset: EvaluationDataset,
    incidents: Mapping[str, IncidentEvidence],
    retriever: RunbookRetriever,
    analyst: IncidentAnalyst,
) -> PipelineEvaluationSummary:
    retrieval_summary = await evaluate_retrieval_cases(
        cases=dataset.retrieval_cases,
        incidents=incidents,
        retriever=retriever,
    )
    assessment_results = []

    for case in dataset.assessment_cases:
        incident = _get_incident(
            incidents,
            case.incident_id,
        )
        graph = build_investigation_graph(
            retriever=retriever,
            analyst=analyst,
            retrieval_limit=case.retrieval_limit,
            minimum_relevance_score=(
                case.minimum_relevance_score
            ),
        )
        try:
            result = await graph.ainvoke(
                {
                    "incident": incident,
                }
            )
        except ValueError as exc:
            assessment_results.append(
                AssessmentEvaluationResult(
                    case_id=case.case_id,
                    incident_id=case.incident_id,
                    incident_id_matches=False,
                    citations_grounded=False,
                    expected_citation_recall=0.0,
                    root_cause_term_coverage=0.0,
                    action_term_coverage=0.0,
                    confidence_acceptable=False,
                    evaluation_error=(
                        f"{exc.__class__.__name__}: {exc}"
                    ),
                    passed=False,
                )
            )
            continue

        assessment_results.append(
            evaluate_assessment_case(
                case=case,
                assessment=result["assessment"],
                retrieved_sections=(
                    result["retrieved_sections"]
                ),
            )
        )

    return PipelineEvaluationSummary(
        retrieval=retrieval_summary,
        assessment=summarize_assessment_results(
            assessment_results
        ),
    )
