import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "skills" / "investment-research-start" / "scripts" / "run.py"
SEARCH = ROOT / "skills" / "investment-research-sourcing" / "scripts" / "search.py"
RESEARCH = ROOT / "skills" / "investment-research-evidence" / "scripts" / "research.py"
SOURCE_FIXTURES = ROOT / "tests" / "fixtures" / "sources"


class CliContractTests(unittest.TestCase):
    def run_cli(self, script, *args, cwd, env=None):
        return subprocess.run(
            [sys.executable, str(script), *map(str, args)],
            cwd=cwd,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_search_missing_key_writes_failure_envelope_and_returns_four(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "input.json").write_text(
                json.dumps({"seed": {"type": "topic", "value": "AI"}}), encoding="utf-8"
            )
            (root / "thesis.md").write_text("Recurring workflows.", encoding="utf-8")
            env = os.environ.copy()
            env.pop("EXA_API_KEY", None)
            result = self.run_cli(
                SEARCH, "--input", root / "input.json", "--thesis", root / "thesis.md",
                "--output", root / "retrieval.json", cwd=root, env=env,
            )
            payload = json.loads((root / "retrieval.json").read_text(encoding="utf-8"))

        self.assertEqual(result.returncode, 4)
        self.assertEqual(payload["exit_code"], 4)
        self.assertEqual(payload["status"], "failed")
        self.assertNotIn("EXA_API_KEY=", result.stdout + result.stderr)

    def test_search_snapshot_mode_writes_normalized_candidates_without_exa(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "candidates.json"
            env = os.environ.copy()
            env.pop("EXA_API_KEY", None)

            result = self.run_cli(
                SEARCH,
                "snapshots",
                "--product-hunt", SOURCE_FIXTURES / "product-hunt.atom",
                "--yc", SOURCE_FIXTURES / "yc-companies.json",
                "--hacker-news", SOURCE_FIXTURES / "hacker-news-items.json",
                "--output", output,
                cwd=root,
                env=env,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(payload["provider"], "official_snapshots")
        self.assertEqual(payload["actual_count"], 1)
        self.assertEqual(payload["excluded"], [])
        candidate = payload["candidates"][0]
        self.assertEqual(
            {origin["source"] for origin in candidate["origins"]},
            {"product_hunt", "yc"},
        )
        self.assertNotIn("hacker_news", {origin["source"] for origin in candidate["origins"]})
        self.assertIn(
            "https://news.ycombinator.com/item?id=987654",
            {signal["source_url"] for signal in candidate["freshness_or_traction_signals"]},
        )

    def test_research_rejects_empty_retry_with_code_two(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "candidates.json").write_text(
                json.dumps({"candidates": [{"name": "Acme", "slug": "acme", "website": "https://acme.example"}]}),
                encoding="utf-8",
            )
            result = self.run_cli(
                RESEARCH, "--candidates", root / "candidates.json", "--slug", "acme",
                "--focus", "--output", root / "retry.json", cwd=root,
            )
            payload = json.loads((root / "retry.json").read_text(encoding="utf-8"))

        self.assertEqual(result.returncode, 2)
        self.assertEqual(payload["exit_code"], 2)

    def test_research_rejects_non_object_candidates_with_code_two(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "candidates.json").write_text("[]", encoding="utf-8")
            result = self.run_cli(
                RESEARCH, "--candidates", root / "candidates.json", "--slug", "acme",
                "--output", root / "retrieval.json", cwd=root,
            )
            payload = json.loads((root / "retrieval.json").read_text(encoding="utf-8"))

        self.assertEqual(result.returncode, 2)
        self.assertEqual(payload["exit_code"], 2)
        self.assertNotIn("traceback", result.stderr.lower())

    def test_run_cli_uses_write_and_validation_exit_codes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            temporary = root / "artifact.tmp"
            destination = root / "artifact.json"
            temporary.write_text("broken", encoding="utf-8")
            destination.write_text('{"old":true}', encoding="utf-8")
            commit = self.run_cli(
                RUN, "commit", "--source", temporary, "--destination", destination,
                "--kind", "json", cwd=root,
            )
            validate = self.run_cli(
                RUN, "validate", "--run-dir", root / "missing-run", cwd=root,
            )

        self.assertEqual(commit.returncode, 6)
        self.assertEqual(validate.returncode, 7)


if __name__ == "__main__":
    unittest.main()
