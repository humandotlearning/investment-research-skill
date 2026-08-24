import contextlib
import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "investment-research-start" / "scripts" / "run.py"
FIXTURE = ROOT / "tests" / "fixtures" / "assignment-v2"


def load_run():
    spec = importlib.util.spec_from_file_location("assignment_v2_lifecycle_run", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AssignmentV2LifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.run_module = load_run()

    def write_sources(self, root, *, input_change=None, thesis=None, rubric_change=None):
        root.mkdir(parents=True, exist_ok=True)
        input_data = json.loads((FIXTURE / "input.json").read_text(encoding="utf-8"))
        if input_change:
            input_change(input_data)
        thesis_text = thesis or (FIXTURE / "thesis.md").read_text(encoding="utf-8")
        rubric = json.loads((FIXTURE / "rubric.json").read_text(encoding="utf-8"))
        rubric["thesis_fingerprint"] = hashlib.sha256(
            thesis_text.encode("utf-8")
        ).hexdigest()
        if rubric_change:
            rubric_change(rubric)
        input_path = root / "input.json"
        thesis_path = root / "thesis.md"
        rubric_path = root / "rubric.json"
        input_path.write_text(json.dumps(input_data), encoding="utf-8")
        thesis_path.write_text(thesis_text, encoding="utf-8")
        rubric_path.write_text(json.dumps(rubric), encoding="utf-8")
        return input_path, thesis_path, rubric_path

    def test_normalize_input_materializes_assignment_v2_defaults(self):
        normalized = self.run_module.normalize_input(
            {"seed": {"type": "topic", "value": "visual-memory agents"}}
        )

        self.assertEqual(normalized["version"], 2)
        self.assertEqual(
            normalized["sourcing"],
            {
                "target_count": 10,
                "primary_sources": ["product_hunt", "yc"],
                "signal_sources": ["hacker_news"],
            },
        )
        self.assertEqual(normalized["research"], {"full_coverage": True})
        self.assertNotIn("limit", normalized["research"])
        self.assertEqual(
            normalized["recommendation_thresholds"],
            {"watch_min": 65, "meeting_min": 80},
        )

    def test_initialize_requires_nonempty_thesis_and_strict_thesis_linked_rubric(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path, thesis_path, rubric_path = self.write_sources(root / "sources")
            with self.assertRaisesRegex(ValueError, "rubric"):
                self.run_module.initialize_run(root / "missing-rubric", input_path, thesis_path)

            thesis_path.write_text("\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "thesis"):
                self.run_module.initialize_run(
                    root / "empty-thesis", input_path, thesis_path, rubric_path
                )

            input_path, thesis_path, rubric_path = self.write_sources(
                root / "bad-sources",
                rubric_change=lambda value: value["categories"][2].update(
                    {"name": "Market attractiveness"}
                ),
            )
            with self.assertRaisesRegex(ValueError, "categories"):
                self.run_module.initialize_run(
                    root / "bad-rubric", input_path, thesis_path, rubric_path
                )

            rubric_changes = {
                "weight": lambda value: value["categories"][0].update({"weight": 19}),
                "anchors": lambda value: value["categories"][0]["anchors"].pop("10"),
                "total": lambda value: value.update({"total_weight": 99}),
                "thesis": lambda value: value.update({"thesis_fingerprint": "wrong"}),
            }
            for label, change in rubric_changes.items():
                with self.subTest(rubric_rule=label):
                    sources = self.write_sources(
                        root / f"bad-{label}", rubric_change=change
                    )
                    with self.assertRaisesRegex(ValueError, "rubric"):
                        self.run_module.initialize_run(root / f"run-{label}", *sources)

    def test_initialize_versions_files_and_resumes_only_exact_assignment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources = self.write_sources(root / "sources")
            run_dir = root / "run"
            first = self.run_module.initialize_run(run_dir, *sources)
            second = self.run_module.initialize_run(run_dir, *sources)
            manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
            normalized = json.loads((run_dir / "input.json").read_text(encoding="utf-8"))

        self.assertFalse(first["resumed"])
        self.assertTrue(second["resumed"])
        self.assertEqual(manifest["version"], 2)
        self.assertEqual(normalized["version"], 2)
        self.assertEqual(manifest["assignment_fingerprint"], first["manifest"]["assignment_fingerprint"])
        self.assertIsNone(manifest["supersedes_run_id"])
        self.assertIsNone(manifest["supersedes_run_path"])
        self.assertIsNone(manifest["superseded_by"])

    def test_resume_rejects_manifest_fingerprint_drift_and_superseded_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources = self.write_sources(root / "sources")
            run_dir = root / "run"
            self.run_module.initialize_run(run_dir, *sources)
            manifest_path = run_dir / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["rubric_fingerprint"] = "0" * 64
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "rubric fingerprint"):
                self.run_module.initialize_run(run_dir, *sources)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old_sources = self.write_sources(root / "old-sources")
            old_run = root / "old-run"
            self.run_module.initialize_run(old_run, *old_sources)
            new_sources = self.write_sources(
                root / "new-sources",
                input_change=lambda value: value["seed"].update(
                    {"value": "new visual-memory topic"}
                ),
            )
            self.run_module.supersede_run(old_run, root / "new-run", *new_sources)

            with self.assertRaisesRegex(ValueError, "superseded"):
                self.run_module.initialize_run(old_run, *old_sources)

    def test_rubric_anchor_keys_are_order_independent_distinct_and_thesis_specific(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def reorder(value):
                anchors = value["categories"][0]["anchors"]
                value["categories"][0]["anchors"] = {
                    "20": anchors["20"],
                    "0": anchors["0"],
                    "10": anchors["10"],
                }

            reordered = self.write_sources(root / "reordered", rubric_change=reorder)
            self.run_module.initialize_run(root / "reordered-run", *reordered)

            def duplicate(value):
                anchors = value["categories"][0]["anchors"]
                anchors["10"] = anchors["0"]

            duplicate_sources = self.write_sources(
                root / "duplicate", rubric_change=duplicate
            )
            with self.assertRaisesRegex(ValueError, "distinct"):
                self.run_module.initialize_run(
                    root / "duplicate-run", *duplicate_sources
                )

            def unrelated(value):
                value["categories"][0]["anchors"] = {
                    "0": "Nebula alpha evidence.",
                    "10": "Nebula beta evidence.",
                    "20": "Nebula gamma evidence.",
                }

            unrelated_sources = self.write_sources(
                root / "unrelated", rubric_change=unrelated
            )
            with self.assertRaisesRegex(ValueError, "thesis token"):
                self.run_module.initialize_run(
                    root / "unrelated-run", *unrelated_sources
                )

            def boilerplate_only(value):
                for category in value["categories"]:
                    category["anchors"] = {
                        "0": "Investment thesis alpha case.",
                        "10": "Investment thesis beta case.",
                        "20": "Investment thesis gamma case.",
                    }

            boilerplate_sources = self.write_sources(
                root / "boilerplate",
                thesis="# Investment thesis\nAI.\n",
                rubric_change=boilerplate_only,
            )
            with self.assertRaisesRegex(ValueError, "meaningful"):
                self.run_module.initialize_run(
                    root / "boilerplate-run", *boilerplate_sources
                )

    def test_changed_input_thesis_or_rubric_never_mutates_existing_run(self):
        changes = {
            "input": {"input_change": lambda value: value.update({"assumptions": ["new"]})},
            "topic": {
                "input_change": lambda value: value["seed"].update(
                    {"value": "changed visual-memory topic"}
                )
            },
            "target": {
                "input_change": lambda value: value.update(
                    {"sourcing": {"target_count": 12}}
                )
            },
            "thesis": {"thesis": "# Changed thesis\nBack visual-memory infrastructure.\n"},
            "rubric": {
                "rubric_change": lambda value: value["categories"][0]["anchors"].update(
                    {"10": "Changed visual workflow team anchor."}
                )
            },
        }
        for label, change in changes.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                original_sources = self.write_sources(root / "original")
                run_dir = root / "run"
                self.run_module.initialize_run(run_dir, *original_sources)
                before = {
                    path.relative_to(run_dir): path.read_bytes()
                    for path in run_dir.rglob("*")
                    if path.is_file()
                }
                changed_sources = self.write_sources(root / "changed", **change)

                with self.assertRaisesRegex(ValueError, "supersede"):
                    self.run_module.initialize_run(run_dir, *changed_sources)

                after = {
                    path.relative_to(run_dir): path.read_bytes()
                    for path in run_dir.rglob("*")
                    if path.is_file()
                }
                self.assertEqual(before, after)

    def test_supersede_creates_new_run_and_bidirectional_links_without_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old_sources = self.write_sources(root / "old-sources")
            old_run = root / "old-run"
            self.run_module.initialize_run(old_run, *old_sources)
            old_assignment_files = {
                name: (old_run / name).read_bytes()
                for name in ("input.json", "thesis.md", "rubric.json")
            }
            new_sources = self.write_sources(
                root / "new-sources",
                input_change=lambda value: value.update(
                    {"sourcing": {"target_count": 12}}
                ),
            )
            new_run = root / "new-run"

            result = self.run_module.supersede_run(old_run, new_run, *new_sources)
            old_manifest = json.loads((old_run / "manifest.json").read_text(encoding="utf-8"))
            new_manifest = json.loads((new_run / "manifest.json").read_text(encoding="utf-8"))

            self.assertFalse(result["resumed"])
            self.assertEqual(new_manifest["supersedes_run_id"], "old-run")
            self.assertEqual(new_manifest["supersedes_run_path"], str(old_run.resolve()))
            self.assertEqual(old_manifest["superseded_by"]["run_id"], "new-run")
            self.assertEqual(old_manifest["superseded_by"]["path"], str(new_run.resolve()))
            self.assertEqual(
                old_assignment_files,
                {
                    name: (old_run / name).read_bytes()
                    for name in ("input.json", "thesis.md", "rubric.json")
                },
            )
            with self.assertRaisesRegex(ValueError, "conflicting"):
                self.run_module.supersede_run(old_run, root / "another-run", *new_sources)

    def test_supersede_retry_repairs_failed_backward_link_without_mutating_new_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old_sources = self.write_sources(root / "old-sources")
            old_run = root / "old-run"
            self.run_module.initialize_run(old_run, *old_sources)
            new_sources = self.write_sources(
                root / "new-sources",
                input_change=lambda value: value["seed"].update(
                    {"value": "recoverable visual-memory topic"}
                ),
            )
            new_run = root / "new-run"
            original_write = self.run_module.atomic_write_json
            new_manifest_writes = []

            def fail_backward_link(path, value):
                resolved = Path(path).resolve()
                if resolved == (new_run / "manifest.json").resolve():
                    new_manifest_writes.append(json.loads(json.dumps(value)))
                if (
                    resolved == (old_run / "manifest.json").resolve()
                    and value.get("superseded_by")
                ):
                    raise self.run_module.ArtifactWriteError("backward link blocked")
                return original_write(path, value)

            with patch.object(
                self.run_module, "atomic_write_json", side_effect=fail_backward_link
            ):
                with self.assertRaisesRegex(
                    self.run_module.ArtifactWriteError, "backward link blocked"
                ):
                    self.run_module.supersede_run(
                        old_run, new_run, *new_sources
                    )

            new_manifest = json.loads(
                (new_run / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(len(new_manifest_writes), 1)
            self.assertEqual(new_manifest["supersedes_run_id"], "old-run")
            self.assertEqual(new_manifest["supersedes_run_path"], str(old_run.resolve()))
            before_retry = {
                path.relative_to(new_run): path.read_bytes()
                for path in new_run.rglob("*")
                if path.is_file()
            }

            self.run_module.supersede_run(old_run, new_run, *new_sources)

            after_retry = {
                path.relative_to(new_run): path.read_bytes()
                for path in new_run.rglob("*")
                if path.is_file()
            }
            old_manifest = json.loads(
                (old_run / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(before_retry, after_retry)
            self.assertEqual(old_manifest["superseded_by"]["run_id"], "new-run")

    def test_validate_run_rejects_malformed_lifecycle_links(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources = self.write_sources(root / "sources")
            run_dir = root / "run"
            self.run_module.initialize_run(run_dir, *sources)
            manifest_path = run_dir / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["supersedes_run_id"] = "old-run"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            result = self.run_module.validate_run(run_dir)

        self.assertTrue(any("linkage" in error for error in result["errors"]))

    def test_supersede_refuses_to_reuse_an_existing_destination_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old_sources = self.write_sources(root / "old-sources")
            old_run = root / "old-run"
            self.run_module.initialize_run(old_run, *old_sources)
            new_sources = self.write_sources(
                root / "new-sources",
                input_change=lambda value: value["seed"].update(
                    {"value": "new visual-memory topic"}
                ),
            )
            occupied_run = root / "occupied-run"
            self.run_module.initialize_run(occupied_run, *new_sources)

            with self.assertRaisesRegex(ValueError, "conflicting|already contains"):
                self.run_module.supersede_run(
                    old_run, occupied_run, *new_sources
                )

    def test_supersede_cli_exposes_same_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old_sources = self.write_sources(root / "old-sources")
            old_run = root / "old-run"
            self.run_module.initialize_run(old_run, *old_sources)
            new_sources = self.write_sources(
                root / "new-sources",
                thesis="# New thesis\nBack visual-memory infrastructure.\n",
            )
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = self.run_module.main(
                    [
                        "supersede",
                        "--supersedes-run-dir", str(old_run),
                        "--run-dir", str(root / "new-run"),
                        "--input", str(new_sources[0]),
                        "--thesis", str(new_sources[1]),
                        "--rubric", str(new_sources[2]),
                    ]
                )

        self.assertEqual(code, 0, output.getvalue())
        self.assertEqual(json.loads(output.getvalue())["status"], "ok")

    def test_legacy_fixture_validation_remains_read_only(self):
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
        self.assertEqual(result["layout"], "legacy")
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
