import hashlib
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
RUBRIC_FIXTURE = ROOT / "tests" / "fixtures" / "assignment-v2" / "rubric.json"


def write_rubric(path, thesis_path):
    rubric = json.loads(RUBRIC_FIXTURE.read_text(encoding="utf-8"))
    thesis = thesis_path.read_text(encoding="utf-8")
    rubric["thesis_fingerprint"] = hashlib.sha256(thesis.encode("utf-8")).hexdigest()
    for category in rubric["categories"]:
        for score in category["anchors"]:
            category["anchors"][score] += f" Thesis context: {thesis}"
    path.write_text(json.dumps(rubric), encoding="utf-8")
    return path


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

    def write_snapshot_fixture(self, root, count, *, include_hn=False):
        product_hunt_entries = []
        yc_companies = []
        for index in range(count):
            product_hunt_entries.append(
                f"""  <entry>
    <id>tag:producthunt.com,2026-08-20:post/{1000 + index}</id>
    <title>Company {index} – Workflow automation</title>
    <updated>2026-08-20T12:00:00Z</updated>
    <link rel="related" href="https://company-{index}.example/launch" />
    <link rel="alternate" href="https://www.producthunt.com/posts/company-{index}" />
    <summary>Company {index} automates a recurring workflow.</summary>
  </entry>"""
            )
            yc_companies.append(
                {
                    "id": 2000 + index,
                    "name": f"Company {index}",
                    "slug": f"company-{index}",
                    "website": f"https://company-{index}.example",
                    "one_liner": f"Company {index} automates a recurring workflow.",
                    "batch": "S26",
                    "url": f"https://www.ycombinator.com/companies/company-{index}",
                }
            )
        product_hunt = root / "product-hunt.atom"
        product_hunt.write_text(
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<feed xmlns="http://www.w3.org/2005/Atom">\n'
            + "\n".join(product_hunt_entries)
            + "\n</feed>\n",
            encoding="utf-8",
        )
        yc = root / "yc.json"
        yc.write_text(json.dumps({"companies": yc_companies}), encoding="utf-8")
        hacker_news = None
        if include_hn:
            hacker_news = root / "hn.json"
            hacker_news.write_text(
                json.dumps(
                    [
                        {
                            "id": 3000,
                            "type": "story",
                            "title": "Show HN: Company 0 – Workflow automation",
                            "url": "https://company-0.example/launch",
                            "time": 1787227200,
                            "score": 42,
                            "descendants": 7,
                        }
                    ]
                ),
                encoding="utf-8",
            )
        return product_hunt, yc, hacker_news

    def run_snapshot_fixture(self, root, count, *, include_hn=False):
        source_input = root / "input.json"
        source_thesis = root / "thesis.md"
        source_input.write_text(
            json.dumps(
                {
                    "seed": {"type": "topic", "value": "Workflow automation"},
                    "sourcing": {"target_count": 10},
                    "research": {"full_coverage": True},
                }
            ),
            encoding="utf-8",
        )
        source_thesis.write_text("Back recurring workflow automation.", encoding="utf-8")
        rubric = write_rubric(root / "rubric.json", source_thesis)
        run_dir = root / "run"
        initialized = self.run_cli(
            RUN,
            "init",
            "--run-dir",
            run_dir,
            "--input",
            source_input,
            "--thesis",
            source_thesis,
            "--rubric",
            rubric,
            cwd=root,
        )
        self.assertEqual(initialized.returncode, 0, initialized.stderr)
        product_hunt, yc, hacker_news = self.write_snapshot_fixture(
            root, count, include_hn=include_hn
        )
        arguments = [
            "snapshots",
            "--input",
            run_dir / "input.json",
            "--thesis",
            run_dir / "thesis.md",
            "--product-hunt",
            product_hunt,
            "--yc",
            yc,
        ]
        if hacker_news is not None:
            arguments.extend(["--hacker-news", hacker_news])
        arguments.extend(
            [
                "--output",
                run_dir / "sourcing" / "candidates.json",
                "--retrieval-output",
                run_dir / "sourcing" / "retrieval.json",
            ]
        )
        produced = self.run_cli(SEARCH, *arguments, cwd=root)
        self.assertEqual(produced.returncode, 0, produced.stderr)
        return run_dir

    def test_snapshot_dual_origins_and_hn_provenance_pass_v2_sourcing_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = self.run_snapshot_fixture(root, 10, include_hn=True)
            candidates = json.loads(
                (run_dir / "sourcing" / "candidates.json").read_text(encoding="utf-8")
            )
            retrieval = json.loads(
                (run_dir / "sourcing" / "retrieval.json").read_text(encoding="utf-8")
            )
            staged = self.run_cli(
                RUN,
                "stage",
                "--run-dir",
                run_dir,
                "--stage",
                "sourcing",
                "--status",
                "completed",
                "--provider",
                "source_snapshots",
                "--exit-code",
                "0",
                "--artifact",
                "sourcing/retrieval.json",
                "--artifact",
                "sourcing/candidates.json",
                cwd=root,
            )

        self.assertEqual(staged.returncode, 0, staged.stderr)
        candidate = candidates["candidates"][0]
        self.assertEqual({origin["source"] for origin in candidate["origins"]}, {"product_hunt", "yc"})
        self.assertEqual(
            set(candidate["source_urls"]),
            {
                *(origin["canonical_url"] for origin in candidate["origins"]),
                "https://news.ycombinator.com/item?id=3000",
            },
        )
        candidate_results = [
            result
            for result in retrieval["results"]
            if result["candidate_slug"] == candidate["slug"]
        ]
        self.assertEqual({result["source"] for result in candidate_results}, {"product_hunt", "yc", "hacker_news"})
        self.assertTrue(
            all(
                result.get("candidate_name") == candidate["name"]
                and result.get("candidate_website") == candidate["website"]
                and result.get("source_id")
                and result.get("url")
                for result in candidate_results
            )
        )

    def test_snapshot_exclusion_origins_are_emitted_and_pass_v2_sourcing_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = self.run_snapshot_fixture(root, 11)
            candidates = json.loads(
                (run_dir / "sourcing" / "candidates.json").read_text(encoding="utf-8")
            )
            retrieval = json.loads(
                (run_dir / "sourcing" / "retrieval.json").read_text(encoding="utf-8")
            )
            staged = self.run_cli(
                RUN,
                "stage",
                "--run-dir",
                run_dir,
                "--stage",
                "sourcing",
                "--status",
                "completed",
                "--provider",
                "source_snapshots",
                "--exit-code",
                "0",
                "--artifact",
                "sourcing/retrieval.json",
                "--artifact",
                "sourcing/candidates.json",
                cwd=root,
            )

        self.assertEqual(staged.returncode, 0, staged.stderr)
        self.assertEqual(len(candidates["candidates"]), 10)
        self.assertEqual(len(candidates["excluded"]), 1)
        exclusion = candidates["excluded"][0]
        exclusion_results = [
            result
            for result in retrieval["results"]
            if result.get("candidate_name") == exclusion["name"]
        ]
        self.assertEqual(len(exclusion_results), 2)
        self.assertEqual({result["source"] for result in exclusion_results}, {"product_hunt", "yc"})
        self.assertEqual(
            {result["source_id"] for result in exclusion_results},
            {origin["source_id"] for origin in exclusion["origins"]},
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
            source_input = root / "source-input.json"
            source_thesis = root / "source-thesis.md"
            source_input.write_text(
                json.dumps({
                    "seed": {"type": "topic", "value": "Workflow AI"},
                    "sourcing": {"target_count": 10},
                    "research": {"full_coverage": True},
                }),
                encoding="utf-8",
            )
            source_thesis.write_text("Automate recurring diligence.", encoding="utf-8")
            source_rubric = write_rubric(root / "rubric.json", source_thesis)
            run_dir = root / "run"
            initialized = self.run_cli(
                RUN, "init", "--run-dir", run_dir, "--input", source_input,
                "--thesis", source_thesis, "--rubric", source_rubric, cwd=root,
            )
            self.assertEqual(initialized.returncode, 0, initialized.stderr)
            output = run_dir / "sourcing" / "candidates.json"
            retrieval_output = run_dir / "sourcing" / "retrieval.json"
            env = os.environ.copy()
            env.pop("EXA_API_KEY", None)

            result = self.run_cli(
                SEARCH,
                "snapshots",
                "--input", run_dir / "input.json",
                "--thesis", run_dir / "thesis.md",
                "--product-hunt", SOURCE_FIXTURES / "product-hunt.atom",
                "--yc", SOURCE_FIXTURES / "yc-companies.json",
                "--hacker-news", SOURCE_FIXTURES / "hacker-news-items.json",
                "--output", output,
                "--retrieval-output", retrieval_output,
                cwd=root,
                env=env,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(output.read_text(encoding="utf-8"))
            retrieval = json.loads(retrieval_output.read_text(encoding="utf-8"))
            staged = self.run_cli(
                RUN, "stage", "--run-dir", run_dir, "--stage", "sourcing",
                "--status", "partial", "--provider", "source_snapshots",
                "--exit-code", "0", "--artifact", "sourcing/retrieval.json",
                "--artifact", "sourcing/candidates.json", cwd=root,
            )
            manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))

        self.assertEqual(staged.returncode, 0, staged.stderr)
        self.assertEqual(manifest["stages"]["sourcing"]["status"], "partial")
        self.assertEqual(payload["provider"], "source_snapshots")
        self.assertEqual(payload["provider"], retrieval["provider"])
        self.assertEqual(payload["query"], retrieval["query"])
        self.assertEqual(payload["retrieval_path"], "sourcing/retrieval.json")
        self.assertEqual(payload["requested_count"], 10)
        self.assertEqual(payload["actual_count"], 1)
        self.assertEqual(payload["excluded"], [])
        self.assertEqual(retrieval["status"], "ok")
        self.assertEqual(retrieval["exit_code"], 0)
        self.assertTrue(retrieval["retrieved_at"].endswith("Z"))
        self.assertEqual(len(retrieval["results"]), 3)
        candidate = payload["candidates"][0]
        self.assertEqual(
            candidate["thesis_fit_reasons"],
            [
                "Acme AI matches the sourcing topic: Workflow AI.",
                "Acme AI is relevant to the investment thesis: Automate recurring diligence.",
            ],
        )
        self.assertEqual(candidate["fit_reasons"], candidate["thesis_fit_reasons"])
        self.assertEqual(candidate["candidate_type"], "priority")
        self.assertEqual(candidate["research_priority"], 1)
        self.assertEqual(candidate["source_quality"], "primary_record")
        self.assertTrue(candidate["selected_for_research"])
        self.assertEqual(
            {origin["source"] for origin in candidate["origins"]},
            {"product_hunt", "yc"},
        )
        self.assertNotIn("hacker_news", {origin["source"] for origin in candidate["origins"]})
        self.assertIn(
            "https://news.ycombinator.com/item?id=987654",
            {signal["source_url"] for signal in candidate["freshness_or_traction_signals"]},
        )

    def test_snapshot_mode_enforces_requested_count_and_hard_max(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "input.json"
            thesis_path = root / "thesis.md"
            output = root / "candidates.json"
            retrieval = root / "retrieval.json"
            input_data = {
                "seed": {"type": "topic", "value": "Vertical workflow software"},
                "sourcing": {"target_count": 10},
                "research": {"full_coverage": True},
            }
            input_path.write_text(json.dumps(input_data), encoding="utf-8")
            thesis_path.write_text("Back durable workflow automation.", encoding="utf-8")
            companies = []
            for index in range(11):
                companies.append({
                    "id": 100 + index,
                    "name": f"Company {index}",
                    "slug": f"company-{index}",
                    "website": f"https://company-{index}.example",
                    "one_liner": f"Automates workflow {index}.",
                    "batch": "S26",
                    "url": f"https://www.ycombinator.com/companies/company-{index}",
                })
            yc_path = root / "yc.json"
            yc_path.write_text(json.dumps({"companies": companies}), encoding="utf-8")

            limited = self.run_cli(
                SEARCH, "snapshots", "--input", input_path, "--thesis", thesis_path,
                "--product-hunt", SOURCE_FIXTURES / "product-hunt.atom",
                "--yc", yc_path, "--output", output,
                "--retrieval-output", retrieval, cwd=root,
            )
            self.assertEqual(limited.returncode, 0, limited.stderr)
            payload = json.loads(output.read_text(encoding="utf-8"))

            input_data["sourcing"]["target_count"] = 21
            input_path.write_text(json.dumps(input_data), encoding="utf-8")
            over_limit = self.run_cli(
                SEARCH, "snapshots", "--input", input_path, "--thesis", thesis_path,
                "--product-hunt", SOURCE_FIXTURES / "product-hunt.atom",
                "--yc", yc_path, "--output", root / "over-limit.json",
                "--retrieval-output", root / "over-limit-retrieval.json", cwd=root,
            )

        self.assertEqual(payload["requested_count"], 10)
        self.assertEqual(payload["actual_count"], 10)
        self.assertEqual(len(payload["candidates"]), 10)
        self.assertTrue(all(candidate["selected_for_research"] for candidate in payload["candidates"]))
        self.assertEqual(len(payload["excluded"]), 2)
        self.assertTrue(all(exclusion["origins"] for exclusion in payload["excluded"]))
        self.assertTrue(all("requested count" in exclusion["reason"] for exclusion in payload["excluded"]))
        self.assertEqual(over_limit.returncode, 2)

    def test_run_stage_cli_accepts_source_snapshots_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_input = root / "input.json"
            source_thesis = root / "thesis.md"
            source_input.write_text(
                json.dumps({"seed": {"type": "topic", "value": "AI"}}),
                encoding="utf-8",
            )
            source_thesis.write_text("Recurring workflows.", encoding="utf-8")
            source_rubric = write_rubric(root / "rubric.json", source_thesis)
            run_dir = root / "run"
            initialized = self.run_cli(
                RUN, "init", "--run-dir", run_dir, "--input", source_input,
                "--thesis", source_thesis, "--rubric", source_rubric, cwd=root,
            )
            self.assertEqual(initialized.returncode, 0, initialized.stderr)
            sourcing = run_dir / "sourcing"
            (sourcing / "retrieval.json").write_text(json.dumps({
                "query": "AI",
                "provider": "source_snapshots",
                "retrieved_at": "2026-08-24T00:00:00Z",
                "status": "ok",
                "exit_code": 0,
                "results": [],
            }), encoding="utf-8")
            (sourcing / "candidates.json").write_text(json.dumps({
                "provider": "source_snapshots",
                "query": "AI",
                "retrieval_path": "sourcing/retrieval.json",
                "requested_count": 15,
                "actual_count": 0,
                "candidates": [],
                "excluded": [],
            }), encoding="utf-8")

            staged = self.run_cli(
                RUN, "stage", "--run-dir", run_dir, "--stage", "sourcing",
                "--status", "partial", "--provider", "source_snapshots",
                "--exit-code", "0", "--artifact", "sourcing/retrieval.json",
                "--artifact", "sourcing/candidates.json", cwd=root,
            )
            manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))

        self.assertEqual(staged.returncode, 0, staged.stderr)
        self.assertEqual(manifest["stages"]["sourcing"]["status"], "partial")

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
