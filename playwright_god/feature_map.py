"""Feature-aware repository understanding built from indexed source files."""

from __future__ import annotations

from dataclasses import dataclass, field
import itertools
from typing import Iterable, Sequence

from .chunker import Chunk
from .crawler import FileInfo


@dataclass(frozen=True)
class ArtifactEvidence:
    """Repository proof that supports a feature or test opportunity."""

    artifact_id: str
    file_path: str
    language: str
    start_line: int
    end_line: int
    signal_type: str
    summary: str

    def to_dict(self) -> dict[str, object]:
        return {
            "artifact_id": self.artifact_id,
            "file_path": self.file_path,
            "language": self.language,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "signal_type": self.signal_type,
            "summary": self.summary,
        }


@dataclass
class FeatureArea:
    """A user-visible capability inferred from repository evidence."""

    feature_id: str
    name: str
    summary: str
    confidence: float
    artifacts: list[ArtifactEvidence] = field(default_factory=list)
    entry_points: list[str] = field(default_factory=list)
    workflows: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "feature_id": self.feature_id,
            "name": self.name,
            "summary": self.summary,
            "confidence": round(self.confidence, 3),
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "entry_points": self.entry_points,
            "workflows": self.workflows,
        }


@dataclass(frozen=True)
class FeatureCorrelation:
    """A relationship between two inferred features."""

    correlation_id: str
    source_feature_id: str
    target_feature_id: str
    relationship_type: str
    confidence: float
    evidence_ids: list[str]
    summary: str

    def to_dict(self) -> dict[str, object]:
        return {
            "correlation_id": self.correlation_id,
            "source_feature_id": self.source_feature_id,
            "target_feature_id": self.target_feature_id,
            "relationship_type": self.relationship_type,
            "confidence": round(self.confidence, 3),
            "evidence_ids": self.evidence_ids,
            "summary": self.summary,
        }


@dataclass(frozen=True)
class TestOpportunity:
    """A candidate Playwright scenario inferred from repository understanding."""

    opportunity_id: str
    feature_id: str
    title: str
    priority: str
    confidence: float
    evidence_ids: list[str]
    preconditions: list[str]
    assertions: list[str]
    uncertainty_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "opportunity_id": self.opportunity_id,
            "feature_id": self.feature_id,
            "title": self.title,
            "priority": self.priority,
            "confidence": round(self.confidence, 3),
            "evidence_ids": self.evidence_ids,
            "preconditions": self.preconditions,
            "assertions": self.assertions,
            "uncertainty_notes": self.uncertainty_notes,
        }


@dataclass
class RepositoryFeatureMap:
    """Top-level repository understanding artifact."""

    generated_at: str
    source_root: str
    total_files: int
    total_chunks: int
    languages: dict[str, int]
    features: list[FeatureArea] = field(default_factory=list)
    correlations: list[FeatureCorrelation] = field(default_factory=list)
    test_opportunities: list[TestOpportunity] = field(default_factory=list)
    file_index: list[dict[str, object]] = field(default_factory=list)
    schema_version: str = "2.1"

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "source_root": self.source_root,
            "total_files": self.total_files,
            "total_chunks": self.total_chunks,
            "languages": self.languages,
            "features": [feature.to_dict() for feature in self.features],
            "correlations": [item.to_dict() for item in self.correlations],
            "test_opportunities": [item.to_dict() for item in self.test_opportunities],
            "file_index": self.file_index,
        }


@dataclass(frozen=True)
class _FeatureDefinition:
    feature_id: str
    name: str
    keywords: tuple[str, ...]
    summary: str
    workflows: tuple[str, ...]
    opportunity_titles: tuple[str, ...]


