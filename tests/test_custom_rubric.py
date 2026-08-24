import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN_SCRIPT = ROOT / "skills" / "investment-research-start" / "scripts" / "run.py"
LEGACY_RUBRIC_FIXTURE = ROOT / "tests" / "fixtures" / "flow-v2" / "rubric.json"
CUSTOM_RUBRIC_FIXTURE = ROOT / "tests" / "fixtures" / "flow-v2" / "smb-ai-agents-rubric.json"


def load_run():
    spec = importlib.util.spec_from_file_location("custom_rubric_run", RUN_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CustomRubricTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.run_module = load_run()

    def _write_thesis(self, root: Path) -> Path:
        thesis_path = root / "thesis.md"
        thesis_path.write_text(
            "# Investment thesis\n"
            "Back SMB AI agent startups with rapid workflow growth and market expansion.\n",
            encoding="utf-8",
        )
        return thesis_path

    def _write_input(self, root: Path) -> Path:
        input_path = root / "input.json"
        input_path.write_text(
            json.dumps({"seed": {"type": "topic", "value": "SMB AI agents"}}),
            encoding="utf-8",
        )
        return input_path

    def _write_rubric(self, root: Path, source: Path) -> Path:
        rubric = json.loads(source.read_text(encoding="utf-8"))
        thesis = (root / "thesis.md").read_text(encoding="utf-8")
        rubric["thesis_fingerprint"] = hashlib.sha256(thesis.encode("utf-8")).hexdigest()
        for category in rubric["categories"]:
            for score in category["anchors"]:
                category["anchors"][score] += f" Thesis context: {thesis}"
        path = root / "rubric.json"
        path.write_text(json.dumps(rubric), encoding="utf-8")
        return path

    def _make_run_dir_with_rubric(self, source: Path) -> Path:
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        input_path = self._write_input(root)
        thesis_path = self._write_thesis(root)
        rubric_path = self._write_rubric(root, source)
        run_dir = root / "run"
        self.run_module.initialize_run(run_dir, input_path, thesis_path, rubric_path)
        return run_dir

    def _analysis_text(self, rows: list[str], final_score: int = 100) -> str:
        return (
            "## Scorecard\n"
            "| Category | Score | Evidence refs | Reasoning |\n"
            "| --- | ---: | --- | --- |\n"
            + "\n".join(rows)
            + f"\n| **Final score** | **{final_score} / 100** | **Arithmetic total** | |\n\n"
            "## Recommendation\nTake a meeting\n\n"
            "## Risks and open questions\n- Verify remaining risks.\n"
        )

    def test_initialize_run_accepts_custom_rubric_names_and_weights(self):
        run_dir = self._make_run_dir_with_rubric(CUSTOM_RUBRIC_FIXTURE)
        stored_rubric = json.loads((run_dir / "rubric.json").read_text(encoding="utf-8"))

        self.assertEqual(
            [category["name"] for category in stored_rubric["categories"]],
            [
                "Growth potential and momentum",
                "Market size and expansion path",
                "Product differentiation and defensibility",
                "SMB problem intensity and adoption fit",
                "Execution risk and capital efficiency",
            ],
        )
        self.assertEqual(
            [category["weight"] for category in stored_rubric["categories"]],
            [30, 30, 20, 15, 5],
        )

    def test_parse_analysis_uses_configured_weights_and_evidence_areas(self):
        run_dir = self._make_run_dir_with_rubric(CUSTOM_RUBRIC_FIXTURE)
        errors: list[str] = []
        categories = self.run_module.load_rubric_categories(run_dir, errors)
        claims = {
            "traction-1": {
                "id": "traction-1",
                "area": "traction",
                "claim_type": "verified_fact",
                "source_url": "https://metrics.example/arr",
            },
            "market-1": {
                "id": "market-1",
                "area": "market",
                "claim_type": "verified_fact",
                "source_url": "https://market.example/report",
            },
            "product-1": {
                "id": "product-1",
                "area": "product",
                "claim_type": "verified_fact",
                "source_url": "https://product.example/diff",
            },
            "team-1": {
                "id": "team-1",
                "area": "team",
                "claim_type": "verified_fact",
                "source_url": "https://team.example/bio",
            },
        }
        coverage = {
            "team": "present",
            "product": "present",
            "market": "present",
            "traction": "present",
            "competitors": "present",
            "freshness": "present",
        }
        analysis_path = run_dir / "analysis.md"
        analysis_path.write_text(
            self._analysis_text(
                [
                    "| Growth potential and momentum | 30 | claim:traction-1 | Strong momentum. |",
                    "| Market size and expansion path | 30 | claim:market-1 | Large market. |",
                    "| Product differentiation and defensibility | 20 | claim:product-1 | Differentiated. |",
                    "| SMB problem intensity and adoption fit | 15 | claim:market-1, claim:product-1 | Strong fit. |",
                    "| Execution risk and capital efficiency | 5 | claim:team-1 | Efficient team. |",
                ]
            ),
            encoding="utf-8",
        )

        score, call = self.run_module._parse_analysis(
            analysis_path,
            errors,
            "Acme",
            claims,
            coverage,
            rubric_categories=categories,
            used_claim_ids=set(),
            company_website="https://acme.example",
        )

        self.assertEqual(errors, [])
        self.assertEqual(score, 100)
        self.assertEqual(call, "Take a meeting")

    def test_positive_score_requires_claim_in_a_configured_evidence_area(self):
        run_dir = self._make_run_dir_with_rubric(CUSTOM_RUBRIC_FIXTURE)
        errors: list[str] = []
        categories = self.run_module.load_rubric_categories(run_dir, errors)
        claims = {
            "product-1": {
                "id": "product-1",
                "area": "product",
                "claim_type": "verified_fact",
                "source_url": "https://product.example/diff",
            }
        }
        coverage = {
            "team": "present",
            "product": "present",
            "market": "present",
            "traction": "present",
            "competitors": "present",
            "freshness": "present",
        }
        analysis_path = run_dir / "analysis.md"
        analysis_path.write_text(
            self._analysis_text(
                [
                    "| Growth potential and momentum | 0 | gap:traction | Missing momentum. |",
                    "| Market size and expansion path | 5 | claim:product-1 | Wrong area. |",
                    "| Product differentiation and defensibility | 0 | gap:product | Missing product evidence. |",
                    "| SMB problem intensity and adoption fit | 0 | gap:market | Missing fit evidence. |",
                    "| Execution risk and capital efficiency | 0 | gap:team | Missing execution evidence. |",
                ],
                final_score=5,
            ),
            encoding="utf-8",
        )

        self.run_module._parse_analysis(
            analysis_path,
            errors,
            "Acme",
            claims,
            coverage,
            rubric_categories=categories,
            used_claim_ids=set(),
            company_website="https://acme.example",
        )

        self.assertTrue(any("market evidence" in error.lower() for error in errors), errors)

    def test_custom_company_claim_cap_is_applied_when_configured(self):
        run_dir = self._make_run_dir_with_rubric(CUSTOM_RUBRIC_FIXTURE)
        errors: list[str] = []
        categories = self.run_module.load_rubric_categories(run_dir, errors)
        claims = {
            "traction-1": {
                "id": "traction-1",
                "area": "traction",
                "claim_type": "company_claim",
                "source_url": "https://acme.example/metrics",
            }
        }
        coverage = {
            "team": "present",
            "product": "present",
            "market": "present",
            "traction": "present",
            "competitors": "present",
            "freshness": "present",
        }
        analysis_path = run_dir / "analysis.md"
        analysis_path.write_text(
            self._analysis_text(
                [
                    "| Growth potential and momentum | 11 | claim:traction-1 | Above cap. |",
                    "| Market size and expansion path | 0 | gap:market | Missing market evidence. |",
                    "| Product differentiation and defensibility | 0 | gap:product | Missing product evidence. |",
                    "| SMB problem intensity and adoption fit | 0 | gap:market | Missing fit evidence. |",
                    "| Execution risk and capital efficiency | 0 | gap:team | Missing execution evidence. |",
                ],
                final_score=11,
            ),
            encoding="utf-8",
        )

        self.run_module._parse_analysis(
            analysis_path,
            errors,
            "Acme",
            claims,
            coverage,
            rubric_categories=categories,
            used_claim_ids=set(),
            company_website="https://acme.example",
        )

        self.assertTrue(any("capped at 10" in error.lower() for error in errors), errors)

    def test_legacy_rubric_fixture_still_loads_default_mappings(self):
        run_dir = self._make_run_dir_with_rubric(LEGACY_RUBRIC_FIXTURE)
        errors: list[str] = []

        categories = self.run_module.load_rubric_categories(run_dir, errors)

        self.assertEqual(errors, [])
        self.assertEqual(
            categories,
            [
                {
                    "name": "Team",
                    "weight": 20,
                    "evidence_areas": ["team"],
                    "company_claim_cap": 10,
                },
                {
                    "name": "Product differentiation",
                    "weight": 20,
                    "evidence_areas": ["product"],
                    "company_claim_cap": None,
                },
                {
                    "name": "Market",
                    "weight": 20,
                    "evidence_areas": ["market"],
                    "company_claim_cap": 10,
                },
                {
                    "name": "Traction",
                    "weight": 20,
                    "evidence_areas": ["traction"],
                    "company_claim_cap": 10,
                },
                {
                    "name": "Thesis alignment",
                    "weight": 20,
                    "evidence_areas": ["product"],
                    "company_claim_cap": None,
                },
            ],
        )


if __name__ == "__main__":
    unittest.main()
