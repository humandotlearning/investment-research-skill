import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCES_SCRIPT = ROOT / "skills" / "investment-research-sourcing" / "scripts" / "sources.py"
FIXTURES = ROOT / "tests" / "fixtures" / "sources"


def load_sources():
    spec = importlib.util.spec_from_file_location("source_adapters", SOURCES_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SourceAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = load_sources()

    def test_parses_product_hunt_atom_into_a_canonical_origin_record(self):
        records = self.sources.parse_product_hunt_atom(
            (FIXTURES / "product-hunt.atom").read_text(encoding="utf-8")
        )

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["name"], "Acme AI")
        self.assertEqual(record["slug"], "acme-ai")
        self.assertEqual(record["website"], "https://acme.example/pricing")
        self.assertEqual(
            record["origins"],
            [{
                "source": "product_hunt",
                "canonical_url": "https://www.producthunt.com/posts/acme-ai",
                "source_id": "tag:producthunt.com,2026-08-20:post/12345",
                "publication_or_batch_date": "2026-08-20T12:00:00Z",
            }],
        )
        self.assertEqual(record["freshness_or_traction_signals"][0]["kind"], "freshness")

    def test_normalizes_yc_company_directory_snapshot(self):
        records = self.sources.normalize_yc_snapshot(
            json.loads((FIXTURES / "yc-companies.json").read_text(encoding="utf-8"))
        )

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["website"], "https://acme.example")
        self.assertEqual(record["one_line_description"], "Automates diligence workflows for investment teams.")
        self.assertEqual(
            record["origins"][0],
            {
                "source": "yc",
                "canonical_url": "https://www.ycombinator.com/companies/acme-ai",
                "source_id": "42",
                "publication_or_batch_date": "S24",
            },
        )

    def test_source_domain_enforcement_accepts_only_matching_origin_domains(self):
        cases = [
            ("product_hunt", "https://www.producthunt.com/posts/acme", True),
            ("product_hunt", "https://producthunt.com/posts/acme", True),
            ("yc", "https://www.ycombinator.com/companies/acme", True),
            ("product_hunt", "https://acme.example", False),
            ("product_hunt", "https://producthunt.com.evil.example/posts/acme", False),
            ("product_hunt", "https://www.ycombinator.com/companies/acme", False),
            ("yc", "https://www.producthunt.com/posts/acme", False),
            ("hacker_news", "https://news.ycombinator.com/item?id=987654", False),
        ]

        for source, canonical_url, expected in cases:
            with self.subTest(source=source, canonical_url=canonical_url):
                origin = {
                    "source": source,
                    "canonical_url": canonical_url,
                    "source_id": "source-id",
                    "publication_or_batch_date": "2026-08-20",
                }
                self.assertEqual(self.sources.origin_is_allowed(origin), expected)

    def test_invalid_origin_exclusion_preserves_provenance(self):
        invalid = {
            "name": "Imposter",
            "slug": "imposter",
            "website": "https://imposter.example",
            "one_line_description": "Not actually sourced from Product Hunt.",
            "origins": [{
                "source": "product_hunt",
                "canonical_url": "https://example.com/posts/imposter",
                "source_id": "imposter",
                "publication_or_batch_date": "2026-08-20",
            }],
            "team_signal": None,
            "freshness_or_traction_signals": [{
                "kind": "freshness",
                "source_url": "https://example.com/posts/imposter",
            }],
            "thesis_fit_reasons": ["Claims to automate a target workflow."],
        }

        retained, excluded = self.sources.normalize_candidates([invalid])
        self.assertEqual(retained, [])
        self.assertEqual(excluded[0]["origins"], invalid["origins"])
        self.assertIn("unsupported origin", excluded[0]["reason"])

    def test_cross_source_records_merge_by_domain_with_complete_candidate_schema(self):
        product_hunt = self.sources.parse_product_hunt_atom(
            (FIXTURES / "product-hunt.atom").read_text(encoding="utf-8")
        )
        yc = self.sources.normalize_yc_snapshot(
            json.loads((FIXTURES / "yc-companies.json").read_text(encoding="utf-8"))
        )
        records = product_hunt + yc
        for record in records:
            record["thesis_fit_reasons"] = ["Automates investment-team workflows."]

        candidates, excluded = self.sources.normalize_candidates(records)

        self.assertEqual(excluded, [])
        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        required_fields = {
            "name",
            "slug",
            "website",
            "one_line_description",
            "origins",
            "team_signal",
            "freshness_or_traction_signals",
            "thesis_fit_reasons",
            "rank",
        }
        self.assertEqual(set(candidate), required_fields)
        self.assertEqual(candidate["name"], "Acme AI")
        self.assertEqual(candidate["slug"], "acme-ai")
        self.assertEqual(candidate["website"], "https://acme.example")
        self.assertEqual(
            candidate["one_line_description"],
            "Automates diligence workflows for investment teams.",
        )
        self.assertEqual(len(candidate["origins"]), 2)
        self.assertEqual({origin["source"] for origin in candidate["origins"]}, {"product_hunt", "yc"})
        self.assertIsNone(candidate["team_signal"])
        self.assertTrue(candidate["freshness_or_traction_signals"])
        self.assertTrue(all(signal.get("source_url") for signal in candidate["freshness_or_traction_signals"]))
        self.assertEqual(candidate["thesis_fit_reasons"], ["Automates investment-team workflows."])
        self.assertEqual(candidate["rank"], 1)

    def test_hacker_news_domain_match_beats_name_match_and_adds_signals_only(self):
        product_hunt = self.sources.parse_product_hunt_atom(
            (FIXTURES / "product-hunt.atom").read_text(encoding="utf-8")
        )
        product_hunt[0]["thesis_fit_reasons"] = ["Automates investment-team workflows."]
        candidates, excluded = self.sources.normalize_candidates(product_hunt)
        self.assertEqual(excluded, [])
        original_origins = candidates[0]["origins"]
        items = json.loads((FIXTURES / "hacker-news-items.json").read_text(encoding="utf-8"))

        enriched = self.sources.enrich_with_hacker_news(candidates, items)

        self.assertEqual(enriched[0]["origins"], original_origins)
        self.assertNotIn("hacker_news", {origin["source"] for origin in enriched[0]["origins"]})
        hn_url = "https://news.ycombinator.com/item?id=987654"
        competing_url = "https://news.ycombinator.com/item?id=987655"
        hn_signals = [
            signal for signal in enriched[0]["freshness_or_traction_signals"]
            if signal.get("source_url") in {hn_url, competing_url}
        ]
        self.assertEqual({signal["source_url"] for signal in hn_signals}, {hn_url})
        self.assertEqual({signal["kind"] for signal in hn_signals}, {"freshness", "traction"})

    def test_hacker_news_falls_back_to_normalized_company_name(self):
        candidate = {
            "name": "Name-Only Labs",
            "slug": "name-only-labs",
            "website": "https://nameonly.example",
            "one_line_description": "Searchable research notes.",
            "origins": [{
                "source": "yc",
                "canonical_url": "https://www.ycombinator.com/companies/name-only-labs",
                "source_id": "name-only-labs",
                "publication_or_batch_date": "S26",
            }],
            "team_signal": None,
            "freshness_or_traction_signals": [{
                "kind": "freshness",
                "source_url": "https://www.ycombinator.com/companies/name-only-labs",
            }],
            "thesis_fit_reasons": ["Improves research workflows."],
            "rank": 1,
        }
        items = json.loads((FIXTURES / "hacker-news-items.json").read_text(encoding="utf-8"))

        enriched = self.sources.enrich_with_hacker_news([candidate], items)

        hn_url = "https://news.ycombinator.com/item?id=987656"
        self.assertEqual(
            {signal["kind"] for signal in enriched[0]["freshness_or_traction_signals"] if signal.get("source_url") == hn_url},
            {"freshness", "traction"},
        )
        self.assertEqual(enriched[0]["origins"], candidate["origins"])

    def test_missing_signal_is_excluded_with_origin_provenance(self):
        record = {
            "name": "Quiet Co",
            "slug": "quiet-co",
            "website": "https://quiet.example",
            "one_line_description": "A company without a freshness or traction signal.",
            "origins": [{
                "source": "yc",
                "canonical_url": "https://www.ycombinator.com/companies/quiet-co",
                "source_id": "quiet-co",
                "publication_or_batch_date": None,
            }],
            "team_signal": None,
            "freshness_or_traction_signals": [],
            "thesis_fit_reasons": ["Fits the target workflow."],
        }

        candidates, excluded = self.sources.normalize_candidates([record])

        self.assertEqual(candidates, [])
        self.assertEqual(excluded[0]["origins"], record["origins"])
        self.assertIn("missing freshness or traction signal", excluded[0]["reason"])

    def test_ranking_is_deterministic_regardless_of_input_order(self):
        def record(name):
            slug = name.lower()
            origin_url = f"https://www.producthunt.com/posts/{slug}"
            return {
                "name": name,
                "slug": slug,
                "website": f"https://{slug}.example",
                "one_line_description": f"{name} workflow software.",
                "origins": [{
                    "source": "product_hunt",
                    "canonical_url": origin_url,
                    "source_id": slug,
                    "publication_or_batch_date": "2026-08-20",
                }],
                "team_signal": None,
                "freshness_or_traction_signals": [{
                    "kind": "freshness",
                    "source_url": origin_url,
                }],
                "thesis_fit_reasons": ["Fits the target workflow."],
            }

        forward, forward_excluded = self.sources.normalize_candidates([record("Beta"), record("Alpha")])
        reverse, reverse_excluded = self.sources.normalize_candidates([record("Alpha"), record("Beta")])

        self.assertEqual(forward_excluded, [])
        self.assertEqual(reverse_excluded, [])
        self.assertEqual([(candidate["name"], candidate["rank"]) for candidate in forward], [("Alpha", 1), ("Beta", 2)])
        self.assertEqual(forward, reverse)


if __name__ == "__main__":
    unittest.main()