_FEATURE_DEFINITIONS: tuple[_FeatureDefinition, ...] = (
    _FeatureDefinition(
        "authentication",
        "Authentication",
        ("login", "register", "auth", "password", "email", "token", "signin", "signup"),
        "Identity, session, and sign-in flows that gate access to application features.",
        ("User signs in with valid credentials", "User sees a friendly error for invalid credentials"),
        ("User can sign in with valid credentials", "Invalid credentials show an actionable error"),
    ),
    _FeatureDefinition(
        "todo-management",
        "Todo Management",
        ("todo", "todos", "task", "complete", "delete", "checkbox"),
        "Create, update, and remove task-like records from the primary workspace.",
        ("User adds a new todo item", "User completes and deletes an existing todo"),
        ("User can add a todo item", "User can complete and delete a todo item"),
    ),
    _FeatureDefinition(
        "navigation",
        "Navigation",
        ("nav", "navigation", "route", "router", "menu", "href", "link"),
        "Links, routes, and shell navigation that connect feature areas together.",
        ("User can move between primary sections",),
        ("User can navigate between primary pages",),
    ),
    _FeatureDefinition(
        "profile-settings",
        "Profile and Settings",
        ("profile", "settings", "preferences", "logout", "account"),
        "Account-facing settings, profile surfaces, and session actions.",
        ("User can review profile information", "User can sign out from the workspace"),
        ("User can view profile details", "User can sign out from settings"),
    ),
    _FeatureDefinition(
        "cli-workflow",
        "CLI Workflow",
        ("cli", "click", "command", "index", "generate", "plan", "--help"),
        "Command-line workflows that drive indexing, generation, and planning.",
        ("User indexes a repository from the CLI", "User generates a test from saved memory"),
        ("User can index a repository from the CLI", "User can generate output from saved memory"),
    ),
    _FeatureDefinition(
        "repository-analysis",
        "Repository Analysis",
        ("crawl", "crawler", "chunk", "indexer", "embed", "memory map", "repository"),
        "Repository discovery, chunking, indexing, and memory-building capabilities.",
        ("Repository files are grouped into meaningful feature areas",),
        ("Repository analysis groups related artifacts",),
    ),
    _FeatureDefinition(
        "test-generation",
        "Test Generation",
        ("playwright", "generator", "expect", "page.goto", "selector", "test"),
        "Prompt building and test-generation behavior driven by repository context.",
        ("User receives generated Playwright coverage recommendations",),
        ("User receives evidence-backed Playwright coverage recommendations",),
    ),
    _FeatureDefinition(
        "documentation",
        "Documentation",
        ("readme", "documentation", "quickstart", "guide"),
        "User-facing guidance that explains workflows and expected outcomes.",
        ("User can follow the documented setup and workflow",),
        ("User can follow the documented CLI workflow",),
    ),
)

_FALLBACK_FEATURES: dict[str, _FeatureDefinition] = {
    "tests": _FeatureDefinition(
        "testing-support",
        "Testing Support",
        (),
        "Shared fixtures, regression coverage, and validation helpers that support delivery.",
        ("Contributors can verify behavior deterministically",),
        ("Regression coverage validates expected workflows",),
    ),
    "docs": _FEATURE_DEFINITIONS[-1],
}


