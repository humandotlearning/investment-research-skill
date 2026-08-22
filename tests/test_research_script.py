import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skills.research.scripts import research
from skills.research.scripts.research import research_company


class ResearchScriptTests(unittest.TestCase):
    def test_load_api_key_prefers_non_empty_environment_value(self):
        with patch.dict(os.environ, {"EXA_API_KEY": "environment-key"}, clear=True):
            self.assertEqual(research._load_api_key(), "environment-key")

    def test_load_api_key_reads_current_directory_env_local(self):
        with patch.dict(os.environ, {}, clear=True), tempfile.TemporaryDirectory() as temp_dir:
            Path(temp_dir, ".env.local").write_text(
                "\nEXA_API_KEY = \"local-key\"\n",
                encoding="utf-8",
            )
            with patch.object(research.Path, "cwd", return_value=Path(temp_dir)):
                self.assertEqual(research._load_api_key(), "local-key")

    def test_load_api_key_returns_none_for_missing_or_malformed_value(self):
        with patch.dict(os.environ, {"EXA_API_KEY": ""}, clear=True), tempfile.TemporaryDirectory() as temp_dir:
            Path(temp_dir, ".env.local").write_text("not an assignment\n", encoding="utf-8")
            with patch.object(research.Path, "cwd", return_value=Path(temp_dir)):
                self.assertIsNone(research._load_api_key())

    @patch("skills.research.scripts.research.Exa")
    def test_research_company_includes_company_identity_in_query(self, exa_class):
        exa_class.return_value.search.return_value.results = []

        result = research_company("Acme", "https://acme.test", None, "key")

        self.assertIn("Acme", result["query"])
        self.assertEqual(result["company"], "Acme")


if __name__ == "__main__":
    unittest.main()
