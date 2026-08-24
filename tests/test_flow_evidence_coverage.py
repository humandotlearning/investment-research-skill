import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN_SCRIPT = ROOT / "skills" / "investment-research-start" / "scripts" / "run.py"
RUBRIC_FIXTURE = ROOT / "tests" / "fixtures" / "flow-v2" / "rubric.json"


def load_run():
    spec = importlib.util.spec_from_file_location("flow_coverage_run", RUN_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FlowEvidenceCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.run_module = load_run()

    def _write_flow(self, root: Path):
        input_path = root / "source-input.json"
        thesis_path = root / "source-thesis.md"
        rubric_path = root / "source-rubric.json"
        input_path.write_text(
            json.dumps({"seed": {"type": "topic", "value": "AI workflow software"}}),
            encoding="utf-8",
        )
        thesis = "# Thesis\nBack AI workflow software for investment teams.\n"
        thesis_path.write_text(thesis, encoding="utf-8")
        rubric = json.loads(RUBRIC_FIXTURE.read_text(encoding="utf-8"))
        rubric["thesis_fingerprint"] = hashlib.sha256(thesis.encode("utf-8")).hexdigest()
        for category in rubric["categories"]:
            for anchor in category["anchors"]:
                category["anchors"][anchor] += " AI workflow software."
        rubric_path.write_text(json.dumps(rubric), encoding="utf-8")
        return input_path, thesis_path, rubric_path

    def _origin(self, index: int, source: str = "yc"):
        if source == "product_hunt":
            return {
                "source": source,
                "canonical_url": f"https://www.producthunt.com/posts/company-{index}",
                "source_id": f"ph-{index}",
                "publication_or_batch_date": "2026-08-20T00:00:00Z",
            }
        return {
            "source": source,
            "canonical_url": f"https://www.ycombinator.com/companies/company-{index}",
            "source_id": f"yc-{index}",
            "publication_or_batch_date": "S24",
        }

    def _candidate(self, index: int):
        origins = [self._origin(index)]
        if index == 1:
            origins.append(self._origin(index, "product_hunt"))
        return {
            "name": f"Company {index}",
            "slug": f"company-{index}",
            "website": f"https://company{index}.example",
            "one_line_description": f"Company {index} automates investment workflows.",
            "origins": origins,
            "team_signal": None,
            "freshness_or_traction_signals": [
                {
                    "kind": "freshness",
                    "source_url": origin["canonical_url"],
                    "date": origin["publication_or_batch_date"],
                }
                for origin in origins
            ],
            "thesis_fit_reasons": ["Automates a workflow named in the thesis."],
            "rank": index,
            "description": f"Company {index} automates investment workflows.",
            "candidate_type": "priority",
            "fit_reasons": ["Automates a workflow named in the thesis."],
            "research_priority": index,
            "source_quality": "primary_record",
            "source_urls": [origin["canonical_url"] for origin in origins],
            "selected_for_research": True,
        }

    def _write_sourcing(self, run_dir: Path, count: int, excluded=None):
        sourcing_dir = run_dir / "sourcing"
        sourcing_dir.mkdir(parents=True, exist_ok=True)
        candidates = [self._candidate(index) for index in range(1, count + 1)]
        retrieval = {
            "query": "Official Product Hunt and YC snapshots",
            "provider": "source_snapshots",
            "retrieved_at": "2026-08-23T00:00:00Z",
            "status": "ok",
            "exit_code": 0,
            "results": [
                {
                    "title": candidate["name"],
                    "candidate_name": candidate["name"],
                    "candidate_slug": candidate["slug"],
                    "candidate_website": candidate["website"],
                    "url": origin["canonical_url"],
                    "source": origin["source"],
                    "source_id": origin["source_id"],
                    "published_date": origin["publication_or_batch_date"],
                    "highlights": [candidate["one_line_description"]],
                }
                for candidate in candidates
                for origin in candidate["origins"]
            ],
        }
        payload = {
            "provider": "source_snapshots",
            "query": retrieval["query"],
            "retrieval_path": "sourcing/retrieval.json",
            "requested_count": 10,
            "actual_count": len(candidates),
            "candidates": candidates,
            "excluded": list(excluded or []),
        }
        (sourcing_dir / "retrieval.json").write_text(json.dumps(retrieval), encoding="utf-8")
        (sourcing_dir / "candidates.json").write_text(json.dumps(payload), encoding="utf-8")
        return payload

    def _completed_record(self, artifacts, *, provider=None, exit_code=None):
        return {
            "status": "completed",
            "attempt_count": 1,
            "provider": provider,
            "exit_code": exit_code,
            "error": None,
            "artifacts": artifacts,
            "completed_at": "2026-08-23T00:00:00Z",
        }

    def make_complete_run(self, root: Path):
        run_dir = root / "run"
        self.run_module.initialize_run(run_dir, *self._write_flow(root))
        sourcing = self._write_sourcing(run_dir, 10)
        self.run_module.update_stage(
            run_dir,
            "sourcing",
            "completed",
            provider="source_snapshots",
            exit_code=0,
            artifacts=["sourcing/retrieval.json", "sourcing/candidates.json"],
        )
        summary_rows = []
        gap_rows = []
        manifest_path = run_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for candidate in sourcing["candidates"]:
            name, slug, website = candidate["name"], candidate["slug"], candidate["website"]
            company_dir = run_dir / "companies" / slug
            company_dir.mkdir(parents=True, exist_ok=True)
            retrieval = {
                "query": name,
                "provider": "web",
                "retrieved_at": "2026-08-23T00:00:00Z",
                "status": "ok",
                "exit_code": 0,
                "results": [
                    {
                        "title": name,
                        "url": website,
                        "published_date": None,
                        "highlights": ["Official company evidence."],
                    }
                ],
            }
            (company_dir / "retrieval-initial.json").write_text(
                json.dumps(retrieval), encoding="utf-8"
            )
            claims = [
                {
                    "id": f"{area}-1",
                    "area": area,
                    "claim": f"{name} reports a {area} signal.",
                    "claim_type": "company_claim",
                    "source_url": website,
                    "source_quality": "first_party",
                    "confidence": "medium",
                }
                for area in ("team", "product", "market", "traction")
            ]
            evidence = {
                "version": 2,
                "company": {"name": name, "slug": slug, "website": website},
                "coverage": {
                    "team": "present",
                    "product": "present",
                    "market": "present",
                    "traction": "present",
                    "competitors": "missing",
                    "freshness": "missing",
                },
                "missing_categories": ["competitors", "freshness"],
                "retrievals": [
                    {
                        "artifact_path": f"companies/{slug}/retrieval-initial.json",
                        "provider": "web",
                        "query": name,
                        "retrieved_at": "2026-08-23T00:00:00Z",
                        "status": "ok",
                        "exit_code": 0,
                    }
                ],
                "claims": claims,
                "unresolved_gaps": ["competitors", "freshness"],
            }
            (company_dir / "evidence.json").write_text(json.dumps(evidence), encoding="utf-8")
            analysis = (
                "## Scorecard\n"
                "| Category | Score / 20 | Evidence refs | Reasoning |\n"
                "| --- | ---: | --- | --- |\n"
                "| Team | 10 | claim:team-1 | Evidence. |\n"
                "| Product differentiation | 10 | claim:product-1 | Evidence. |\n"
                "| Market | 10 | claim:market-1 | Evidence. |\n"
                "| Traction | 10 | claim:traction-1 | Evidence. |\n"
                "| Thesis alignment | 10 | claim:product-1, claim:market-1 | Evidence. |\n"
                "| **Final score** | **50 / 100** | **Arithmetic total** | |\n\n"
                "## Evidence-backed narrative\n"
                f"- {name} reports $2M ARR. [refs: traction-1]\n"
                f"- {name} reports 90% retention. [refs: traction-1]\n\n"
                "## Recommendation\nPass\n\n"
                "## Risks and open questions\n- Company-reported evidence needs confirmation.\n"
            )
            (company_dir / "analysis.md").write_text(analysis, encoding="utf-8")
            (company_dir / "memo.md").write_text(
                "## Recommendation\n**Pass**\n\n## Score\n**50 / 100**\n",
                encoding="utf-8",
            )
            manifest["companies"][slug] = {
                "research": self._completed_record(
                    [f"companies/{slug}/evidence.json"], provider="web", exit_code=0
                ),
                "analysis": self._completed_record([f"companies/{slug}/analysis.md"]),
                "memo": self._completed_record([f"companies/{slug}/memo.md"]),
            }
            summary_rows.append(f"| {name} | 50 | Pass |")
            gap_rows.append(f"{name}: competitors, freshness")
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        (run_dir / "run-summary.md").write_text(
            "## Decisions\n| Company | Score | Recommendation |\n| --- | ---: | --- |\n"
            + "\n".join(summary_rows)
            + "\n\n## Skipped candidates\nNone.\n\n## Unresolved gaps\n"
            + "\n".join(gap_rows)
            + "\n\n## Retries\nNone.\n\n## Failures\nNone.\n",
            encoding="utf-8",
        )
        return run_dir

    def _validate_errors(self, run_dir: Path):
        return "\n".join(self.run_module.validate_run(run_dir)["errors"]).lower()

    def _rewrite_input_contract(self, run_dir: Path, change):
        input_path = run_dir / "input.json"
        manifest_path = run_dir / "manifest.json"
        input_data = json.loads(input_path.read_text(encoding="utf-8"))
        change(input_data)
        input_path.write_text(json.dumps(input_data), encoding="utf-8")
        thesis = (run_dir / "thesis.md").read_text(encoding="utf-8")
        rubric = json.loads((run_dir / "rubric.json").read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["input_fingerprint"] = self.run_module.FLOW_V2.input_fingerprint(
            input_data, thesis
        )
        manifest["flow_fingerprint"] = self.run_module.FLOW_V2.flow_fingerprint(
            input_data, thesis, rubric
        )
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    def _set_claim_source(self, run_dir: Path, claim_id: str, source_url: str, *, claim_type=None):
        company_dir = run_dir / "companies" / "company-1"
        evidence_path = company_dir / "evidence.json"
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        claim = next(claim for claim in evidence["claims"] if claim["id"] == claim_id)
        claim["source_url"] = source_url
        if claim_type is not None:
            claim["claim_type"] = claim_type
        evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
        retrieval_path = company_dir / "retrieval-initial.json"
        retrieval = json.loads(retrieval_path.read_text(encoding="utf-8"))
        retrieval["results"].append(
            {"title": "Supporting source", "url": source_url, "published_date": None, "highlights": []}
        )
        retrieval_path.write_text(json.dumps(retrieval), encoding="utf-8")

    def test_three_candidates_cannot_complete_sourcing_and_must_be_partial(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = root / "run"
            self.run_module.initialize_run(run_dir, *self._write_flow(root))
            self._write_sourcing(run_dir, 3)

            with self.assertRaisesRegex(ValueError, "10.*20|fewer than 10"):
                self.run_module.update_stage(
                    run_dir,
                    "sourcing",
                    "completed",
                    provider="source_snapshots",
                    exit_code=0,
                    artifacts=["sourcing/retrieval.json", "sourcing/candidates.json"],
                )
            manifest = self.run_module.update_stage(
                run_dir,
                "sourcing",
                "partial",
                provider="source_snapshots",
                exit_code=0,
                artifacts=["sourcing/retrieval.json", "sourcing/candidates.json"],
            )

        self.assertEqual(manifest["stages"]["sourcing"]["status"], "partial")

    def test_sourcing_completion_requires_flow_target_count_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = root / "run"
            self.run_module.initialize_run(run_dir, *self._write_flow(root))
            self._write_sourcing(run_dir, 10)
            path = run_dir / "sourcing" / "candidates.json"
            candidates = json.loads(path.read_text(encoding="utf-8"))
            candidates["requested_count"] = 12
            path.write_text(json.dumps(candidates), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "requested_count"):
                self.run_module.update_stage(
                    run_dir,
                    "sourcing",
                    "completed",
                    provider="source_snapshots",
                    exit_code=0,
                    artifacts=["sourcing/retrieval.json", "sourcing/candidates.json"],
                )

    def test_flow_rejects_partial_research_modes_at_normalization_and_init(self):
        invalid_research = (
            {"full_coverage": False},
            {"full_coverage": None},
            {"full_coverage": "true"},
            {"full_coverage": True, "limit": 10},
            {"full_coverage": True, "limit": False},
            {"full_coverage": True, "limit": None},
            {"full_coverage": True, "limit": {}},
        )
        for index, research in enumerate(invalid_research):
            with self.subTest(research=research), self.assertRaisesRegex(
                ValueError, "full_coverage|limit"
            ):
                self.run_module.normalize_input(
                    {"seed": {"type": "topic", "value": "AI"}, "research": research}
                )

            with self.subTest(init_research=research), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                input_path, thesis_path, rubric_path = self._write_flow(root)
                input_data = json.loads(input_path.read_text(encoding="utf-8"))
                input_data["research"] = research
                input_path.write_text(json.dumps(input_data), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "full_coverage|limit"):
                    self.run_module.initialize_run(
                        root / f"run-{index}", input_path, thesis_path, rubric_path
                    )

        for wrong_shape in (None, [], "all"):
            with self.subTest(research_shape=wrong_shape), self.assertRaisesRegex(
                ValueError, "research"
            ):
                self.run_module.normalize_input(
                    {"seed": {"type": "topic", "value": "AI"}, "research": wrong_shape}
                )

    def test_validation_rejects_false_full_coverage_and_synthesized_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = self.make_complete_run(Path(directory))
            candidates_path = run_dir / "sourcing" / "candidates.json"
            candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
            for candidate in candidates["candidates"][8:]:
                candidate["selected_for_research"] = False
                company_dir = run_dir / "companies" / candidate["slug"]
                for artifact in company_dir.iterdir():
                    artifact.unlink()
                company_dir.rmdir()
            candidates_path.write_text(json.dumps(candidates), encoding="utf-8")
            manifest_path = run_dir / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["companies"].pop("company-9")
            manifest["companies"].pop("company-10")
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            summary_path = run_dir / "run-summary.md"
            summary_path.write_text(
                summary_path.read_text(encoding="utf-8").replace(
                    "## Skipped candidates\nNone.",
                    "## Skipped candidates\nCompany 9\nCompany 10",
                ),
                encoding="utf-8",
            )
            self._rewrite_input_contract(
                run_dir,
                lambda value: value.update(
                    {"research": {"full_coverage": False, "limit": 8}}
                ),
            )

            result = self.run_module.validate_run(run_dir)

        self.assertFalse(result["valid"], result)
        self.assertTrue(any("full_coverage" in error or "limit" in error for error in result["errors"]))
        self.assertTrue(any("company 9" in error.lower() for error in result["errors"]))

        with tempfile.TemporaryDirectory() as directory:
            run_dir = self.make_complete_run(Path(directory))
            self._rewrite_input_contract(
                run_dir,
                lambda value: value.update(
                    {"research": {"full_coverage": True, "limit": 10}}
                ),
            )

            result = self.run_module.validate_run(run_dir)

        self.assertFalse(result["valid"], result)
        self.assertTrue(any("limit" in error for error in result["errors"]))

    def test_generic_company_page_and_hacker_news_cannot_be_origins(self):
        mutations = (
            ("web", "https://company1.example/about", "product hunt or yc"),
            ("hacker_news", "https://news.ycombinator.com/item?id=1", "product hunt or yc"),
        )
        for source, url, phrase in mutations:
            with self.subTest(source=source), tempfile.TemporaryDirectory() as directory:
                run_dir = self.make_complete_run(Path(directory))
                path = run_dir / "sourcing" / "candidates.json"
                value = json.loads(path.read_text(encoding="utf-8"))
                value["candidates"][0]["origins"] = [
                    {
                        "source": source,
                        "canonical_url": url,
                        "source_id": "invented",
                        "publication_or_batch_date": "2026-08-20",
                    }
                ]
                path.write_text(json.dumps(value), encoding="utf-8")

                errors = self._validate_errors(run_dir)

            self.assertIn(phrase, errors)

    def test_origins_are_record_specific_and_bound_to_sourcing_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = self.make_complete_run(Path(directory))
            candidates_path = run_dir / "sourcing" / "candidates.json"
            candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
            candidate = candidates["candidates"][0]
            origin = candidate["origins"][0]
            old_url = origin["canonical_url"]
            bad_url = "https://www.ycombinator.com/blog/company-1"
            origin["canonical_url"] = bad_url
            candidate["source_urls"] = [
                bad_url if url == old_url else url for url in candidate["source_urls"]
            ]
            for signal in candidate["freshness_or_traction_signals"]:
                if signal["source_url"] == old_url:
                    signal["source_url"] = bad_url
            candidates_path.write_text(json.dumps(candidates), encoding="utf-8")
            retrieval_path = run_dir / "sourcing" / "retrieval.json"
            retrieval = json.loads(retrieval_path.read_text(encoding="utf-8"))
            result_record = next(result for result in retrieval["results"] if result["url"] == old_url)
            result_record["url"] = bad_url
            retrieval_path.write_text(json.dumps(retrieval), encoding="utf-8")

            result = self.run_module.validate_run(run_dir)

        self.assertFalse(result["valid"], result)
        self.assertTrue(any("record-specific" in error for error in result["errors"]))

        with tempfile.TemporaryDirectory() as directory:
            run_dir = self.make_complete_run(Path(directory))
            candidates_path = run_dir / "sourcing" / "candidates.json"
            candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
            candidates["candidates"][0]["origins"][0]["canonical_url"] = (
                "https://www.ycombinator.com/companies/absent-record?utm_source=test"
            )
            candidates_path.write_text(json.dumps(candidates), encoding="utf-8")

            result = self.run_module.validate_run(run_dir)

        self.assertFalse(result["valid"], result)
        self.assertTrue(any("sourcing provenance" in error for error in result["errors"]))

        with tempfile.TemporaryDirectory() as directory:
            run_dir = self.make_complete_run(Path(directory))
            candidates_path = run_dir / "sourcing" / "candidates.json"
            candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
            candidates["excluded"] = [{
                "name": "Excluded Co",
                "candidate_type": "excluded",
                "reason": "Outside thesis",
                "origins": [self._origin(99)],
            }]
            candidates_path.write_text(json.dumps(candidates), encoding="utf-8")
            summary_path = run_dir / "run-summary.md"
            summary_path.write_text(
                summary_path.read_text(encoding="utf-8").replace(
                    "## Skipped candidates\nNone.", "## Skipped candidates\nExcluded Co"
                ),
                encoding="utf-8",
            )

            result = self.run_module.validate_run(run_dir)

        self.assertFalse(result["valid"], result)
        self.assertTrue(any("exclusion excluded co" in error.lower() and "provenance" in error.lower() for error in result["errors"]))

    def test_origin_provenance_requires_exact_source_id_and_candidate_identity(self):
        mutations = (
            (lambda record: record.pop("source"), "source"),
            (lambda record: record.pop("source_id"), "source_id"),
            (lambda record: record.update({"source": "invented"}), "source"),
            (lambda record: record.update({"source_id": "invented"}), "source_id"),
            (lambda record: record.update({"candidate_name": "Company 2"}), "candidate identity"),
            (lambda record: record.update({"candidate_slug": "company-2"}), "candidate identity"),
        )
        for mutate, phrase in mutations:
            with self.subTest(phrase=phrase), tempfile.TemporaryDirectory() as directory:
                run_dir = self.make_complete_run(Path(directory))
                retrieval_path = run_dir / "sourcing" / "retrieval.json"
                retrieval = json.loads(retrieval_path.read_text(encoding="utf-8"))
                mutate(retrieval["results"][0])
                retrieval_path.write_text(json.dumps(retrieval), encoding="utf-8")

                result = self.run_module.validate_run(run_dir)

            self.assertFalse(result["valid"], result)
            self.assertTrue(any(phrase in error.lower() for error in result["errors"]), result["errors"])

    def test_signal_provenance_requires_exact_provider_and_source_id(self):
        mutations = (
            (lambda record: record.pop("source"), "source"),
            (lambda record: record.pop("source_id"), "source_id"),
            (lambda record: record.update({"source": "yc"}), "source"),
            (lambda record: record.update({"source_id": "other-item"}), "source_id"),
            (lambda record: record.update({"candidate_name": "Company 2"}), "candidate identity"),
        )
        for mutate, phrase in mutations:
            with self.subTest(phrase=phrase), tempfile.TemporaryDirectory() as directory:
                run_dir = self.make_complete_run(Path(directory))
                candidates_path = run_dir / "sourcing" / "candidates.json"
                candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
                candidate = candidates["candidates"][0]
                hn_url = "https://news.ycombinator.com/item?id=4242"
                candidate["freshness_or_traction_signals"].append(
                    {"kind": "traction", "source_url": hn_url, "score": 10}
                )
                candidate["source_urls"].append(hn_url)
                candidates_path.write_text(json.dumps(candidates), encoding="utf-8")
                retrieval_path = run_dir / "sourcing" / "retrieval.json"
                retrieval = json.loads(retrieval_path.read_text(encoding="utf-8"))
                signal_record = {
                    "title": candidate["name"],
                    "candidate_name": candidate["name"],
                    "candidate_slug": candidate["slug"],
                    "candidate_website": candidate["website"],
                    "url": hn_url,
                    "source": "hacker_news",
                    "source_id": "4242",
                    "published_date": "2026-08-20T00:00:00Z",
                    "highlights": ["HN traction signal"],
                }
                mutate(signal_record)
                retrieval["results"].append(signal_record)
                retrieval_path.write_text(json.dumps(retrieval), encoding="utf-8")

                result = self.run_module.validate_run(run_dir)

            self.assertFalse(result["valid"], result)
            self.assertTrue(any(phrase in error.lower() for error in result["errors"]), result["errors"])

    def test_current_flow_sourcing_requires_source_snapshots_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = self.make_complete_run(Path(directory))
            candidates_path = run_dir / "sourcing" / "candidates.json"
            candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
            candidates["provider"] = "web"
            candidates_path.write_text(json.dumps(candidates), encoding="utf-8")
            retrieval_path = run_dir / "sourcing" / "retrieval.json"
            retrieval = json.loads(retrieval_path.read_text(encoding="utf-8"))
            retrieval["provider"] = "web"
            retrieval_path.write_text(json.dumps(retrieval), encoding="utf-8")
            manifest_path = run_dir / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["stages"]["sourcing"]["provider"] = "web"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            result = self.run_module.validate_run(run_dir)

        self.assertFalse(result["valid"], result)
        self.assertTrue(any("source_snapshots" in error for error in result["errors"]), result["errors"])

    def test_current_flow_rejects_official_company_sourcing_signal(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = self.make_complete_run(Path(directory))
            candidates_path = run_dir / "sourcing" / "candidates.json"
            candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
            candidate = candidates["candidates"][0]
            website = candidate["website"]
            candidate["freshness_or_traction_signals"].append(
                {"kind": "traction", "source_url": website, "score": 10}
            )
            candidate["source_urls"].append(website)
            candidates_path.write_text(json.dumps(candidates), encoding="utf-8")
            retrieval_path = run_dir / "sourcing" / "retrieval.json"
            retrieval = json.loads(retrieval_path.read_text(encoding="utf-8"))
            retrieval["results"].append(
                {
                    "title": candidate["name"],
                    "candidate_name": candidate["name"],
                    "candidate_slug": candidate["slug"],
                    "candidate_website": website,
                    "url": website,
                    "source": "official_company",
                    "source_id": website,
                    "published_date": None,
                    "highlights": ["Official company traction."],
                }
            )
            retrieval_path.write_text(json.dumps(retrieval), encoding="utf-8")

            result = self.run_module.validate_run(run_dir)

        self.assertFalse(result["valid"], result)
        self.assertTrue(any("official company" in error.lower() or "hn" in error.lower() for error in result["errors"]), result["errors"])

    def test_origin_provenance_comparison_normalizes_tracking_query(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = self.make_complete_run(Path(directory))
            candidates_path = run_dir / "sourcing" / "candidates.json"
            candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
            candidate = candidates["candidates"][0]
            origin = candidate["origins"][0]
            original = origin["canonical_url"]
            tracked = original + "/?utm_source=flow"
            origin["canonical_url"] = tracked
            candidate["source_urls"] = [
                tracked if url == original else url for url in candidate["source_urls"]
            ]
            for signal in candidate["freshness_or_traction_signals"]:
                if signal["source_url"] == original:
                    signal["source_url"] = tracked
            candidates_path.write_text(json.dumps(candidates), encoding="utf-8")

            result = self.run_module.validate_run(run_dir)

        self.assertTrue(result["valid"], result["errors"])

    def test_exclusion_without_product_hunt_or_yc_provenance_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = self.make_complete_run(Path(directory))
            path = run_dir / "sourcing" / "candidates.json"
            value = json.loads(path.read_text(encoding="utf-8"))
            value["excluded"] = [
                {"name": "Invented Co", "candidate_type": "excluded", "reason": "No fit", "origins": []}
            ]
            path.write_text(json.dumps(value), encoding="utf-8")

            errors = self._validate_errors(run_dir)

        self.assertIn("exclusion", errors)
        self.assertIn("origin", errors)

    def test_malformed_origin_and_manifest_shapes_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = self.make_complete_run(Path(directory))
            candidates_path = run_dir / "sourcing" / "candidates.json"
            candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
            candidates["candidates"][0]["origins"][0]["source_id"] = {"invented": True}
            candidates_path.write_text(json.dumps(candidates), encoding="utf-8")

            errors = self._validate_errors(run_dir)

        self.assertIn("source_id", errors)

        with tempfile.TemporaryDirectory() as directory:
            run_dir = self.make_complete_run(Path(directory))
            manifest_path = run_dir / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["companies"]["company-1"]["analysis"] = []
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            result = self.run_module.validate_run(run_dir)

        self.assertFalse(result["valid"])
        self.assertTrue(any("malformed current artifacts" in error for error in result["errors"]))

    def test_missing_any_company_artifact_blocks_full_coverage_completion(self):
        for artifact, stage in (
            ("evidence.json", "research"),
            ("analysis.md", "analysis"),
            ("memo.md", "memo"),
        ):
            with self.subTest(artifact=artifact), tempfile.TemporaryDirectory() as directory:
                run_dir = self.make_complete_run(Path(directory))
                (run_dir / "companies" / "company-10" / artifact).unlink()

                errors = self._validate_errors(run_dir)

            self.assertIn("company 10", errors)
            self.assertTrue("missing" in errors or "artifact" in errors)
            self.assertIn(stage, errors)

    def test_downstream_company_stage_cannot_complete_before_predecessor(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = self.make_complete_run(Path(directory))
            manifest_path = run_dir / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["companies"]["company-1"]["research"] = self.run_module._stage_record()
            manifest["companies"]["company-1"]["analysis"] = self.run_module._stage_record()
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "research.*completed"):
                self.run_module.update_stage(
                    run_dir,
                    "analysis",
                    "completed",
                    company="company-1",
                    artifacts=["companies/company-1/analysis.md"],
                )

    def test_unsupported_claim_fails_even_when_it_appears_in_retrieval(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = self.make_complete_run(Path(directory))
            company_dir = run_dir / "companies" / "company-1"
            retrieval_path = company_dir / "retrieval-initial.json"
            retrieval = json.loads(retrieval_path.read_text(encoding="utf-8"))
            retrieval["results"].append(
                {"title": "Blog", "url": "https://generic.example/post", "published_date": None, "highlights": []}
            )
            retrieval_path.write_text(json.dumps(retrieval), encoding="utf-8")
            evidence_path = company_dir / "evidence.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence["claims"][0]["source_url"] = "https://generic.example/post"
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

            errors = self._validate_errors(run_dir)

        self.assertIn("unsupported claim source", errors)
        self.assertIn("company 1", errors)

    def test_product_hunt_and_yc_claims_must_match_candidate_origins(self):
        for source_url in (
            "https://www.ycombinator.com/companies/different-company",
            "https://www.producthunt.com/posts/different-company",
        ):
            with self.subTest(source_url=source_url), tempfile.TemporaryDirectory() as directory:
                run_dir = self.make_complete_run(Path(directory))
                self._set_claim_source(
                    run_dir, "team-1", source_url, claim_type="verified_fact"
                )

                result = self.run_module.validate_run(run_dir)

            self.assertFalse(result["valid"], result)
            self.assertTrue(any("recorded origin" in error for error in result["errors"]))

    def test_company_claim_source_accepts_trusted_subdomains_not_siblings_or_suffix_tricks(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = self.make_complete_run(Path(directory))
            self._set_claim_source(
                run_dir,
                "traction-1",
                "https://metrics.company1.example/arr",
                claim_type="verified_fact",
            )

            result = self.run_module.validate_run(run_dir)

        self.assertTrue(result["valid"], result["errors"])

        for source_url in (
            "https://sibling-company1.example/arr",
            "https://company1.example.evil.test/arr",
            "https://company1-example.test/arr",
        ):
            with self.subTest(source_url=source_url), tempfile.TemporaryDirectory() as directory:
                run_dir = self.make_complete_run(Path(directory))
                self._set_claim_source(
                    run_dir, "traction-1", source_url, claim_type="verified_fact"
                )

                result = self.run_module.validate_run(run_dir)

            self.assertFalse(result["valid"], result)
            self.assertTrue(any("unsupported claim source" in error for error in result["errors"]))

    def test_missing_host_urls_never_match_each_other(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = self.make_complete_run(Path(directory))
            malformed = "http:///missing-host"
            candidates_path = run_dir / "sourcing" / "candidates.json"
            candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
            candidates["candidates"][0]["website"] = malformed
            candidates_path.write_text(json.dumps(candidates), encoding="utf-8")
            company_dir = run_dir / "companies" / "company-1"
            evidence_path = company_dir / "evidence.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence["company"]["website"] = malformed
            for claim in evidence["claims"]:
                claim["source_url"] = malformed
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
            retrieval_path = company_dir / "retrieval-initial.json"
            retrieval = json.loads(retrieval_path.read_text(encoding="utf-8"))
            retrieval["results"][0]["url"] = malformed
            retrieval_path.write_text(json.dumps(retrieval), encoding="utf-8")

            result = self.run_module.validate_run(run_dir)

        self.assertFalse(result["valid"], result)
        self.assertTrue(any("absolute http" in error.lower() or "hostname" in error.lower() for error in result["errors"]))

    def test_malformed_origin_signal_and_claim_urls_are_rejected_independently(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = self.make_complete_run(Path(directory))
            candidates_path = run_dir / "sourcing" / "candidates.json"
            candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
            candidates["candidates"][0]["origins"][0]["canonical_url"] = "https:///companies/no-host"
            candidates_path.write_text(json.dumps(candidates), encoding="utf-8")
            result = self.run_module.validate_run(run_dir)
        self.assertFalse(result["valid"], result)

        with tempfile.TemporaryDirectory() as directory:
            run_dir = self.make_complete_run(Path(directory))
            candidates_path = run_dir / "sourcing" / "candidates.json"
            candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
            candidates["candidates"][0]["freshness_or_traction_signals"][0][
                "source_url"
            ] = "https:///item?id=1"
            candidates_path.write_text(json.dumps(candidates), encoding="utf-8")
            result = self.run_module.validate_run(run_dir)
        self.assertFalse(result["valid"], result)

        with tempfile.TemporaryDirectory() as directory:
            run_dir = self.make_complete_run(Path(directory))
            evidence_path = run_dir / "companies" / "company-1" / "evidence.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence["claims"][0]["source_url"] = "https:///claim/no-host"
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
            result = self.run_module.validate_run(run_dir)
        self.assertFalse(result["valid"], result)

    def test_score_arithmetic_company_claim_cap_and_missing_coverage_are_enforced(self):
        mutations = {
            "arithmetic": ("**50 / 100**", "**51 / 100**", "score arithmetic mismatch"),
            "company-cap": ("| Team | 10 |", "| Team | 11 |", "company-claim-only"),
        }
        for label, (old, new, phrase) in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                run_dir = self.make_complete_run(Path(directory))
                path = run_dir / "companies" / "company-1" / "analysis.md"
                path.write_text(path.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")

                errors = self._validate_errors(run_dir)

            self.assertIn(phrase, errors)

        with tempfile.TemporaryDirectory() as directory:
            run_dir = self.make_complete_run(Path(directory))
            evidence_path = run_dir / "companies" / "company-1" / "evidence.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            next(claim for claim in evidence["claims"] if claim["id"] == "team-1")[
                "claim_type"
            ] = "verified_fact"
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
            analysis_path = run_dir / "companies" / "company-1" / "analysis.md"
            analysis = analysis_path.read_text(encoding="utf-8")
            analysis = analysis.replace(
                "| Team | 10 | claim:team-1 |",
                "| Team | 11 | claim:team-1 |",
            ).replace("**50 / 100**", "**51 / 100**")
            analysis_path.write_text(analysis, encoding="utf-8")

            errors = self._validate_errors(run_dir)

        self.assertIn("company-claim-only", errors)

        with tempfile.TemporaryDirectory() as directory:
            run_dir = self.make_complete_run(Path(directory))
            evidence_path = run_dir / "companies" / "company-1" / "evidence.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence["coverage"]["team"] = "missing"
            evidence["missing_categories"] = ["team", "competitors", "freshness"]
            evidence["unresolved_gaps"] = ["team", "competitors", "freshness"]
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

            errors = self._validate_errors(run_dir)

        self.assertIn("missing coverage must score zero", errors)

    def test_analysis_narrative_requires_resolved_same_company_refs(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = self.make_complete_run(Path(directory))
            result = self.run_module.validate_run(run_dir)
        self.assertTrue(result["valid"], result["errors"])

        mutations = (
            (
                "reports $2M ARR. [refs: traction-1]",
                "reports $2M ARR.",
                "factual narrative",
            ),
            (
                "reports 90% retention. [refs: traction-1]",
                "reports 90% retention. [refs: other-company-traction]",
                "unknown narrative reference",
            ),
        )
        for old, new, phrase in mutations:
            with self.subTest(new=new), tempfile.TemporaryDirectory() as directory:
                run_dir = self.make_complete_run(Path(directory))
                analysis_path = run_dir / "companies" / "company-1" / "analysis.md"
                analysis_path.write_text(
                    analysis_path.read_text(encoding="utf-8").replace(old, new),
                    encoding="utf-8",
                )

                result = self.run_module.validate_run(run_dir)

            self.assertFalse(result["valid"], result)
            self.assertTrue(any(phrase in error.lower() for error in result["errors"]))

    def test_factual_metrics_in_risk_section_are_not_silently_exempt(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = self.make_complete_run(Path(directory))
            analysis_path = run_dir / "companies" / "company-1" / "analysis.md"
            analysis_path.write_text(
                analysis_path.read_text(encoding="utf-8").replace(
                    "- Company-reported evidence needs confirmation.",
                    "- Retention fell to 40% and ARR declined to $1M.",
                ),
                encoding="utf-8",
            )

            result = self.run_module.validate_run(run_dir)

        self.assertFalse(result["valid"], result)
        self.assertTrue(any("factual narrative" in error.lower() for error in result["errors"]))

    def test_factual_metrics_cannot_hide_in_markdown_representations_or_uncertainty(self):
        inserted_lines = (
            "### Company 1 reports $50M ARR and 95% retention",
            "| Operating metrics | $50M ARR and 95% retention |",
            "- ARR is $50M and retention is 95%, but churn may increase.",
        )
        for inserted in inserted_lines:
            with self.subTest(inserted=inserted), tempfile.TemporaryDirectory() as directory:
                run_dir = self.make_complete_run(Path(directory))
                analysis_path = run_dir / "companies" / "company-1" / "analysis.md"
                analysis = analysis_path.read_text(encoding="utf-8")
                if inserted.startswith("-"):
                    analysis = analysis.replace(
                        "- Company-reported evidence needs confirmation.", inserted
                    )
                else:
                    analysis = analysis.replace(
                        "## Evidence-backed narrative",
                        f"## Evidence-backed narrative\n{inserted}",
                    )
                analysis_path.write_text(analysis, encoding="utf-8")

                result = self.run_module.validate_run(run_dir)

            self.assertFalse(result["valid"], result)
            self.assertTrue(
                any("factual narrative" in error.lower() for error in result["errors"]),
                result["errors"],
            )

    def test_narrative_allows_referenced_prose_and_nonfactual_connective_or_open_questions(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = self.make_complete_run(Path(directory))
            analysis_path = run_dir / "companies" / "company-1" / "analysis.md"
            analysis = analysis_path.read_text(encoding="utf-8")
            analysis = analysis.replace(
                "## Evidence-backed narrative",
                "## Evidence-backed narrative\n"
                "Company 1 reports $50M ARR and 95% retention. [refs: traction-1]\n"
                "Taken together, these signals inform the recommendation.\n"
                "| Operating metrics | $50M ARR and 95% retention [refs: traction-1] |",
            ).replace(
                "- Company-reported evidence needs confirmation.",
                "- Could churn increase?",
            )
            analysis_path.write_text(analysis, encoding="utf-8")

            result = self.run_module.validate_run(run_dir)

        self.assertTrue(result["valid"], result["errors"])

    def test_qualitative_assertions_and_unstructured_narrative_are_not_ignored(self):
        mutations = (
            (
                "- Company 1 reports $2M ARR. [refs: traction-1]",
                "- The startup signed several enterprise pilots.",
                "factual narrative",
            ),
            (
                "- Company 1 reports $2M ARR. [refs: traction-1]",
                "The startup signed several enterprise pilots.",
                "factual narrative",
            ),
        )
        for old, new, phrase in mutations:
            with self.subTest(new=new), tempfile.TemporaryDirectory() as directory:
                run_dir = self.make_complete_run(Path(directory))
                analysis_path = run_dir / "companies" / "company-1" / "analysis.md"
                analysis_path.write_text(
                    analysis_path.read_text(encoding="utf-8").replace(old, new),
                    encoding="utf-8",
                )

                result = self.run_module.validate_run(run_dir)

            self.assertFalse(result["valid"], result)
            self.assertTrue(any(phrase in error.lower() for error in result["errors"]))

    def test_missing_exact_risks_heading_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = self.make_complete_run(Path(directory))
            path = run_dir / "companies" / "company-1" / "analysis.md"
            path.write_text(
                path.read_text(encoding="utf-8").replace(
                    "## Risks and open questions", "## Risks & open questions"
                ),
                encoding="utf-8",
            )

            errors = self._validate_errors(run_dir)

        self.assertIn("## risks and open questions", errors)

    def test_unused_claim_and_company_identity_mismatch_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = self.make_complete_run(Path(directory))
            evidence_path = run_dir / "companies" / "company-1" / "evidence.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence["company"]["slug"] = "different-company"
            evidence["claims"].append(
                {
                    "id": "unused-1",
                    "area": "product",
                    "claim": "Unused company claim.",
                    "claim_type": "company_claim",
                    "source_url": "https://company1.example",
                    "source_quality": "first_party",
                    "confidence": "low",
                }
            )
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

            errors = self._validate_errors(run_dir)

        self.assertIn("company identity", errors)
        self.assertIn("unused claim", errors)

    def test_canonical_domain_and_name_duplicates_fail_but_multiple_origins_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = self.make_complete_run(Path(directory))
            result = self.run_module.validate_run(run_dir)
            self.assertTrue(result["valid"], result["errors"])
            path = run_dir / "sourcing" / "candidates.json"
            value = json.loads(path.read_text(encoding="utf-8"))
            value["candidates"][1]["website"] = "https://www.company1.example/pricing"
            path.write_text(json.dumps(value), encoding="utf-8")

            errors = self._validate_errors(run_dir)

        self.assertIn("duplicate candidate domain", errors)

    def test_valid_full_coverage_fixture_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_module.validate_run(self.make_complete_run(Path(directory)))

        self.assertTrue(result["valid"], result["errors"])


if __name__ == "__main__":
    unittest.main()
