"""Unit tests for playwright_god.feature_map."""

from __future__ import annotations

from playwright_god.chunker import Chunk
from playwright_god.crawler import FileInfo
from playwright_god.feature_map import (
    ArtifactEvidence,
    FeatureArea,
    FeatureCorrelation,
    RepositoryFeatureMap,
    TestOpportunity as FeatureTestOpportunity,
    _build_test_opportunities,
    _display_name,
    format_feature_summary,
    infer_repository_feature_map,
)


def _chunk(file_path: str, language: str = "javascript") -> Chunk:
    return Chunk(
        file_path=file_path,
        content="content",
        start_line=1,
        end_line=5,
        language=language,
        chunk_id=Chunk._make_id(file_path, 1, 5),
    )


class TestInferRepositoryFeatureMap:
    def test_infers_authentication_and_todo_features(self, sample_repo_files):
        feature_map = infer_repository_feature_map(sample_repo_files)
        feature_ids = {feature.feature_id for feature in feature_map.features}
        assert "authentication" in feature_ids
        assert "todo-management" in feature_ids

    def test_feature_evidence_references_known_files(self, sample_repo_files):
        feature_map = infer_repository_feature_map(sample_repo_files)
        evidence_paths = {
            artifact.file_path
            for feature in feature_map.features
            for artifact in feature.artifacts
        }
        assert "index.html" in evidence_paths
        assert "app.js" in evidence_paths

    def test_builds_correlations_for_shared_artifacts(self, sample_repo_files):
        feature_map = infer_repository_feature_map(sample_repo_files)
        assert feature_map.correlations
        assert any(item.relationship_type == "shared-artifact" for item in feature_map.correlations)

    def test_generates_test_opportunities(self, sample_repo_files):
        feature_map = infer_repository_feature_map(sample_repo_files)
        titles = [item.title for item in feature_map.test_opportunities]
        assert any("sign in" in title.lower() for title in titles)

    def test_tracks_total_files_and_languages(self, sample_repo_files):
        feature_map = infer_repository_feature_map(sample_repo_files, chunks=[_chunk("index.html", "html")])
        assert feature_map.total_files == len(sample_repo_files)
        assert feature_map.total_chunks == 1
        assert feature_map.languages["html"] >= 1

    def test_uses_chunk_ranges_for_artifact_lines(self, sample_repo_files):
        feature_map = infer_repository_feature_map(
            sample_repo_files,
            chunks=[Chunk(file_path="app.js", content="", start_line=5, end_line=25, language="javascript", chunk_id="appjs")],
        )
        auth_feature = next(feature for feature in feature_map.features if feature.feature_id == "authentication")
        app_js_evidence = next(artifact for artifact in auth_feature.artifacts if artifact.file_path == "app.js")
        assert app_js_evidence.start_line == 5
        assert app_js_evidence.end_line == 25

    def test_fallback_feature_used_for_docs_directory(self):
        file_info = FileInfo(
            path="docs/notes.txt",
            absolute_path="/repo/docs/notes.txt",
            content="misc reference",
            language="text",
            size=10,
        )
        feature_map = infer_repository_feature_map([file_info])
        assert {feature.feature_id for feature in feature_map.features} == {"documentation"}

    def test_to_dict_serializes_feature_entities(self):
        artifact = ArtifactEvidence(
            artifact_id="artifact-1",
            file_path="app.py",
            language="python",
            start_line=1,
            end_line=5,
            signal_type="route",
            summary="Example artifact",
        )
        feature = FeatureArea(
            feature_id="feature-1",
            name="Feature",
            summary="Example feature",
            confidence=0.9,
            artifacts=[artifact],
        )
        correlation = FeatureCorrelation(
            correlation_id="feature-1:feature-2",
            source_feature_id="feature-1",
            target_feature_id="feature-2",
            relationship_type="shared-artifact",
            confidence=0.7,
            evidence_ids=["artifact-1"],
            summary="Shared file",
        )
        opportunity = FeatureTestOpportunity(
            opportunity_id="feature-1:test",
            feature_id="feature-1",
            title="User completes the flow",
            priority="high",
            confidence=0.8,
            evidence_ids=["artifact-1"],
            preconditions=["App is running"],
            assertions=["Page loads"],
        )
        repo_map = RepositoryFeatureMap(
            generated_at="2026-04-11T00:00:00+00:00",
            source_root="/repo",
            total_files=1,
            total_chunks=1,
            languages={"python": 1},
            features=[feature],
            correlations=[correlation],
            test_opportunities=[opportunity],
            file_index=[{"path": "app.py", "language": "python"}],
        )

        payload = repo_map.to_dict()

        assert payload["features"][0]["artifacts"][0]["artifact_id"] == "artifact-1"
        assert payload["correlations"][0]["correlation_id"] == "feature-1:feature-2"
        assert payload["test_opportunities"][0]["opportunity_id"] == "feature-1:test"


class TestFormatFeatureSummary:
    def test_summary_contains_feature_names(self, sample_repo_files):
        feature_map = infer_repository_feature_map(sample_repo_files)
        summary = format_feature_summary(feature_map)
        assert "Feature areas inferred" in summary
        assert "Authentication" in summary

    def test_empty_feature_map_summary(self):
        summary = format_feature_summary(
            infer_repository_feature_map([], chunks=[]),
        )
        assert summary == "No feature areas inferred."

    def test_unknown_feature_ids_do_not_create_opportunities(self):
        feature = FeatureArea(
            feature_id="unknown-feature",
            name="Unknown",
            summary="Unknown",
            confidence=0.5,
            artifacts=[],
        )
        assert _build_test_opportunities([feature], []) == []

    def test_display_name_returns_known_and_fallback_values(self):
        assert _display_name("authentication") == "Authentication"
        assert _display_name("custom-feature") == "Custom Feature"
