"""Consistency checks for the checked-in project plan and local privacy rules."""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ProjectMetadataTests(unittest.TestCase):
    def test_required_documents_exist(self):
        for name in ["AGENTS.md", "README.md", "ROADMAP.md", "BACKLOG.json",
                     "docs/WORKFLOW.md", "docs/DECISIONS.md", "templates/task.md",
                     "practice/README.md", "labs/README.md", "Makefile", ".gitignore",
                     "tools/workflow.py", "tools/unittest_driver.py"]:
            with self.subTest(name=name):
                self.assertTrue((ROOT / name).is_file())
                self.assertGreater((ROOT / name).stat().st_size, 0)

    def test_backlog_is_ordered_unique_and_self_consistent(self):
        backlog = json.loads((ROOT / "BACKLOG.json").read_text(encoding="utf-8"))
        self.assertEqual(backlog["schema_version"], 1)
        self.assertGreater(len(backlog["items"]), 0)
        required = {"key", "topic", "title", "goal", "slug", "scope", "level",
                    "depends_on", "source", "acceptance"}
        seen = set()
        slugs = set()
        for number, item in enumerate(backlog["items"], 1):
            with self.subTest(key=item.get("key")):
                self.assertEqual(set(item), required)
                self.assertEqual(item["key"], f"EP-{number:03d}")
                self.assertNotIn(item["key"], seen)
                self.assertRegex(item["slug"], r"^ep\d{3,}_[a-z0-9_]+$")
                self.assertNotIn(item["slug"], slugs)
                self.assertEqual(item["scope"], f"practice/{item['slug']}")
                self.assertTrue(set(item["depends_on"]).issubset(seen))
                self.assertIsInstance(item["acceptance"], list)
                self.assertTrue(all(isinstance(rule, str) and rule.strip() for rule in item["acceptance"]))
                self.assertGreater(len(item["acceptance"]), 0)
                self.assertEqual(item["source"], "original exercise")
                seen.add(item["key"])
                slugs.add(item["slug"])

    def test_gitignore_excludes_private_artifacts_but_not_source(self):
        private = [".local/state.json", ".local/drafts/GH-20261105/v1/manifest.json",
                   "tools/__pycache__/workflow.cpython-314.pyc", ".venv/pyvenv.cfg",
                   ".env", ".env.production", "logs/run.log", "credentials.json", "private.pem"]
        public = ["AGENTS.md", "BACKLOG.json", "tests/test_workflow.py",
                  "practice/example/solution.py", ".env.example"]
        result = subprocess.run(
            ["git", "check-ignore", "--no-index", "--stdin", "-z"],
            cwd=ROOT, input="\0".join(private + public) + "\0", capture_output=True,
            text=True, check=False, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        ignored = set(filter(None, result.stdout.split("\0")))
        self.assertEqual(ignored, set(private))

    def test_project_policy_and_makefile_use_real_interfaces(self):
        policy = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("America/Vancouver", policy)
        self.assertIn("09:30", policy)
        self.assertIn("Never call `decide` from cron", policy)
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertIn("\tpython3 -m unittest discover -s tests -v", makefile)
        for command in ("status", "next"):
            self.assertIn(f"\tpython3 tools/workflow.py {command}", makefile)
        self.assertIsNone(re.search(r"\b(?:pip install|git commit|git push)\b", makefile))


if __name__ == "__main__":
    unittest.main()
