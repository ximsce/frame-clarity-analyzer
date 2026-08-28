"""Batch orchestration over manifests, analyzers, and progress storage."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .analyzers import AnalyzerProtocol, validate_score
from .errors import AnalyzerError, ConfigurationError
from .models import AnalyzerResult, FrameManifest, FrameManifestItem, FrameOutcome, RunResult
from .progress import ProgressMetadata, ProgressStore


def _sanitize_error(error: Exception, secrets: Sequence[str] = ()) -> str:
    message = str(error).strip() or error.__class__.__name__
    for secret in secrets:
        if secret:
            message = message.replace(secret, "[redacted]")
    return message[:1000]


def _normalize_analyzer_result(value: object) -> AnalyzerResult:
    if isinstance(value, AnalyzerResult):
        score = value.score
        reasoning = value.reasoning
    elif isinstance(value, tuple) and len(value) == 2:
        score, reasoning = value
    else:
        raise AnalyzerError("Analyzer returned an unsupported result")
    if not isinstance(reasoning, str):
        raise AnalyzerError("Analyzer reasoning must be a string")
    return AnalyzerResult(score=validate_score(score), reasoning=reasoning)


def _analyze_item(
    item: FrameManifestItem,
    analyzer: AnalyzerProtocol,
    previous: Optional[FrameOutcome],
    secrets: Sequence[str],
) -> FrameOutcome:
    attempts = (previous.attempts if previous else 0) + 1
    try:
        result = _normalize_analyzer_result(analyzer.analyze(item.path))
        return FrameOutcome.success(
            filename=item.filename,
            frame_index=item.frame_index,
            score=result.score,
            reasoning=result.reasoning,
            attempts=attempts,
            provenance=item.provenance,
        )
    except Exception as exc:
        return FrameOutcome.failed(
            filename=item.filename,
            frame_index=item.frame_index,
            error=_sanitize_error(exc, secrets),
            attempts=attempts,
            provenance=item.provenance,
        )


def _run_batch(
    items: Sequence[FrameManifestItem],
    analyzer: AnalyzerProtocol,
    previous: Dict[str, FrameOutcome],
    max_workers: int,
    secrets: Sequence[str],
) -> List[FrameOutcome]:
    if max_workers == 1:
        return [_analyze_item(item, analyzer, previous.get(item.filename), secrets) for item in items]
    results: Dict[str, FrameOutcome] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_analyze_item, item, analyzer, previous.get(item.filename), secrets): item
            for item in items
        }
        for future in as_completed(futures):
            item = futures[future]
            results[item.filename] = future.result()
    return [results[item.filename] for item in items]


def run_analysis(
    manifest: FrameManifest,
    analyzer: AnalyzerProtocol,
    *,
    analyzer_name: str,
    model: str,
    progress_store: Optional[ProgressStore] = None,
    resume: bool = True,
    batch_size: int = 10,
    max_workers: int = 1,
    secrets: Sequence[str] = (),
    top_n: int = 50,
) -> RunResult:
    """Analyze all pending frames and checkpoint after each batch."""

    if batch_size <= 0:
        raise ConfigurationError("batch_size must be positive")
    if max_workers <= 0:
        raise ConfigurationError("max_workers must be positive")
    if top_n <= 0:
        raise ConfigurationError("top_n must be positive")

    metadata = ProgressMetadata(
        input_id=manifest.input_id,
        analyzer=analyzer_name,
        model=model,
    )
    previous: Dict[str, FrameOutcome] = {}
    if resume and progress_store is not None:
        state = progress_store.load(manifest, metadata)
        if state is not None:
            previous = {outcome.filename: outcome for outcome in state.outcomes}
            if state.migrated_legacy:
                progress_store.save(metadata, previous.values())

    outcomes: Dict[str, FrameOutcome] = dict(previous)
    pending = [
        item
        for item in manifest.items
        if item.filename not in previous
        or previous[item.filename].status == "failed"
    ]
    for start in range(0, len(pending), batch_size):
        batch = pending[start : start + batch_size]
        batch_outcomes = _run_batch(batch, analyzer, previous, max_workers, secrets)
        for outcome in batch_outcomes:
            outcomes[outcome.filename] = outcome
        previous.update({outcome.filename: outcome for outcome in batch_outcomes})
        if progress_store is not None:
            progress_store.save(metadata, outcomes.values())

    ordered = [outcomes[item.filename] for item in manifest.items if item.filename in outcomes]
    if progress_store is not None and not pending:
        progress_store.save(metadata, ordered)
    return RunResult(outcomes=ordered, top_n=top_n)
