import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
RUN_SCRIPT = ROOT / "skills" / "investment-research-start" / "scripts" / "run.py"


def load_module():
    spec = importlib.util.spec_from_file_location("investment_run", RUN_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RunScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.run_module = load_module()

    def test_key_precedence_and_preflight_redact_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, ".env.local").write_text(
                "EXA_API_KEY='file-secret'\n", encoding="utf-8"
            )
            with patch.dict(os.environ, {"EXA_API_KEY": "process-secret"}, clear=True):
                key, source = self.run_module.load_api_key(directory)
                result = self.run_module.preflight(
                    cwd=directory, sdk_available=False, network_status="not_checked"
                )

        self.assertEqual((key, source), ("process-secret", "environment"))
        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["recommended_provider"], "web")
        self.assertNotIn("process-secret", json.dumps(result))

    def test_key_lookup_finds_repository_env_from_nested_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".git").mkdir()
            (root / ".env.local").write_text("EXA_API_KEY=file-secret\n", encoding="utf-8")
            nested = root / "runs" / "one"
            nested.mkdir(parents=True)
            with patch.dict(os.environ, {}, clear=True):
                key, source = self.run_module.load_api_key(nested)

        self.assertEqual((key, source), ("file-secret", "env_local"))

    def test_preflight_classifies_ready_and_network_failure(self):
        with patch.dict(os.environ, {"EXA_API_KEY": "secret"}, clear=True):
            ready = self.run_module.preflight(sdk_available=True, network_status="reachable")
            degraded = self.run_module.preflight(
                sdk_available=True, network_status="unreachable"
            )
        self.assertTrue(ready["exa_ready"])
        self.assertEqual(ready["recommended_provider"], "exa")
        self.assertFalse(degraded["exa_ready"])
        self.assertEqual(degraded["failure_class"], "network_unavailable")

    def test_preflight_output_write_failure_returns_code_six(self):
        with patch.object(
            self.run_module,
            "atomic_write_json",
            side_effect=self.run_module.ArtifactWriteError("blocked"),
        ):
            code = self.run_module.main(["preflight", "--output", "status.json"])
        self.assertEqual(code, 6)

    def test_recommendation_threshold_boundaries_are_deterministic(self):
        thresholds = {"watch_min": 65, "meeting_min": 80}
        self.assertEqual(self.run_module._expected_call(64, thresholds), "Pass")
        self.assertEqual(self.run_module._expected_call(65, thresholds), "Watch")
        self.assertEqual(self.run_module._expected_call(79, thresholds), "Watch")
        self.assertEqual(self.run_module._expected_call(80, thresholds), "Take a meeting")

    def test_init_materializes_defaults_and_resumes_only_matching_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_input = root / "source-input.json"
            source_thesis = root / "source-thesis.md"
            source_input.write_text(
                json.dumps({"seed": {"type": "topic", "value": "AI agents"}}),
                encoding="utf-8",
            )
            source_thesis.write_text("# Thesis\nRecurring workflows.\n", encoding="utf-8")
            run_dir = root / "run"

            first = self.run_module.initialize_run(run_dir, source_input, source_thesis)
            second = self.run_module.initialize_run(run_dir, source_input, source_thesis)
            normalized = json.loads((run_dir / "input.json").read_text(encoding="utf-8"))
            source_thesis.write_text("# Thesis\nChanged.\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "does not match"):
                self.run_module.initialize_run(run_dir, source_input, source_thesis)

        self.assertFalse(first["resumed"])
        self.assertTrue(second["resumed"])
        self.assertEqual(normalized["sourcing"]["target_count"], 15)
        self.assertEqual(normalized["research"]["limit"], 8)
        self.assertFalse(normalized["research"]["full_coverage"])
        self.assertEqual(normalized["recommendation_thresholds"]["watch_min"], 65)

    def test_init_rejects_tampered_or_already_completed_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_input = root / "source.json"
            source_thesis = root / "source.md"
            source_input.write_text(
                json.dumps({"seed": {"type": "topic", "value": "AI"}}), encoding="utf-8"
            )
            source_thesis.write_text("# Thesis\n", encoding="utf-8")
            run_dir = root / "run"
            self.run_module.initialize_run(run_dir, source_input, source_thesis)

            (run_dir / "thesis.md").write_text("# Tampered\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "stored run fingerprint"):
                self.run_module.initialize_run(run_dir, source_input, source_thesis)

            (run_dir / "thesis.md").write_text("# Thesis\n", encoding="utf-8")
            manifest_path = run_dir / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["validation"]["status"] = "completed"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "already completed"):
                self.run_module.initialize_run(run_dir, source_input, source_thesis)

    def test_full_coverage_is_an_explicit_boolean(self):
        normalized = self.run_module.normalize_input(
            {
                "seed": {"type": "topic", "value": "AI"},
                "research": {"limit": 8, "full_coverage": True},
            }
        )
        self.assertTrue(normalized["research"]["full_coverage"])
        with self.assertRaisesRegex(ValueError, "full_coverage"):
            self.run_module.normalize_input(
                {
                    "seed": {"type": "topic", "value": "AI"},
                    "research": {"full_coverage": "yes"},
                }
            )

    def test_atomic_promote_preserves_old_destination_on_invalid_json(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "artifact.tmp"
            destination = root / "artifact.json"
            destination.write_text('{"status":"old"}\n', encoding="utf-8")
            source.write_text("not-json", encoding="utf-8")

            with self.assertRaises(json.JSONDecodeError):
                self.run_module.atomic_promote(source, destination, kind="json")

            self.assertEqual(destination.read_text(encoding="utf-8"), '{"status":"old"}\n')

    def test_atomic_promote_replaces_destination_for_valid_json(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "artifact.tmp"
            destination = root / "artifact.json"
            source.write_text('{"status":"new"}\n', encoding="utf-8")
            destination.write_text('{"status":"old"}\n', encoding="utf-8")

            self.run_module.atomic_promote(source, destination, kind="json")

            self.assertEqual(destination.read_text(encoding="utf-8"), '{"status":"new"}\n')
            self.assertFalse(source.exists())

    def test_stage_completion_requires_valid_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_input = root / "input-source.json"
            thesis = root / "thesis-source.md"
            source_input.write_text(
                json.dumps({"seed": {"type": "topic", "value": "AI"}}),
                encoding="utf-8",
            )
            thesis.write_text("# Thesis\nTest.\n", encoding="utf-8")
            run_dir = root / "run"
            self.run_module.initialize_run(run_dir, source_input, thesis)

            with self.assertRaisesRegex(ValueError, "artifact"):
                self.run_module.update_stage(
                    run_dir,
                    "sourcing",
                    "completed",
                    artifacts=["sourcing/candidates.json"],
                )

            artifact = run_dir / "sourcing" / "candidates.json"
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text('{"candidates":[],"excluded":[]}\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "retrieval.json"):
                self.run_module.update_stage(
                    run_dir,
                    "sourcing",
                    "completed",
                    provider="web",
                    exit_code=0,
                    artifacts=["sourcing/candidates.json"],
                )

            retrieval = artifact.parent / "retrieval.json"
            retrieval.write_text(
                json.dumps(
                    {
                        "query": "AI",
                        "provider": "web",
                        "retrieved_at": "2026-08-23T00:00:00Z",
                        "status": "ok",
                        "exit_code": 0,
                        "results": [],
                    }
                ),
                encoding="utf-8",
            )
            artifact.write_text(
                json.dumps(
                    {
                        "provider": "web",
                        "query": "AI",
                        "retrieval_path": "sourcing/retrieval.json",
                        "requested_count": 15,
                        "actual_count": 0,
                        "candidates": [],
                        "excluded": [],
                    }
                ),
                encoding="utf-8",
            )
            manifest = self.run_module.update_stage(
                run_dir,
                "sourcing",
                "completed",
                provider="web",
                exit_code=0,
                artifacts=["sourcing/retrieval.json", "sourcing/candidates.json"],
            )

        self.assertEqual(manifest["stages"]["sourcing"]["status"], "completed")
        self.assertEqual(manifest["stages"]["sourcing"]["attempt_count"], 1)

    def test_research_stage_blocks_more_than_initial_attempt_and_one_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_input = root / "input.json"
            thesis = root / "thesis.md"
            source_input.write_text(
                json.dumps({"seed": {"type": "topic", "value": "AI"}}), encoding="utf-8"
            )
            thesis.write_text("# Thesis\n", encoding="utf-8")
            run_dir = root / "run"
            self.run_module.initialize_run(run_dir, source_input, thesis)
            self.run_module.update_stage(run_dir, "research", "running", company="acme")
            self.run_module.update_stage(run_dir, "research", "running", company="acme")

            with self.assertRaisesRegex(ValueError, "one retry"):
                self.run_module.update_stage(run_dir, "research", "running", company="acme")

    def test_company_stage_rejects_unsafe_slug(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_input = root / "input.json"
            thesis = root / "thesis.md"
            source_input.write_text(
                json.dumps({"seed": {"type": "topic", "value": "AI"}}), encoding="utf-8"
            )
            thesis.write_text("# Thesis\n", encoding="utf-8")
            run_dir = root / "run"
            self.run_module.initialize_run(run_dir, source_input, thesis)

            with self.assertRaisesRegex(ValueError, "company slug"):
                self.run_module.update_stage(
                    run_dir, "research", "running", company="../../outside"
                )

    def test_legacy_fixture_reports_mixed_and_stale_without_writing(self):
        fixture = ROOT / "tests" / "fixtures" / "legacy-run"
        before = {
            path.relative_to(fixture): path.read_bytes()
            for path in fixture.rglob("*")
            if path.is_file()
        }

        result = self.run_module.validate_run(fixture)

        after = {
            path.relative_to(fixture): path.read_bytes()
            for path in fixture.rglob("*")
            if path.is_file()
        }
        self.assertFalse(result["valid"])
        self.assertTrue(any("mixed" in error for error in result["errors"]))
        self.assertTrue(any("stale" in error.lower() for error in result["errors"]))
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
