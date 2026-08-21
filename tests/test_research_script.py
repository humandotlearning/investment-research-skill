import unittest
from unittest.mock import patch

from skills.research.scripts.research import research_company


class ResearchScriptTests(unittest.TestCase):
    @patch("skills.research.scripts.research.Exa")
    def test_research_company_includes_company_identity_in_query(self, exa_class):
        exa_class.return_value.search.return_value.results = []

        result = research_company("Acme", "https://acme.test", None, "key")

        self.assertIn("Acme", result["query"])
        self.assertEqual(result["company"], "Acme")


if __name__ == "__main__":
    unittest.main()
