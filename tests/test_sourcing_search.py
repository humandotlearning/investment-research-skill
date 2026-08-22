import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skills.sourcing.scripts import search
from skills.sourcing.scripts.search import search_candidates


class SourcingSearchTests(unittest.TestCase):
    def test_load_api_key_prefers_non_empty_environment_value(self):
        with patch.dict(os.environ, {"EXA_API_KEY": "environment-key"}, clear=True):
            self.assertEqual(search._load_api_key(), "environment-key")

    def test_load_api_key_reads_current_directory_env_local(self):
        with patch.dict(os.environ, {}, clear=True), tempfile.TemporaryDirectory() as temp_dir:
            Path(temp_dir, ".env.local").write_text(
                "# local credentials\nexport EXA_API_KEY = 'local-key'\n",
                encoding="utf-8",
            )
            with patch.object(search.Path, "cwd", return_value=Path(temp_dir)):
                self.assertEqual(search._load_api_key(), "local-key")

    def test_load_api_key_returns_none_for_missing_or_malformed_value(self):
        with patch.dict(os.environ, {"EXA_API_KEY": ""}, clear=True), tempfile.TemporaryDirectory() as temp_dir:
            Path(temp_dir, ".env.local").write_text("EXA_API_KEY\n", encoding="utf-8")
            with patch.object(search.Path, "cwd", return_value=Path(temp_dir)):
                self.assertIsNone(search._load_api_key())

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
