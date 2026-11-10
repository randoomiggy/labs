"""Report-export regressions: synthetic identifiers, real files and CLI calls."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from report_export import ExportError, export_report, redact_report  # noqa: E402
from workflow import Workflow  # noqa: E402


class ReportExportTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(os.environ.get("TMPDIR", str(Path.home() / ".hermes/cache/scratch")))
        scratch.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="report-export-test-", dir=scratch)
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.source = self.base / "raw.md"
        self.output = self.base / "masked.md"
        self.source.write_bytes(b"Synthetic report\n")
        self.script = Path(__file__).resolve().parents[1] / "tools/report_export.py"

    def cli(self, *args):
        return subprocess.run([sys.executable, str(self.script), *map(str, args)],
                              capture_output=True, check=False, timeout=10)

    def assert_refused_unchanged(self, output=None):
        output = self.output if output is None else output
        before = self.source.read_bytes()
        with self.assertRaises((ExportError, OSError)):
            export_report(self.source, output)
        self.assertEqual(self.source.read_bytes(), before)
        if output != self.source and not output.is_symlink():
            self.assertFalse(output.exists())

    def test_masks_known_patterns_and_keeps_report_readable(self):
        source = (
            "/home/synthetic-user/projects/demo/tests/test_solution.py\n"
            "/home/synthetic-user/notes.txt /Users/synthetic-user/notes.txt\n"
            "mail=reviewer@private.example tag=Synthetic#1234\n"
            "phone: 2025550100 mobile=+1 (202) 555-0100 other: 202-555-0100\n"
            "token=ghp_" + "A" * 36 + "\n"
            "Authorization: Bearer synthetic-credential-value\n"
            'password: "synthetic phrase only"\n'
        )
        result = redact_report(source, "/home/synthetic-user/projects/demo")
        self.assertIn("<project>/tests/test_solution.py", result)
        self.assertIn("<home>/notes.txt", result)
        self.assertIn("<email>", result)
        self.assertIn("<battletag>", result)
        self.assertEqual(result.count("<phone>"), 3)
        for private in ("synthetic-user", "private.example", "Synthetic#1234", "2025550100",
                        "555-0100", "ghp_", "synthetic-credential-value", "synthetic phrase only"):
            self.assertNotIn(private, result)

    def test_preserves_hashes_versions_numbers_task_ids_and_ordinary_code_exactly(self):
        sha = hashlib.sha256(b"synthetic evidence").hexdigest()
        source = (
            f"EP-001 GH-20261105 v1 version=3.11.10 sha256={sha}\n"
            f'{{"before_sha256":"{sha}","tests_run":1234567890}}\n'
            "2026-11-05T16:33:49.600936+00:00\n"
            "```python\ndef add_one(value):\n    return value + 1\n"
            "password = None\nsecret = ''\ntoken = get_token()\n"
            "password = os.environ['SYNTHETIC_PASSWORD']\n"
            "if token == expected_value:\n    return True\n```\n"
            "HTTP 599; range(100, 600); 1234567890; /var/log/synthetic.log\n"
        )
        self.assertEqual(redact_report(source), source)

    def test_json_format_and_safe_values_survive_masking(self):
        raw = {"path": "/Users/synthetic-user/demo/file.py", "email": "fixture@private.example",
               "token": "synthetic-token-value", "password": None, "version": "v2",
               "code": "def add_one(value): return value + 1"}
        result = json.loads(redact_report(json.dumps(raw), "/Users/synthetic-user/demo"))
        self.assertEqual(result["path"], "<project>/file.py")
        self.assertEqual(result["email"], "<email>")
        self.assertEqual(result["token"], "<token>")
        for field in ("password", "version", "code"):
            self.assertEqual(result[field], raw[field])

    def test_known_token_prefixes_are_masked_without_entropy_guessing(self):
        tokens = ["ghp_" + "A" * 36, "github_pat_" + "B" * 40,
                  "sk-proj-" + "C" * 32, "xoxb-" + "D" * 24,
                  "AKIA" + "E" * 16, "eyJ" + "a" * 12 + "." + "b" * 16 + "." + "c" * 16]
        for token in tokens:
            with self.subTest(prefix=token.split("_")[0][:12]):
                self.assertEqual(redact_report("credential " + token), "credential <token>")

    def test_explicit_local_sensitive_values_are_literal_and_longest_first(self):
        source = "owner=synthetic-owner-long account=synthetic-owner literal=[synthetic.*]"
        values = ["synthetic-owner", "synthetic-owner-long", "[synthetic.*]"]
        self.assertEqual(redact_report(source, sensitive_values=values),
                         "owner=<redacted> account=<redacted> literal=<redacted>")
        self.assertEqual(redact_report("password=synthetic!credential", sensitive_values=["synthetic!credential"]),
                         "password=<redacted>")

    def test_explicit_sensitive_values_have_a_strict_contract(self):
        for values in ("synthetic-owner", b"synthetic-owner", [""], ["  "], [None], [123]):
            with self.subTest(values=repr(values)), self.assertRaises(ExportError):
                redact_report("Synthetic report", sensitive_values=values)

    def test_export_creates_new_private_file_and_never_changes_raw_bytes(self):
        self.source.write_bytes("Email fixture@private.example\r\nПроверка\n".encode("utf-8"))
        before = self.source.read_bytes()
        notice = export_report(self.source, self.output)
        self.assertEqual(self.source.read_bytes(), before)
        self.assertEqual(self.output.read_bytes(), "Email <email>\r\nПроверка\n".encode("utf-8"))
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o600)
        self.assertEqual(notice["masking"], "best-effort")
        self.assertIs(notice["comprehensive_security_scan"], False)
        self.assertIs(notice["manual_review_required"], True)

    def test_repeated_redaction_is_stable_for_masked_reports(self):
        first = redact_report('email=fixture@private.example secret="synthetic-value" phone=2025550100')
        self.assertEqual(redact_report(first), first)

    def test_refuses_same_path_existing_output_and_hardlink(self):
        self.assert_refused_unchanged(self.source)
        self.output.write_bytes(b"Existing reviewed report\n")
        before = self.output.read_bytes()
        with self.assertRaises(ExportError):
            export_report(self.source, self.output)
        self.assertEqual(self.output.read_bytes(), before)
        self.output.unlink()
        os.link(self.source, self.output)
        with self.assertRaises(ExportError):
            export_report(self.source, self.output)
        self.assertEqual(self.source.read_bytes(), self.output.read_bytes())

    def test_refuses_output_symlinks_including_dangling_links(self):
        for target in (self.source, self.base / "not-created"):
            with self.subTest(target=target.name):
                self.output.symlink_to(target)
                self.assert_refused_unchanged()
                self.assertTrue(self.output.is_symlink())
                self.output.unlink()

    def test_refuses_source_and_parent_symlinks_without_following_them(self):
        alias = self.base / "alias.md"
        alias.symlink_to(self.source)
        with self.assertRaises(ExportError):
            export_report(alias, self.output)
        alias.unlink()
        directory = self.base / "real"
        directory.mkdir()
        link = self.base / "link"
        link.symlink_to(directory, target_is_directory=True)
        self.assert_refused_unchanged(link / "masked.md")
        self.assertEqual(list(directory.iterdir()), [])

    def test_refuses_exports_under_immutable_payload_manifest_or_snapshot_before_writing(self):
        snapshot = self.base / ".local/drafts/GH-20261105/v1"
        (snapshot / "payload").mkdir(parents=True)
        (snapshot / "manifest.json").write_bytes(b"{}\n")
        outputs = [snapshot / "payload/report.md", snapshot / "manifest.json", snapshot / "review-export.md",
                   self.base / "payload/export.md", self.base / "manifest.json"]
        (self.base / "payload").mkdir()
        for output in outputs:
            with self.subTest(output=output.relative_to(self.base)):
                before = {path.relative_to(self.base): path.read_bytes()
                          for path in self.base.rglob("*") if path.is_file()}
                with self.assertRaises(ExportError):
                    export_report(self.source, output)
                after = {path.relative_to(self.base): path.read_bytes()
                         for path in self.base.rglob("*") if path.is_file()}
                self.assertEqual(after, before)

    def test_refuses_snapshot_like_directory_even_outside_default_local_layout(self):
        snapshot = self.base / "copied-snapshot"
        (snapshot / "payload").mkdir(parents=True)
        (snapshot / "manifest.json").write_bytes(b"{}")
        self.assert_refused_unchanged(snapshot / "masked.md")

    def test_parent_must_exist_and_parent_traversal_is_not_repaired(self):
        parent = self.base / "absent"
        self.assert_refused_unchanged(parent / "masked.md")
        self.assertFalse(parent.exists())
        self.assert_refused_unchanged(self.base / "absent/../masked.md")

    def test_invalid_utf8_and_binary_input_fail_before_creating_any_output(self):
        for raw in (b"Late UTF-8 failure after readable text\n\xff", b"\x00Synthetic", b"Synthetic\x01", b"Synthetic\x7f"):
            with self.subTest(raw=repr(raw)):
                self.source.write_bytes(raw)
                self.assert_refused_unchanged()

    def test_obvious_unhandled_secrets_fail_closed_with_no_output(self):
        for raw in ("Unknown short credential ghp_short", "Unknown short credential sk-short",
                    "password=synthetic!credential", "secret=синтетическое-значение",
                    "-----BEGIN PRIVATE KEY-----\nsynthetic-only\n-----END PRIVATE KEY-----"):
            with self.subTest(raw=raw.splitlines()[0]):
                self.source.write_text(raw, encoding="utf-8")
                self.assert_refused_unchanged()

    def test_project_root_is_specific_and_path_prefix_does_not_mask_a_sibling(self):
        for root in ("/", "/home", "/Users"):
            with self.subTest(root=root), self.assertRaises(ExportError):
                redact_report("Synthetic", root)
        self.assertEqual(redact_report("/opt/demo/file.py /opt/demo-other/file.py", "/opt/demo"),
                         "<project>/file.py /opt/demo-other/file.py")

    def test_cli_real_utf8_export_with_local_sensitive_file(self):
        self.source.write_bytes("fixture@private.example synthetic-owner Проверка\n".encode("utf-8"))
        private = self.base / "local-sensitive.json"
        private.write_text(json.dumps(["synthetic-owner"]), encoding="utf-8")
        result = self.cli(self.source, self.output, "--root", self.base, "--sensitive-file", private)
        self.assertEqual(result.returncode, 0, result.stderr)
        notice = json.loads(result.stdout)
        self.assertEqual(notice["masking"], "best-effort")
        self.assertTrue(notice["manual_review_required"])
        self.assertEqual(result.stderr, b"")
        self.assertEqual(self.output.read_bytes(), "<email> <redacted> Проверка\n".encode("utf-8"))
        self.assertEqual(json.loads(private.read_bytes()), ["synthetic-owner"])

    def test_cli_refusals_are_nonzero_with_no_output_and_no_raw_contents_in_diagnostics(self):
        for raw in (b"fixture@private.example\xff", b"\x00synthetic-secret", b"ghp_short"):
            with self.subTest(raw=repr(raw)):
                self.source.write_bytes(raw)
                result = self.cli(self.source, self.output)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, b"")
                self.assertIn("error", json.loads(result.stderr))
                self.assertFalse(self.output.exists())
                self.assertNotIn(b"private.example", result.stderr)
                self.assertNotIn(b"synthetic-secret", result.stderr)
                self.assertNotIn(b"ghp_short", result.stderr)
                self.assertEqual(self.source.read_bytes(), raw)

    def test_cli_rejects_malformed_sensitive_files_and_unsafe_paths(self):
        private = self.base / "local-sensitive.json"
        for raw in (b"[\xff]", b'{}', b'[""]', b'[123]'):
            with self.subTest(raw=raw):
                private.write_bytes(raw)
                result = self.cli(self.source, self.output, "--sensitive-file", private)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, b"")
                self.assertFalse(self.output.exists())
        result = self.cli(self.source, self.source)
        self.assertEqual(result.returncode, 2)
        result = self.cli()
        self.assertEqual(result.returncode, 2)
        result = self.cli("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn(b"best-effort", result.stdout)

    def test_export_of_real_test_evidence_keeps_raw_hashes_and_approval_gate_valid(self):
        root = self.base / "project"
        root.mkdir()
        (root / "BACKLOG.json").write_text('{"schema_version":1,"items":[{"key":"EP-001"}]}', encoding="utf-8")
        scope = "practice/ep001_example"
        source = self.base / "source"
        (source / scope).mkdir(parents=True)
        (source / scope / "test_example.py").write_text(
            "import unittest\nclass Example(unittest.TestCase):\n"
            "    def test_real(self):\n        self.assertEqual(1, 1)\n", encoding="utf-8"
        )
        workflow = Workflow(root)
        proposal = workflow.draft(source, "EP-001", "GH-20261105")
        report = workflow.run_tests("GH-20261105", "v1", scope)
        self.assertTrue(report["passed"])
        snapshot = Path(proposal["snapshot_dir"])
        raw_path = snapshot / "verification.json"
        before = {path.relative_to(snapshot): path.read_bytes() for path in snapshot.rglob("*") if path.is_file()}
        export_report(raw_path, self.output, root)
        exported = json.loads(self.output.read_bytes())
        self.assertEqual(exported["tests_run"], 1)
        self.assertEqual(exported["fingerprint"], proposal["fingerprint"])
        self.assertNotIn(str(Path.home()), self.output.read_text(encoding="utf-8"))
        self.assertEqual({path.relative_to(snapshot): path.read_bytes() for path in snapshot.rglob("*") if path.is_file()}, before)
        verified = workflow.verify("GH-20261105", "v1")
        self.assertTrue(verified["integrity"])
        self.assertTrue(verified["test_evidence_valid"])
        self.assertEqual(verified["fingerprint"], proposal["fingerprint"])


if __name__ == "__main__":
    unittest.main()
