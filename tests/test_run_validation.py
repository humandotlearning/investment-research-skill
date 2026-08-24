import importlib.util
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "investment-research-start" / "scripts" / "run.py"
RUBRIC_FIXTURE = ROOT / "tests" / "fixtures" / "assignment-v2" / "rubric.json"


def load_run():
    spec = importlib.util.spec_from_file_location("validation_run", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_rubric(path, thesis_path):
    rubric = json.loads(RUBRIC_FIXTURE.read_text(encoding="utf-8"))
    thesis = thesis_path.read_text(encoding="utf-8")
    rubric["thesis_fingerprint"] = hashlib.sha256(thesis.encode("utf-8")).hexdigest()
    for category in rubric["categories"]:
        for score in category["anchors"]:
            category["anchors"][score] += f" Thesis context: {thesis}"
    path.write_text(json.dumps(rubric), encoding="utf-8")
    return path


class NewRunValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.run_module = load_run()

    def make_run(self, root):
        source_input, source_thesis = root / "source.json", root / "source.md"
        source_input.write_text(json.dumps({"seed": {"type": "topic", "value": "AI"}}), encoding="utf-8")
        source_thesis.write_text("# Thesis\nRecurring work.\n", encoding="utf-8")
        source_rubric = write_rubric(root / "rubric.json", source_thesis)
        run_dir = root / "run"
        self.run_module.initialize_run(run_dir, source_input, source_thesis, source_rubric)
        sourcing = run_dir / "sourcing"
        sourcing.mkdir(parents=True, exist_ok=True)
        candidate_specs = [("Acme", "acme", "https://acme.example")] + [
            (f"Company {index}", f"company-{index}", f"https://company{index}.example")
            for index in range(2, 11)
        ]
        candidates_list = []
        retrieval_results = []
        for rank, (name, slug, website) in enumerate(candidate_specs, start=1):
            origin_url = f"https://www.ycombinator.com/companies/{slug}"
            candidates_list.append({
                "name": name,
                "slug": slug,
                "website": website,
                "one_line_description": "Automation.",
                "origins": [{
                    "source": "yc",
                    "canonical_url": origin_url,
                    "source_id": f"yc-{rank}",
                    "publication_or_batch_date": "S24",
                }],
                "team_signal": None,
                "freshness_or_traction_signals": [{
                    "kind": "freshness", "source_url": origin_url, "date": "S24",
                }],
                "thesis_fit_reasons": ["Recurring workflow fit."],
                "rank": rank,
                "description": "Automation.",
                "source_urls": [origin_url],
                "candidate_type": "priority",
                "fit_reasons": ["Workflow"],
                "research_priority": rank,
                "source_quality": "primary_record",
                "selected_for_research": True,
            })
            retrieval_results.append({
                "title": name,
                "candidate_name": name,
                "candidate_slug": slug,
                "candidate_website": website,
                "source": "yc",
                "source_id": f"yc-{rank}",
                "url": origin_url,
                "published_date": "S24",
                "highlights": ["signal"],
            })
        retrieval = {"query":"Acme","provider":"source_snapshots","retrieved_at":"2026-08-23T00:00:00Z","status":"ok","exit_code":0,"results":retrieval_results}
        (sourcing / "retrieval.json").write_text(json.dumps(retrieval), encoding="utf-8")
        candidates = {"version":2,"provider":"source_snapshots","query":"Acme","retrieval_path":"sourcing/retrieval.json","requested_count":10,"actual_count":10,"candidates":candidates_list,"excluded":[]}
        (sourcing / "candidates.json").write_text(json.dumps(candidates), encoding="utf-8")
        summary_rows = []
        gap_rows = []
        for name, slug, website in candidate_specs:
            company = run_dir / "companies" / slug
            company.mkdir(parents=True, exist_ok=True)
            company_retrieval = {"query":name,"provider":"web","retrieved_at":"2026-08-23T00:00:00Z","status":"ok","exit_code":0,"results":[{"title":name,"url":website,"published_date":None,"highlights":["signal"]}]}
            (company / "retrieval-initial.json").write_text(json.dumps(company_retrieval), encoding="utf-8")
            areas = ["team", "product", "market", "traction"]
            evidence = {
                "version": 2,
                "company": {"name":name,"slug":slug,"website":website},
                "coverage": {"team":"present","product":"present","market":"present","traction":"present","competitors":"missing","freshness":"missing"},
                "missing_categories": ["competitors", "freshness"],
                "retrievals": [{"artifact_path":f"companies/{slug}/retrieval-initial.json","provider":"web","query":name,"retrieved_at":"2026-08-23T00:00:00Z","status":"ok","exit_code":0}],
                "claims": [{"id":f"{area}-1","area":area,"claim":f"{area} signal","claim_type":"company_claim","source_url":website,"source_quality":"first_party","confidence":"medium"} for area in areas],
                "unresolved_gaps": ["competitors", "freshness"],
            }
            (company / "evidence.json").write_text(json.dumps(evidence), encoding="utf-8")
            rows = "\n".join([
                "| Team | 10 | claim:team-1 | Evidence. |",
                "| Product differentiation | 10 | claim:product-1 | Evidence. |",
                "| Market | 10 | claim:market-1 | Evidence. |",
                "| Traction | 10 | claim:traction-1 | Evidence. |",
                "| Thesis alignment | 10 | claim:product-1, claim:market-1 | Evidence. |",
            ])
            analysis = f"## Scorecard\n| Category | Score / 20 | Evidence refs | Reasoning |\n| --- | ---: | --- | --- |\n{rows}\n| **Final score** | **50 / 100** | **Arithmetic total** | |\n\n## Recommendation\nPass\n\n## Risks and open questions\n- Verify company claims.\n"
            (company / "analysis.md").write_text(analysis, encoding="utf-8")
            (company / "memo.md").write_text("## Recommendation\n**Pass**\n\n## Score\n**50 / 100**\n", encoding="utf-8")
            summary_rows.append(f"| {name} | 50 | Pass |")
            gap_rows.append(f"{name}: competitors, freshness")
        (run_dir / "run-summary.md").write_text(
            "## Decisions\n| Company | Score | Recommendation |\n| --- | ---: | --- |\n"
            + "\n".join(summary_rows) + "\n\n"
            "## Skipped candidates\nNone.\n\n"
            "## Unresolved gaps\n" + "\n".join(gap_rows) + "\n\n"
            "## Retries\nNone.\n\n"
            "## Failures\nNone.\n",
            encoding="utf-8",
        )
        self.run_module.update_stage(run_dir, "sourcing", "completed", provider="source_snapshots", exit_code=0, artifacts=["sourcing/retrieval.json", "sourcing/candidates.json"])
        for _, slug, _ in candidate_specs:
            for stage, artifact in [("research","evidence.json"),("analysis","analysis.md"),("memo","memo.md")]:
                self.run_module.update_stage(
                    run_dir,
                    stage,
                    "completed",
                    company=slug,
                    provider="web" if stage == "research" else None,
                    exit_code=0 if stage == "research" else None,
                    artifacts=[f"companies/{slug}/{artifact}"],
                )
        return run_dir

    def test_complete_new_run_is_valid(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_module.validate_run(self.make_run(Path(directory)))
        self.assertTrue(result["valid"], result["errors"])

    def test_duplicate_stale_claim_invalid_enum_gap_score_and_memo_drift_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = self.make_run(Path(directory))
            candidates_path = run_dir / "sourcing" / "candidates.json"
            candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
            candidates["candidates"].append({**candidates["candidates"][0], "name":"Duplicate"})
            candidates["actual_count"] = 2
            candidates_path.write_text(json.dumps(candidates), encoding="utf-8")
            evidence_path = run_dir / "companies" / "acme" / "evidence.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence["coverage"]["traction"] = "mixed"
            evidence["claims"][0].update({"claim_type":"rumor", "source_url":"https://stale.example"})
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
            analysis_path = run_dir / "companies" / "acme" / "analysis.md"
            analysis_path.write_text(analysis_path.read_text(encoding="utf-8").replace("claim:traction-1", "gap:traction"), encoding="utf-8")
            memo_path = run_dir / "companies" / "acme" / "memo.md"
            memo_path.write_text(memo_path.read_text(encoding="utf-8").replace("**Pass**", "**Watch**"), encoding="utf-8")
            result = self.run_module.validate_run(run_dir)
        errors = "\n".join(result["errors"])
        for phrase in ["duplicate", "not present in retrieval", "mixed", "rumor", "gap-only", "memo recommendation mismatch"]:
            self.assertIn(phrase, errors.lower())

    def test_rejects_incomplete_triage_unbounded_retrievals_and_extra_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = self.make_run(Path(directory))
            candidates_path = run_dir / "sourcing" / "candidates.json"
            candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
            candidates.pop("query")
            candidates["candidates"][0].pop("research_priority")
            candidates["excluded"] = [{"name": "Nope", "candidate_type": "priority"}]
            candidates_path.write_text(json.dumps(candidates), encoding="utf-8")

            retrieval_path = run_dir / "companies" / "acme" / "retrieval-initial.json"
            retrieval = json.loads(retrieval_path.read_text(encoding="utf-8"))
            retrieval["results"] = retrieval["results"] * 6
            retrieval_path.write_text(json.dumps(retrieval), encoding="utf-8")

            evidence_path = run_dir / "companies" / "acme" / "evidence.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence["retrievals"] = evidence["retrievals"] * 3
            evidence["unresolved_gaps"] = []
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
            result = self.run_module.validate_run(run_dir)

        errors = "\n".join(result["errors"]).lower()
        for phrase in [
            "candidates missing query",
            "research_priority",
            "invalid exclusion",
            "more than one targeted retry",
            "more than 5 results",
            "duplicate retrieval url",
            "unresolved_gaps",
        ]:
            self.assertIn(phrase, errors)

    def test_requires_summary_even_when_no_candidate_is_selected(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = self.make_run(Path(directory))
            candidates_path = run_dir / "sourcing" / "candidates.json"
            candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
            candidates["candidates"][0]["selected_for_research"] = False
            candidates_path.write_text(json.dumps(candidates), encoding="utf-8")
            (run_dir / "run-summary.md").unlink()
            result = self.run_module.validate_run(run_dir)

        self.assertTrue(any("missing run-summary" in error for error in result["errors"]))
        self.assertTrue(any("full coverage" in error for error in result["errors"]))

    def test_score_row_requires_an_evidence_or_gap_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = self.make_run(Path(directory))
            analysis_path = run_dir / "companies" / "acme" / "analysis.md"
            analysis_path.write_text(
                analysis_path.read_text(encoding="utf-8").replace(
                    "| Team | 10 | claim:team-1 |", "| Team | 10 |  |"
                ),
                encoding="utf-8",
            )
            result = self.run_module.validate_run(run_dir)

        self.assertTrue(any("requires an evidence reference" in error for error in result["errors"]))

    def test_manifest_rejects_stale_completed_artifacts_and_excess_research_attempts(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = self.make_run(Path(directory))
            manifest_path = run_dir / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["companies"]["acme"]["analysis"]["artifacts"] = ["companies/acme/stale.md"]
            manifest["companies"]["acme"]["analysis"]["provider"] = "other"
            manifest["companies"]["acme"]["research"]["attempt_count"] = 3
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            result = self.run_module.validate_run(run_dir)

        errors = "\n".join(result["errors"]).lower()
        self.assertIn("manifest artifact", errors)
        self.assertIn("manifest provider", errors)
        self.assertIn("research attempts", errors)

    def test_validator_rejects_input_thesis_fingerprint_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = self.make_run(Path(directory))
            (run_dir / "thesis.md").write_text("# Changed thesis\n", encoding="utf-8")
            result = self.run_module.validate_run(run_dir)

        self.assertTrue(any("fingerprint" in error for error in result["errors"]))

    def test_v2_manifest_cannot_downgrade_to_legacy_with_list_candidates(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = self.make_run(Path(directory))
            candidates_path = run_dir / "sourcing" / "candidates.json"
            candidates_path.write_text('[{"name":"Legacy shape"}]\n', encoding="utf-8")

            result = self.run_module.validate_run(run_dir)

        self.assertEqual(result["layout"], "current")
        self.assertFalse(result["valid"])
        self.assertTrue(any("candidates.json must be an object" in error for error in result["errors"]))

    def test_manifest_parse_or_version_drift_is_current_not_legacy(self):
        for mutation in ("missing", "wrong", "malformed"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                run_dir = self.make_run(Path(directory))
                (run_dir / "sourcing" / "candidates.json").write_text(
                    '[{"name":"Legacy shape"}]\n', encoding="utf-8"
                )
                manifest_path = run_dir / "manifest.json"
                if mutation == "malformed":
                    manifest_path.write_text("{", encoding="utf-8")
                else:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    if mutation == "missing":
                        manifest.pop("version")
                    else:
                        manifest["version"] = 1
                    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

                result = self.run_module.validate_run(run_dir)

                self.assertEqual(result["layout"], "current")
                self.assertFalse(result["valid"])
                self.assertTrue(
                    any("manifest" in error.lower() for error in result["errors"]),
                    result["errors"],
                )

    def test_malformed_nested_shapes_become_validation_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = self.make_run(Path(directory))
            evidence_path = run_dir / "companies" / "acme" / "evidence.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence["coverage"] = []
            evidence["retrievals"][0]["artifact_path"] = ["not", "a", "path"]
            evidence["claims"][0]["id"] = {"bad": "id"}
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

            result = self.run_module.validate_run(run_dir)

        self.assertFalse(result["valid"])
        self.assertGreater(len(result["errors"]), 0)

    def test_candidate_slug_cannot_escape_company_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = self.make_run(Path(directory))
            candidates_path = run_dir / "sourcing" / "candidates.json"
            candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
            candidates["candidates"][0]["slug"] = "../../outside"
            candidates_path.write_text(json.dumps(candidates), encoding="utf-8")

            result = self.run_module.validate_run(run_dir)

        self.assertTrue(any("invalid candidate slug" in error for error in result["errors"]))

    def test_score_cannot_use_another_area_when_category_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = self.make_run(Path(directory))
            evidence_path = run_dir / "companies" / "acme" / "evidence.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence["coverage"]["team"] = "missing"
            evidence["missing_categories"] = ["team", "competitors"]
            evidence["unresolved_gaps"] = ["team", "competitors"]
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
            analysis_path = run_dir / "companies" / "acme" / "analysis.md"
            analysis_path.write_text(
                analysis_path.read_text(encoding="utf-8").replace(
                    "claim:team-1", "claim:product-1"
                ),
                encoding="utf-8",
            )

            result = self.run_module.validate_run(run_dir)

        self.assertTrue(any("team evidence" in error for error in result["errors"]))

    def test_positive_score_is_rejected_when_coverage_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = self.make_run(Path(directory))
            evidence_path = run_dir / "companies" / "acme" / "evidence.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence["coverage"]["team"] = "missing"
            evidence["missing_categories"] = ["team", "competitors"]
            evidence["unresolved_gaps"] = ["team", "competitors"]
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

            result = self.run_module.validate_run(run_dir)

        self.assertTrue(any("team coverage is missing" in error for error in result["errors"]))

    def test_retrieval_status_and_provenance_must_match_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = self.make_run(Path(directory))
            candidates_path = run_dir / "sourcing" / "candidates.json"
            candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
            candidates["query"] = "stale query"
            candidates_path.write_text(json.dumps(candidates), encoding="utf-8")
            retrieval_path = run_dir / "companies" / "acme" / "retrieval-initial.json"
            retrieval = json.loads(retrieval_path.read_text(encoding="utf-8"))
            retrieval.update({"status": "failed", "exit_code": 0})
            retrieval_path.write_text(json.dumps(retrieval), encoding="utf-8")
            evidence_path = run_dir / "companies" / "acme" / "evidence.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence["retrievals"][0]["provider"] = "web"
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

            result = self.run_module.validate_run(run_dir)

        errors = "\n".join(result["errors"]).lower()
        self.assertIn("sourcing query does not match", errors)
        self.assertIn("failed retrieval must have a nonzero exit code", errors)
        self.assertIn("provenance does not match", errors)

    def test_run_summary_requires_all_operational_sections(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = self.make_run(Path(directory))
            summary_path = run_dir / "run-summary.md"
            summary_path.write_text("## Decisions\n| Acme | 50 | Pass |\n", encoding="utf-8")

            result = self.run_module.validate_run(run_dir)

        errors = "\n".join(result["errors"]).lower()
        for heading in ["skipped candidates", "unresolved gaps", "retries", "failures"]:
            self.assertIn(heading, errors)

    def test_retry_requires_recorded_complete_initial_missing_list(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = self.make_run(Path(directory))
            company = run_dir / "companies" / "acme"
            retry = json.loads((company / "retrieval-initial.json").read_text(encoding="utf-8"))
            retry["missing_categories"] = ["team", "competitors"]
            (company / "retrieval-retry.json").write_text(json.dumps(retry), encoding="utf-8")
            evidence_path = company / "evidence.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence["retrievals"].append(
                {
                    "artifact_path": "companies/acme/retrieval-retry.json",
                    "provider": "exa",
                    "query": "Acme",
                    "retrieved_at": "2026-08-23T00:00:00Z",
                    "status": "ok",
                    "exit_code": 0,
                    "missing_categories": ["team", "competitors"],
                }
            )
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
            result = self.run_module.validate_run(run_dir)

        self.assertTrue(any("initial_missing_categories" in error for error in result["errors"]))

    def test_run_summary_must_name_skipped_comparables(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = self.make_run(Path(directory))
            retrieval_path = run_dir / "sourcing" / "retrieval.json"
            retrieval = json.loads(retrieval_path.read_text(encoding="utf-8"))
            retrieval["results"].append(
                {"title": "Beta", "url": "https://beta.example", "published_date": None, "highlights": []}
            )
            retrieval_path.write_text(json.dumps(retrieval), encoding="utf-8")
            candidates_path = run_dir / "sourcing" / "candidates.json"
            candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
            beta = {
                **candidates["candidates"][0],
                "name": "Beta",
                "slug": "beta",
                "website": "https://beta.example",
                "source_urls": ["https://beta.example"],
                "candidate_type": "comparable",
                "research_priority": 2,
                "selected_for_research": False,
            }
            candidates["candidates"].append(beta)
            candidates["actual_count"] = 2
            candidates_path.write_text(json.dumps(candidates), encoding="utf-8")

            result = self.run_module.validate_run(run_dir)

        self.assertTrue(any("missing skipped candidate: Beta" in error for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()