def infer_repository_feature_map(
    files: Sequence[FileInfo],
    chunks: Sequence[Chunk] | None = None,
    source_root: str = ".",
    generated_at: str = "",
) -> RepositoryFeatureMap:
    """Infer feature areas, correlations, and test opportunities for *files*."""
    chunk_count = len(chunks or [])
    chunk_ranges = _chunk_ranges_by_file(chunks or [])
    languages: dict[str, int] = {}
    for file_info in files:
        languages[file_info.language] = languages.get(file_info.language, 0) + 1

    matched_artifacts: dict[str, list[ArtifactEvidence]] = {}
    feature_scores: dict[str, int] = {}

    for file_info in files:
        matches = _match_features(file_info)
        for definition, keywords in matches:
            artifact = _artifact_from_file(
                file_info,
                definition.feature_id,
                keywords,
                chunk_ranges.get(file_info.path),
            )
            matched_artifacts.setdefault(definition.feature_id, []).append(artifact)
            feature_scores[definition.feature_id] = feature_scores.get(definition.feature_id, 0) + len(keywords)

    features: list[FeatureArea] = []
    for definition in _FEATURE_DEFINITIONS:
        artifacts = matched_artifacts.get(definition.feature_id, [])
        if not artifacts:
            continue
        confidence = min(0.98, 0.35 + 0.08 * feature_scores.get(definition.feature_id, 0))
        features.append(
            FeatureArea(
                feature_id=definition.feature_id,
                name=definition.name,
                summary=definition.summary,
                confidence=confidence,
                artifacts=artifacts,
                entry_points=_entry_points(artifacts),
                workflows=list(definition.workflows),
            )
        )

    correlations = _build_correlations(features)
    opportunities = _build_test_opportunities(features, correlations)

    file_index = [
        {"path": file_info.path, "language": file_info.language}
        for file_info in sorted(files, key=lambda item: item.path)
    ]

    return RepositoryFeatureMap(
        generated_at=generated_at,
        source_root=source_root,
        total_files=len(files),
        total_chunks=chunk_count,
        languages=languages,
        features=features,
        correlations=correlations,
        test_opportunities=opportunities,
        file_index=file_index,
    )


def format_feature_summary(feature_map: RepositoryFeatureMap, limit: int = 5) -> str:
    """Return a compact CLI-friendly summary of inferred feature areas."""
    if not feature_map.features:
        return "No feature areas inferred."

    lines = ["Feature areas inferred:"]
    for feature in sorted(feature_map.features, key=lambda item: (-item.confidence, item.name))[:limit]:
        evidence_paths = ", ".join(sorted({artifact.file_path for artifact in feature.artifacts})[:3])
        lines.append(
            f"  - {feature.name} ({feature.confidence:.2f}): {feature.summary} Evidence: {evidence_paths}"
        )
    if feature_map.correlations:
        lines.append("Feature correlations:")
        for correlation in feature_map.correlations[:limit]:
            lines.append(
                "  - "
                f"{correlation.source_feature_id} -> {correlation.target_feature_id} "
                f"({correlation.relationship_type}, {correlation.confidence:.2f})"
            )
    return "\n".join(lines)


def _match_features(file_info: FileInfo) -> list[tuple[_FeatureDefinition, tuple[str, ...]]]:
    text = f"{file_info.path}\n{file_info.content}".lower()
    matches: list[tuple[_FeatureDefinition, tuple[str, ...]]] = []
    for definition in _FEATURE_DEFINITIONS:
        keywords = tuple(keyword for keyword in definition.keywords if keyword in text)
        if keywords:
            matches.append((definition, keywords))

    if matches:
        return matches

    top_level = file_info.path.split("/", 1)[0].split("\\", 1)[0].lower()
    fallback = _FALLBACK_FEATURES.get(top_level)
    if fallback is not None:
        return [(fallback, (top_level,))]
    return []


def _artifact_from_file(
    file_info: FileInfo,
    feature_id: str,
    keywords: Iterable[str],
    chunk_range: tuple[int, int] | None = None,
) -> ArtifactEvidence:
    line_count = max(1, len(file_info.content.splitlines()))
    start_line, end_line = chunk_range or (1, line_count)
    matched = sorted(set(keywords))
    summary = f"Matched feature signals {', '.join(matched[:4])} in {file_info.path}"
    return ArtifactEvidence(
        artifact_id=f"{feature_id}:{file_info.path}",
        file_path=file_info.path,
        language=file_info.language,
        start_line=start_line,
        end_line=end_line,
        signal_type="keyword-match",
        summary=summary,
    )


def _entry_points(artifacts: Sequence[ArtifactEvidence]) -> list[str]:
    seen: list[str] = []
    for artifact in artifacts:
        basename = artifact.file_path.rsplit("/", 1)[-1]
        if basename not in seen:
            seen.append(basename)
    return seen[:5]


