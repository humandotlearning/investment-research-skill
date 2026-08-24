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

    def test_rejects_origin_records_outside_product_hunt_and_yc_domains(self):
        invalid = {
            "name": "Imposter",
            "origins": [{
                "source": "product_hunt",
                "canonical_url": "https://example.com/posts/imposter",
                "source_id": "imposter",
                "publication_or_batch_date": "2026-08-20",
            }],
        }

        self.assertFalse(self.sources.origin_is_allowed(invalid["origins"][0]))
        retained, excluded = self.sources.normalize_candidates([invalid])
        self.assertEqual(retained, [])
        self.assertEqual(excluded[0]["origins"], invalid["origins"])
        self.assertIn("unsupported origin", excluded[0]["reason"])


if __name__ == "__main__":
    unittest.main()
