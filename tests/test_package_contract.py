import json
import py_compile
import re
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
EXPECTED_SKILLS = {
    "investment-research-start",
    "investment-research-sourcing",
    "investment-research-evidence",
    "investment-research-analysis",
    "investment-research-memo",
}


class PackageContractTests(unittest.TestCase):
    def test_skill_directories_match_frontmatter_names(self):
        directories = {path.name for path in SKILLS.iterdir() if path.is_dir()}
        self.assertEqual(directories, EXPECTED_SKILLS)

        for directory in sorted(EXPECTED_SKILLS):
            text = (SKILLS / directory / "SKILL.md").read_text(encoding="utf-8")
            match = re.match(r"---\n(.*?)\n---\n", text, re.DOTALL)
            self.assertIsNotNone(match, directory)
            fields = {}
            for line in match.group(1).splitlines():
                key, value = line.split(":", 1)
                fields[key.strip()] = value.strip()
            self.assertEqual(fields["name"], directory)
            self.assertRegex(fields["name"], r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
            self.assertLessEqual(len(fields["name"]), 64)
            self.assertTrue(1 <= len(fields["description"]) <= 1024)
            self.assertTrue(1 <= len(fields["compatibility"]) <= 500)
            self.assertEqual(
                set(fields), {"name", "description", "compatibility"}, directory
            )

    def test_plugin_metadata_and_cleanup_contract(self):
        plugin = json.loads(
            (ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        self.assertEqual(plugin["name"], "investment-research")
        self.assertEqual(
            plugin["repository"],
            "https://github.com/humandotlearning/investment-research-skill",
        )
        self.assertFalse((ROOT / "skills-lock.json").exists())
        self.assertFalse((ROOT / "docs" / "superpowers").exists())
        self.assertEqual(list(SKILLS.rglob(".gitkeep")), [])

    def test_readme_documents_portable_clients_and_provider_fallback(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()
        for phrase in ["claude code", "codex", "hermes", "openclaw", "exa", "web fallback"]:
            self.assertIn(phrase, readme)

    def test_sourcing_skill_uses_snapshot_adapters_for_the_flow_path(self):
        text = (SKILLS / "investment-research-sourcing" / "SKILL.md").read_text(
            encoding="utf-8"
        ).lower()

        for phrase in [
            "scripts/search.py snapshots",
            "--input",
            "--thesis",
            "--product-hunt",
            "--yc",
            "--hacker-news",
            "--retrieval-output",
            "source_snapshots",
            "legacy exa",
        ]:
            self.assertIn(phrase, text)
        self.assertNotIn("prefer `scripts/search.py --input", text)

    def test_entry_skill_uses_source_snapshot_codex_pipeline_preflight(self):
        text = (SKILLS / "investment-research-start" / "SKILL.md").read_text(
            encoding="utf-8"
        ).lower()

        for phrase in ["source snapshots", "codex pipeline", "source_snapshots"]:
            self.assertIn(phrase, text)
        self.assertNotIn("exa is preferred", text)

    def test_package_has_only_expected_helpers_and_they_compile(self):
        scripts = sorted(
            path.relative_to(ROOT).as_posix()
            for path in SKILLS.rglob("*.py")
        )
        self.assertEqual(
            scripts,
            [
                "skills/investment-research-evidence/scripts/research.py",
                "skills/investment-research-sourcing/scripts/search.py",
                "skills/investment-research-sourcing/scripts/sources.py",
                "skills/investment-research-start/scripts/flow_v2.py",
                "skills/investment-research-start/scripts/run.py",
            ],
        )
        with tempfile.TemporaryDirectory() as directory:
            for index, relative in enumerate(scripts):
                py_compile.compile(
                    str(ROOT / relative),
                    cfile=str(Path(directory) / f"helper-{index}.pyc"),
                    doraise=True,
                )

    def test_skill_references_stay_inside_their_skill_roots(self):
        for directory in sorted(EXPECTED_SKILLS):
            skill_root = (SKILLS / directory).resolve()
            text = (skill_root / "SKILL.md").read_text(encoding="utf-8")
            references = re.findall(
                r"(?<![A-Za-z0-9_.-])((?:scripts|references|assets)/[A-Za-z0-9_./-]+)",
                text,
            )
            for reference in references:
                resolved = (skill_root / reference.rstrip(".,;:")).resolve()
                self.assertTrue(resolved.is_relative_to(skill_root), reference)
                self.assertTrue(resolved.exists(), reference)
            for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
                if re.match(r"^(?:https?://|#)", target):
                    continue
                resolved = (skill_root / target).resolve()
                self.assertFalse(Path(target).is_absolute(), target)
                self.assertTrue(resolved.is_relative_to(skill_root), target)
                self.assertTrue(resolved.exists(), target)
            self.assertNotRegex(text, r"`(?:\.\./|[A-Za-z]:\\|/)[^`]+`")


if __name__ == "__main__":
    unittest.main()