def _chunk_ranges_by_file(chunks: Sequence[Chunk]) -> dict[str, tuple[int, int]]:
    ranges: dict[str, tuple[int, int]] = {}
    for chunk in chunks:
        existing = ranges.get(chunk.file_path)
        if existing is None:
            ranges[chunk.file_path] = (chunk.start_line, chunk.end_line)
            continue
        ranges[chunk.file_path] = (
            min(existing[0], chunk.start_line),
            max(existing[1], chunk.end_line),
        )
    return ranges


def _build_correlations(features: Sequence[FeatureArea]) -> list[FeatureCorrelation]:
    by_file: dict[str, list[str]] = {}
    for feature in features:
        for artifact in feature.artifacts:
            by_file.setdefault(artifact.file_path, []).append(feature.feature_id)

    correlations: dict[tuple[str, str], FeatureCorrelation] = {}
    for file_path, feature_ids in by_file.items():
        unique_ids = sorted(set(feature_ids))
        if len(unique_ids) < 2:
            continue
        for source, target in itertools.combinations(unique_ids, 2):
            key = (source, target)
            correlations[key] = FeatureCorrelation(
                correlation_id=f"{source}:{target}",
                source_feature_id=source,
                target_feature_id=target,
                relationship_type="shared-artifact",
                confidence=0.65,
                evidence_ids=[f"{source}:{file_path}", f"{target}:{file_path}"],
                summary=f"{source} and {target} both rely on {file_path}",
            )
    return list(correlations.values())


def _build_test_opportunities(
    features: Sequence[FeatureArea],
    correlations: Sequence[FeatureCorrelation],
) -> list[TestOpportunity]:
    opportunities: list[TestOpportunity] = []
    definitions = {definition.feature_id: definition for definition in _FEATURE_DEFINITIONS}

    for feature in features:
        definition = definitions.get(feature.feature_id)
        if definition is None:
            continue
        titles = definition.opportunity_titles or (f"{feature.name} works as expected",)
        for index, title in enumerate(titles, start=1):
            opportunity_id = f"{feature.feature_id}:opportunity:{index}"
            uncertainty_notes: list[str] = []
            if feature.confidence < 0.6:
                uncertainty_notes.append(
                    "Repository evidence is partial; review selectors, routes, and user flows before relying on this scenario."
                )
            opportunities.append(
                TestOpportunity(
                    opportunity_id=opportunity_id,
                    feature_id=feature.feature_id,
                    title=title,
                    priority="high" if index == 1 else "medium",
                    confidence=feature.confidence,
                    evidence_ids=[artifact.artifact_id for artifact in feature.artifacts[:3]],
                    preconditions=_preconditions_for_feature(feature.feature_id),
                    assertions=list(feature.workflows[:2]) or [feature.summary],
                    uncertainty_notes=uncertainty_notes,
                )
            )

    for item in correlations:
        title = f"{_display_name(item.source_feature_id)} and {_display_name(item.target_feature_id)} work together"
        opportunities.append(
            TestOpportunity(
                opportunity_id=f"{item.correlation_id}:flow",
                feature_id=item.source_feature_id,
                title=title,
                priority="medium",
                confidence=item.confidence,
                evidence_ids=item.evidence_ids,
                preconditions=[],
                assertions=[item.summary],
                uncertainty_notes=[],
            )
        )
    return opportunities


def _preconditions_for_feature(feature_id: str) -> list[str]:
    if feature_id == "authentication":
        return ["Application is reachable at the configured base URL"]
    if feature_id == "todo-management":
        return ["User is authenticated before mutating todo data"]
    return []


def _display_name(feature_id: str) -> str:
    for definition in _FEATURE_DEFINITIONS:
        if definition.feature_id == feature_id:
            return definition.name
    return feature_id.replace("-", " ").title()
