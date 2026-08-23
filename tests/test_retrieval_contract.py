import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SEARCH_SCRIPT = ROOT / "skills" / "investment-research-sourcing" / "scripts" / "search.py"
RESEARCH_SCRIPT = ROOT / "skills" / "investment-research-evidence" / "scripts" / "research.py"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RetrievalContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.search = load_module("portable_search", SEARCH_SCRIPT)
        cls.research = load_module("portable_research", RESEARCH_SCRIPT)

    def test_search_canonicalizes_deduplicates_and_bounds_results(self):
        results = [
            {"title": "One", "url": "HTTPS://Example.COM:443/", "highlights": ["x" * 700, "ignored"]},
            {"title": "Duplicate", "url": "https://example.com#fragment", "highlights": ["duplicate"]},
        ] + [
            {"title": str(index), "url": f"https://{index}.example", "highlights": ["ok"]}
            for index in range(30)
        ]

        serialized = self.search.serialize_results(results, limit=20)

        self.assertEqual(serialized[0]["url"], "https://example.com")
        self.assertEqual(len(serialized), 20)
        self.assertEqual(len(serialized[0]["highlights"]), 1)
        self.assertEqual(len(serialized[0]["highlights"][0]), 400)

    def test_search_uses_stable_failure_codes(self):
        with self.assertRaises(self.search.RetrievalError) as missing_key:
            self.search.search_candidates(
                {"seed": {"type": "topic", "value": "AI"}}, "Thesis", None
            )
        self.assertEqual(missing_key.exception.code, 4)

        original = self.search.Exa
        self.search.Exa = None
        try:
            with self.assertRaises(self.search.RetrievalError) as missing_sdk:
                self.search.search_candidates(
                    {"seed": {"type": "topic", "value": "AI"}}, "Thesis", "key"
                )
        finally:
            self.search.Exa = original
        self.assertEqual(missing_sdk.exception.code, 3)

    def test_provider_authentication_errors_use_code_four(self):
        class Client:
            def __init__(self, api_key):
                pass

            def search(self, query, **kwargs):
                raise RuntimeError("401 unauthorized")

        for module, call in [
            (
                self.search,
                lambda: self.search.search_candidates(
                    {"seed": {"type": "topic", "value": "AI"}}, "Thesis", "key"
                ),
            ),
            (
                self.research,
                lambda: self.research.research_company(
                    "Acme", "https://acme.example", None, "key"
                ),
            ),
        ]:
            original = module.Exa
            module.Exa = Client
            try:
                with self.assertRaises(module.RetrievalError) as failure:
                    call()
            finally:
                module.Exa = original
            self.assertEqual(failure.exception.code, 4)

    def test_malformed_provider_payload_uses_serialization_code_six(self):
        class Response:
            results = None

        class Client:
            def __init__(self, api_key):
                pass

            def search(self, query, **kwargs):
                return Response()

        original = self.search.Exa
        self.search.Exa = Client
        try:
            with self.assertRaises(self.search.RetrievalError) as failure:
                self.search.search_candidates(
                    {"seed": {"type": "topic", "value": "AI"}}, "Thesis", "key"
                )
        finally:
            self.search.Exa = original
        self.assertEqual(failure.exception.code, 6)

    def test_research_normalizes_complete_retry_list(self):
        self.assertEqual(
            self.research.normalize_focus(["freshness", "traction", "traction"]),
            ["traction", "freshness"],
        )
        with self.assertRaises(self.research.RetrievalError) as invalid:
            self.research.normalize_focus(["revenue"])
        self.assertEqual(invalid.exception.code, 2)

    def test_research_handles_quotes_unicode_and_writes_compact_file(self):
        class Response:
            results = [
                {
                    "title": "Official",
                    "url": "https://example.com/",
                    "highlights": ["y" * 600],
                }
            ]

        class Client:
            def __init__(self, api_key):
                self.api_key = api_key

            def search(self, query, **kwargs):
                return Response()

        original = self.research.Exa
        self.research.Exa = Client
        try:
            payload = self.research.research_company(
                'Acme "namaste"', "https://example.com", ["team", "traction"], "key"
            )
        finally:
            self.research.Exa = original

        self.assertEqual(payload["status"], "ok")
        self.assertIn('Acme "namaste"', payload["query"])
        self.assertEqual(payload["missing_categories"], ["team", "traction"])
        self.assertEqual(len(payload["results"]), 1)
        self.assertLessEqual(len(json.dumps(payload, ensure_ascii=False)), 3000)

    def test_atomic_json_write_leaves_no_temporary_sibling(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "retrieval.json"
            self.search.atomic_write_json(destination, {"status": "ok"})
            self.assertEqual(json.loads(destination.read_text(encoding="utf-8")), {"status": "ok"})
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
