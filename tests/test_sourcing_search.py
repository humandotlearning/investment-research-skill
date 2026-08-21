import unittest
from unittest.mock import patch

from skills.sourcing.scripts.search import search_candidates


class SourcingSearchTests(unittest.TestCase):
    @patch("skills.sourcing.scripts.search.Exa")
    def test_search_candidates_returns_serializable_results(self, exa_class):
        exa_class.return_value.search.return_value.results = [
            type(
                "Result",
                (),
                {
                    "title": "Acme",
                    "url": "https://acme.test",
                    "published_date": None,
                    "highlights": ["AI workflow automation"],
                },
            )()
        ]

        result = search_candidates("AI agents for SMBs", "SMB workflow thesis", 1, "key")

        self.assertEqual(result["results"][0]["url"], "https://acme.test")
        self.assertEqual(result["results"][0]["highlights"], ["AI workflow automation"])


if __name__ == "__main__":
    unittest.main()
