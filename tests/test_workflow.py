"""Regression checks for the local review workflow; all fixture data is synthetic."""
from __future__ import annotations

from contextlib import nullcontext
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from workflow import Workflow, WorkflowError, relative_path  # noqa: E402


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(os.environ.get("TMPDIR", str(Path.home() / ".hermes/cache/scratch")))
        scratch.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="workflow-test-", dir=scratch)
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / "project"
        self.root.mkdir()
        self.source = self.base / "source"
        self.scope = "practice/ep001_example"
        (self.source / self.scope).mkdir(parents=True)
        (self.source / self.scope / "solution.py").write_text(
            "def add_one(value):\n    return value + 1\n", encoding="utf-8"
        )
        (self.source / self.scope / "test_solution.py").write_text(
            "import unittest\nfrom solution import add_one\n"
            "class ExampleTests(unittest.TestCase):\n"
            "    def test_example(self):\n        self.assertEqual(add_one(1), 2)\n",
            encoding="utf-8",
        )
        (self.root / "BACKLOG.json").write_text(json.dumps({
            "schema_version": 1,
            "items": [{"key": "EP-001", "title": "First"}, {"key": "EP-002", "title": "Second"}],
        }), encoding="utf-8")
        self.workflow = Workflow(self.root)
        self.task_id = "GH-20261105"

    def proposal(self):
        return self.workflow.draft(self.source, "EP-001", self.task_id)

    def checked_proposal(self):
        result = self.proposal()
        report = self.workflow.run_tests(self.task_id, "v1", self.scope)
        self.assertTrue(report["passed"], report)
        return result

    def decide(self, proposal, action="approve", version="v1", evidence=None):
        words = {"approve": "Одобряю", "reject": "Отклоняю", "revise": "Доработать"}
        return self.workflow.decide(
            self.task_id, version, proposal["fingerprint"], action,
            evidence or f"{words[action]} {self.task_id} {version}",
        )

    @staticmethod
    def overwrite(path, content):
        path.chmod(0o600)
        path.write_text(content, encoding="utf-8")

    def private_files(self):
        return {path.relative_to(self.root).as_posix(): (path.read_bytes(), path.stat().st_mode & 0o777)
                for path in (self.root / ".local").rglob("*") if path.is_file()}

    def legacy_pending_queue(self, count=2):
        """Recreate the old multi-pending state only in this disposable fixture.

        Each snapshot/report is made by real helper calls, with real tests. The
        subsequent synthetic journal edit models pre-gate pending proposals; it
        is not live consent or evidence for the actual project's tasks.
        """
        (self.root / "BACKLOG.json").write_text(json.dumps({
            "schema_version": 1,
            "items": [{"key": f"EP-{number:03d}", "title": "Synthetic exercise"}
                      for number in range(1, count + 2)],
        }), encoding="utf-8")
        for number in range(1, count + 1):
            task_id = f"GH-202611{number + 4:02d}"
            proposal = self.workflow.draft(self.source, f"EP-{number:03d}", task_id)
            self.assertTrue(self.workflow.run_tests(task_id, "v1", self.scope)["passed"])
            self.workflow.decide(task_id, "v1", proposal["fingerprint"], "approve", f"Одобряю {task_id} v1")
        state = json.loads(self.workflow.state_path.read_text(encoding="utf-8"))
        state["drafts"] = dict(reversed(list(state["drafts"].items())))
        for item in state["drafts"].values():
            item["versions"][-1]["status"] = "pending"
            del item["versions"][-1]["decision"]
        self.workflow.state_path.write_text(json.dumps(state), encoding="utf-8")

    def assert_gate_denial_unchanged(self, key="EP-002", task_id="GH-20261106"):
        before = self.private_files()
        with self.assertRaises(WorkflowError):
            self.workflow.draft(self.source, key, task_id)
        self.assertEqual(self.private_files(), before)

    def test_initial_state_has_no_proposals_or_publications(self):
        status = self.workflow.init_state()
        self.assertEqual(status["tasks"], [])
        self.assertEqual(status["status_counts"], {})
        self.assertFalse(status["publication_supported"])
        self.assertEqual((self.root / ".local").stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.root / ".local/state.json").stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.workflow.init_state(), status)

    def test_next_starts_at_first_seed(self):
        result = self.workflow.next_task()
        self.assertEqual(result["task"]["key"], "EP-001")
        self.assertIs(result["blocked"], False)
        self.assertEqual(result["blockers"], [])
        self.assertEqual(result["blocker_count"], 0)
        self.assertIsNone(result["active_task"])
        self.assertFalse((self.root / ".local").exists(), "next must remain read-only")

    def test_snapshot_does_not_apply_files_to_project(self):
        proposal = self.proposal()
        self.assertEqual(proposal["status"], "pending")
        self.assertEqual(len(proposal["fingerprint"]), 64)
        self.assertFalse((self.root / self.scope).exists())
        verified = self.workflow.verify(self.task_id, "v1")
        self.assertTrue(verified["integrity"])
        self.assertTrue(verified["base_matches"])
        self.assertEqual(verified["fingerprint"], proposal["fingerprint"])

    def test_silence_never_implies_approval(self):
        self.proposal()
        for _ in range(3):
            self.assertEqual(self.workflow.status()["status_counts"], {"pending": 1})

    def test_content_tampering_is_detected(self):
        proposal = self.proposal()
        file = Path(proposal["snapshot_dir"]) / "payload" / self.scope / "solution.py"
        self.overwrite(file, "raise RuntimeError('changed')\n")
        with self.assertRaisesRegex(WorkflowError, "content changed"):
            self.workflow.verify(self.task_id, "v1")

    def test_additional_payload_file_is_detected(self):
        proposal = self.proposal()
        (Path(proposal["snapshot_dir"]) / "payload/extra.txt").write_text("extra", encoding="utf-8")
        with self.assertRaisesRegex(WorkflowError, "file list changed"):
            self.workflow.verify(self.task_id, "v1")

    def test_manifest_tampering_is_detected(self):
        proposal = self.proposal()
        file = Path(proposal["snapshot_dir"]) / "manifest.json"
        manifest = json.loads(file.read_text(encoding="utf-8"))
        manifest["base_commit"] = "changed"
        self.overwrite(file, json.dumps(manifest))
        with self.assertRaisesRegex(WorkflowError, "fingerprint changed"):
            self.workflow.verify(self.task_id, "v1")

    def test_manifest_symlink_is_rejected(self):
        proposal = self.proposal()
        file = Path(proposal["snapshot_dir"]) / "manifest.json"
        target = self.base / "other.json"
        target.write_bytes(file.read_bytes())
        file.unlink()
        file.symlink_to(target)
        with self.assertRaisesRegex(WorkflowError, "Manifest must not be a symlink"):
            self.workflow.verify(self.task_id, "v1")

    def test_private_and_traversal_paths_are_rejected(self):
        for name in ["../escape", "/absolute", "a/../b", "./file.py", ".git/config", ".local/state.json",
                     "a/.env", ".env.production", "key.pem", "a\\b", "C:/x"]:
            with self.subTest(name=name), self.assertRaises(WorkflowError):
                relative_path(name)
        self.assertEqual(relative_path(".env.example"), ".env.example")
        self.assertEqual(relative_path("practice/example.py"), "practice/example.py")

    def test_source_symlinks_are_rejected(self):
        (self.source / "link.py").symlink_to(self.source / self.scope / "solution.py")
        with self.assertRaisesRegex(WorkflowError, "Symlinks"):
            self.proposal()

    def test_destination_symlinks_are_rejected(self):
        (self.root / "practice").symlink_to(self.base / "elsewhere", target_is_directory=True)
        with self.assertRaisesRegex(WorkflowError, "symlink"):
            self.proposal()

    def test_state_symlink_is_rejected(self):
        (self.root / ".local").symlink_to(self.source, target_is_directory=True)
        with self.assertRaisesRegex(WorkflowError, "symlink"):
            self.workflow.init_state()

    def test_empty_payload_is_rejected(self):
        empty = self.base / "empty"
        empty.mkdir()
        with self.assertRaisesRegex(WorkflowError, "empty payload"):
            self.workflow.draft(empty, "EP-001", self.task_id)

    def test_identifiers_are_not_silently_repaired(self):
        for bad_id in ["", "GH-20260230", "GH-20261301", "GH-2026-11-05", "gh-20261105", "../GH-20261105"]:
            with self.subTest(bad_id=bad_id), self.assertRaises(WorkflowError):
                self.workflow.draft(self.source, "EP-001", bad_id)
        with self.assertRaises(WorkflowError):
            self.workflow.draft(self.source, "EP1", self.task_id)

    def test_revision_supersedes_old_approval(self):
        first = self.checked_proposal()
        self.decide(first)
        second = self.proposal()
        self.assertEqual(second["version"], "v2")
        self.assertNotEqual(first["fingerprint"], second["fingerprint"])
        self.assertEqual(self.workflow.verify(self.task_id, "v1")["status"], "superseded")
        self.assertEqual(self.workflow.verify(self.task_id, "v2")["status"], "pending")
        with self.assertRaisesRegex(WorkflowError, "latest pending"):
            self.decide(first)

    def test_same_day_cannot_silently_replace_task(self):
        self.proposal()
        with self.assertRaisesRegex(WorkflowError, "One task per local date"):
            self.workflow.draft(self.source, "EP-002", self.task_id)

    def test_same_task_uses_original_id_for_revisions(self):
        self.proposal()
        with self.assertRaisesRegex(WorkflowError, "already proposed"):
            self.workflow.draft(self.source, "EP-001", "GH-20261106")

    def test_next_blocks_proposed_without_claiming_learning(self):
        self.proposal()
        before = self.private_files()
        result = self.workflow.next_task()
        self.assertIs(result["blocked"], True)
        self.assertIsNone(result["task"])
        self.assertEqual(result["blocker_count"], 1)
        self.assertEqual(result["blockers"], [{"task_id": self.task_id, "task_key": "EP-001",
                                              "version": "v1", "status": "pending"}])
        self.assertEqual(result["active_task"], result["blockers"][0])
        status = self.workflow.status()
        for field in ("blocked", "blocker_count", "blockers", "active_task"):
            self.assertEqual(status[field], result[field])
        self.assertEqual(self.private_files(), before)
        self.assertEqual(self.workflow.status()["tasks"][0]["status"], "pending")

    def test_queue_exhaustion_proposes_a_new_key(self):
        self.decide(self.checked_proposal())
        second_id = "GH-20261106"
        second = self.workflow.draft(self.source, "EP-002", second_id)
        self.assertTrue(self.workflow.run_tests(second_id, "v1", self.scope)["passed"])
        self.workflow.decide(second_id, "v1", second["fingerprint"], "approve", f"Одобряю {second_id} v1")
        result = self.workflow.next_task()
        self.assertTrue(result["seed_queue_exhausted"])
        self.assertEqual(result["task"]["key"], "EP-003")
        self.assertIs(result["blocked"], False)
        self.assertEqual(result["blockers"], [])

    def test_new_topic_denied_while_pending_without_snapshot_or_state_changes(self):
        self.proposal()
        self.assert_gate_denial_unchanged()
        self.assert_gate_denial_unchanged("EP-999", "GH-20261107")

    def test_out_of_order_new_task_must_match_next(self):
        self.workflow.init_state()
        self.assert_gate_denial_unchanged()
        self.assertEqual(self.workflow.next_task()["task"]["key"], "EP-001")
        self.decide(self.checked_proposal())
        self.assert_gate_denial_unchanged("EP-999", "GH-20261107")
        self.assertEqual(self.workflow.next_task()["task"]["key"], "EP-002")

    def test_rejected_and_revision_requested_still_block_but_allow_same_task_repair(self):
        first = self.proposal()
        self.decide(first, action="reject")
        self.assertEqual(self.workflow.next_task()["active_task"]["status"], "rejected")
        self.assert_gate_denial_unchanged()
        second = self.proposal()
        self.assertEqual(second["version"], "v2")
        self.decide(second, action="revise", version="v2")
        result = self.workflow.next_task()
        self.assertIsNone(result["task"])
        self.assertEqual(result["active_task"]["status"], "revision_requested")
        self.assert_gate_denial_unchanged()
        third = self.proposal()
        self.assertEqual(third["version"], "v3")
        self.assertTrue(self.workflow.run_tests(self.task_id, "v3", self.scope)["passed"])
        self.decide(third, version="v3")
        self.assertFalse(self.workflow.next_task()["blocked"])
        self.assertEqual(self.workflow.next_task()["task"]["key"], "EP-002")

    def test_legacy_multiple_pending_are_counted_oldest_first_and_only_active_can_revise(self):
        self.legacy_pending_queue(count=5)
        result = self.workflow.next_task()
        self.assertEqual(result["blocker_count"], 5)
        self.assertEqual(result["blocker_count"], len(result["blockers"]))
        self.assertEqual([item["task_key"] for item in result["blockers"]],
                         [f"EP-{number:03d}" for number in range(1, 6)])
        self.assertEqual(result, self.workflow.next_task(), "selection must be deterministic")
        self.assertIsNone(result["task"])
        self.assert_gate_denial_unchanged("EP-006", "GH-20261110")
        self.assert_gate_denial_unchanged("EP-002", "GH-20261106")
        revised = self.proposal()
        self.assertEqual(revised["version"], "v2")
        result = self.workflow.next_task()
        self.assertEqual(result["blocker_count"], 5)
        self.assertEqual(result["active_task"]["version"], "v2")
        self.assertTrue(self.workflow.run_tests(self.task_id, "v2", self.scope)["passed"])
        self.decide(revised, version="v2")
        result = self.workflow.next_task()
        self.assertEqual(result["blocker_count"], 4)
        self.assertEqual(result["active_task"]["task_key"], "EP-002")
        self.assertIsNone(result["task"])

    def test_approved_earlier_task_may_be_reopened_but_not_bypass_an_earlier_blocker(self):
        self.decide(self.checked_proposal())
        second_id = "GH-20261106"
        second = self.workflow.draft(self.source, "EP-002", second_id)
        reopened = self.proposal()
        self.assertEqual(reopened["version"], "v2")
        self.assertEqual(self.workflow.next_task()["active_task"]["task_key"], "EP-001")
        self.assertFalse(self.workflow.verify(self.task_id, "v1")["local_approval_valid"])
        self.assertTrue(self.workflow.run_tests(second_id, "v1", self.scope)["passed"])
        self.workflow.decide(second_id, "v1", second["fingerprint"], "approve", f"Одобряю {second_id} v1")
        self.assert_gate_denial_unchanged("EP-002", second_id)

    def test_approval_resolves_queue_but_base_and_evidence_remain_separate_application_gates(self):
        with patch.object(self.workflow, "_head", return_value="base-a"):
            proposal = self.checked_proposal()
            self.decide(proposal)
        report = Path(proposal["snapshot_dir"]) / "verification.json"
        report.write_text("{}", encoding="utf-8")
        with patch.object(self.workflow, "_head", return_value="base-after-publication"):
            self.assertFalse(self.workflow.verify(self.task_id, "v1")["local_approval_valid"])
            result = self.workflow.next_task()
            self.assertFalse(result["blocked"])
            self.assertEqual(result["task"]["key"], "EP-002")
            self.assertEqual(self.workflow.status()["status_counts"], {"approved": 1})

    def test_unknown_and_malformed_journal_fails_closed_without_mutation(self):
        self.proposal()
        original = json.loads(self.workflow.state_path.read_text(encoding="utf-8"))
        mutations = [
            lambda state: state["drafts"][self.task_id]["versions"][-1].update(status="published"),
            lambda state: state["drafts"][self.task_id]["versions"][-1].update(status="superseded"),
            lambda state: state["drafts"][self.task_id]["versions"][-1].update(status=[]),
            lambda state: state["drafts"][self.task_id].update(versions=[]),
            lambda state: state["drafts"][self.task_id].update(versions=[None]),
            lambda state: state["drafts"][self.task_id]["versions"][-1].update(version="v2"),
            lambda state: state["drafts"][self.task_id]["versions"][-1].update(fingerprint="bad"),
            lambda state: state["drafts"][self.task_id]["versions"][-1].update(created_at="not-a-time"),
            lambda state: state["drafts"][self.task_id]["versions"][-1].update(task_id="GH-20261107"),
            lambda state: state["drafts"][self.task_id]["versions"][-1].update(status="approved"),
            lambda state: state["drafts"].update({"GH-20261106": state["drafts"][self.task_id]}),
        ]
        for number, mutate in enumerate(mutations):
            state = json.loads(json.dumps(original))
            mutate(state)
            self.workflow.state_path.write_text(json.dumps(state), encoding="utf-8")
            with self.subTest(case=number):
                for command in (self.workflow.status, self.workflow.next_task):
                    with self.assertRaises(WorkflowError):
                        command()
                self.assert_gate_denial_unchanged()

    def test_invalid_json_and_duplicate_keys_do_not_reset_queue(self):
        self.proposal()
        for content in ('{"schema_version":', '{"schema_version":1,"drafts":{},"drafts":{}}',
                        '{"schema_version":1,"drafts":{},"other":NaN}', '[]'):
            with self.subTest(content=content):
                self.workflow.state_path.write_text(content, encoding="utf-8")
                with self.assertRaises(WorkflowError):
                    self.workflow.next_task()
                self.assert_gate_denial_unchanged()

    def test_approved_history_requires_a_consistent_decision_and_historical_hash(self):
        self.decide(self.checked_proposal())
        original = json.loads(self.workflow.state_path.read_text(encoding="utf-8"))
        bad_decisions = [None, {}, {"action": "approve"},
                         {"action": "approve", "evidence": f"Одобряю {self.task_id} v1",
                          "recorded_at": "2026-11-05T16:33:49+00:00", "verification_sha256": "bad"}]
        for decision in bad_decisions:
            with self.subTest(decision=decision):
                state = json.loads(json.dumps(original))
                state["drafts"][self.task_id]["versions"][-1]["decision"] = decision
                self.workflow.state_path.write_text(json.dumps(state), encoding="utf-8")
                with self.assertRaises(WorkflowError):
                    self.workflow.next_task()
                self.assert_gate_denial_unchanged()

    def test_missing_or_truncated_state_with_snapshots_requires_manual_recovery(self):
        self.proposal()
        self.workflow.state_path.unlink()
        with self.assertRaisesRegex(WorkflowError, "inventory mismatch"):
            self.workflow.next_task()
        self.assert_gate_denial_unchanged()
        self.workflow.state_path.write_text('{"schema_version":1,"drafts":{}}', encoding="utf-8")
        with self.assertRaisesRegex(WorkflowError, "inventory mismatch"):
            self.workflow.status()
        self.assert_gate_denial_unchanged()

    def test_malformed_backlog_denies_draft_without_mutation(self):
        self.workflow.init_state()
        for items in ([None], [{"key": []}], [{"key": "EP-001"}, {"key": "EP-001"}]):
            with self.subTest(items=items):
                (self.root / "BACKLOG.json").write_text(json.dumps({"schema_version": 1, "items": items}), encoding="utf-8")
                with self.assertRaises(WorkflowError):
                    self.workflow.next_task()
                self.assert_gate_denial_unchanged("EP-001", self.task_id)

    def test_competing_new_topic_drafts_recheck_gate_under_the_same_lock(self):
        self.workflow.init_state()
        script = Path(__file__).resolve().parents[1] / "tools/workflow.py"
        with self.workflow._lock():
            child = subprocess.Popen(
                [sys.executable, str(script), "--root", str(self.root), "draft", "--task-key", "EP-002",
                 "--task-id", "GH-20261106", "--source", str(self.source)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            self.addCleanup(lambda: child.kill() if child.poll() is None else None)
            time.sleep(0.1)
            self.assertIsNone(child.poll(), "Competing draft must wait on the held workflow lock")
            # A separate Workflow instance acquires the same lock only after it
            # is released. Instead finish the first draft under this held lock.
            with patch.object(self.workflow, "_lock", side_effect=nullcontext):
                self.proposal()
        stdout, stderr = child.communicate(timeout=10)
        self.assertEqual(child.returncode, 2, stderr)
        self.assertEqual(stdout, "")
        self.assertIn("Approval gate blocked", json.loads(stderr)["error"])
        status = self.workflow.status()
        self.assertEqual(len(status["tasks"]), 1)
        self.assertEqual(status["blocker_count"], 1)

    def test_actual_snapshot_tests_pass(self):
        self.proposal()
        result = self.workflow.run_tests(self.task_id, "v1", self.scope)
        self.assertEqual(result["returncode"], 0)
        self.assertEqual(result["tests_run"], 1)
        self.assertTrue(result["passed"])
        self.assertFalse(result["is_os_sandbox"])
        self.assertIn("Ran 1 test", result["stderr"])
        self.assertFalse((self.root / self.scope).exists())

    def test_failing_tests_cannot_be_approved(self):
        (self.source / self.scope / "solution.py").write_text("def add_one(value):\n    return value\n", encoding="utf-8")
        proposal = self.proposal()
        result = self.workflow.run_tests(self.task_id, "v1", self.scope)
        self.assertFalse(result["passed"])
        with self.assertRaisesRegex(WorkflowError, "passing, non-empty"):
            self.decide(proposal)

    def test_zero_tests_is_not_success(self):
        (self.source / self.scope / "test_solution.py").unlink()
        proposal = self.proposal()
        result = self.workflow.run_tests(self.task_id, "v1", self.scope)
        # Empty discovery returns 5 on Python 3.14, and 0 on older interpreters.
        self.assertIn(result["returncode"], (0, 5))
        self.assertEqual(result["tests_run"], 0)
        self.assertFalse(result["passed"])
        with self.assertRaises(WorkflowError):
            self.decide(proposal)

    def test_all_skipped_tests_do_not_count_as_executed_checks(self):
        file = self.source / self.scope / "test_solution.py"
        file.write_text(
            "import unittest\nclass SkippedTests(unittest.TestCase):\n"
            "    @unittest.skip('synthetic fixture')\n"
            "    def test_skipped(self):\n        self.fail('not executed')\n",
            encoding="utf-8",
        )
        proposal = self.proposal()
        result = self.workflow.run_tests(self.task_id, "v1", self.scope)
        self.assertFalse(result["passed"])
        with self.assertRaises(WorkflowError):
            self.decide(proposal)

    def test_printed_fake_runner_summary_does_not_prove_completion(self):
        file = self.source / self.scope / "test_solution.py"
        file.write_text(
            "import sys\ndef load_tests(loader, tests, pattern):\n"
            "    print('Ran 1 test in 0.001s', file=sys.stderr)\n"
            "    print('OK', file=sys.stderr)\n    sys.exit(0)\n",
            encoding="utf-8",
        )
        proposal = self.proposal()
        result = self.workflow.run_tests(self.task_id, "v1", self.scope)
        self.assertEqual(result["returncode"], 0)
        self.assertFalse(result["driver_completed"])
        self.assertEqual(result["tests_run"], 0)
        self.assertFalse(result["passed"])
        with self.assertRaises(WorkflowError):
            self.decide(proposal)

    def test_only_expected_failures_do_not_count_as_success(self):
        file = self.source / self.scope / "test_solution.py"
        file.write_text(
            "import unittest\nclass ExpectedFailures(unittest.TestCase):\n"
            "    @unittest.expectedFailure\n"
            "    def test_expected(self):\n        self.fail('synthetic failure')\n",
            encoding="utf-8",
        )
        proposal = self.proposal()
        result = self.workflow.run_tests(self.task_id, "v1", self.scope)
        self.assertEqual(result["expected_failures"], 1)
        self.assertEqual(result["tests_succeeded"], 0)
        self.assertFalse(result["passed"])
        with self.assertRaises(WorkflowError):
            self.decide(proposal)

    def test_mixed_pass_and_skip_reports_real_counters(self):
        file = self.source / self.scope / "test_solution.py"
        with file.open("a", encoding="utf-8") as handle:
            handle.write("    @unittest.skip('synthetic skip')\n    def test_skipped(self):\n        pass\n")
        self.proposal()
        result = self.workflow.run_tests(self.task_id, "v1", self.scope)
        self.assertEqual(result["tests_run"], 2)
        self.assertEqual(result["tests_succeeded"], 1)
        self.assertEqual(result["tests_skipped"], 1)
        self.assertTrue(result["driver_completed"])
        self.assertTrue(result["passed"])

    def test_cli_draft_test_verify_and_reject(self):
        script = Path(__file__).resolve().parents[1] / "tools/workflow.py"

        def command(*arguments):
            result = subprocess.run(
                [sys.executable, str(script), "--root", str(self.root), *arguments],
                capture_output=True, text=True, check=False, timeout=15,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)

        proposal = command("draft", "--task-key", "EP-001", "--source", str(self.source),
                           "--task-id", self.task_id)
        selection = command("next")
        self.assertIs(selection["blocked"], True)
        self.assertIsNone(selection["task"])
        self.assertEqual(selection["blocker_count"], len(selection["blockers"]))
        before = self.private_files()
        denied = subprocess.run(
            [sys.executable, str(script), "--root", str(self.root), "draft", "--task-key", "EP-002",
             "--task-id", "GH-20261106", "--source", str(self.source)],
            capture_output=True, text=True, check=False, timeout=15,
        )
        self.assertEqual(denied.returncode, 2)
        self.assertEqual(denied.stdout, "")
        self.assertIn("Approval gate blocked", json.loads(denied.stderr)["error"])
        self.assertEqual(self.private_files(), before)
        report = command("test", "--task-id", self.task_id, "--version", "v1",
                         "--start-dir", self.scope)
        self.assertTrue(report["passed"])
        self.assertTrue(command("verify", "--task-id", self.task_id, "--version", "v1")["integrity"])
        decision = command("decide", "--task-id", self.task_id, "--version", "v1",
                           "--fingerprint", proposal["fingerprint"], "--action", "reject",
                           "--evidence", f"Отклоняю {self.task_id} v1")
        self.assertEqual(decision["status"], "rejected")
        self.assertFalse((self.root / self.scope).exists())

    def test_approval_requires_real_test_report(self):
        proposal = self.proposal()
        with self.assertRaisesRegex(WorkflowError, "test evidence"):
            self.decide(proposal)

    def test_approval_requires_exact_live_user_evidence(self):
        proposal = self.checked_proposal()
        with self.assertRaisesRegex(WorkflowError, "actual user command"):
            self.decide(proposal, evidence="silence means yes")
        with self.assertRaisesRegex(WorkflowError, "fingerprint"):
            self.workflow.decide(self.task_id, "v1", "0" * 64, "approve", f"Одобряю {self.task_id} v1")
        result = self.decide(proposal)
        self.assertEqual(result["status"], "approved")
        self.assertFalse(result["publication_performed"])
        self.assertTrue(self.workflow.verify(self.task_id, "v1")["local_approval_valid"])
        self.assertFalse((self.root / self.scope).exists())
        with self.assertRaisesRegex(WorkflowError, "latest pending"):
            self.decide(proposal)

    def test_rejection_does_not_require_tests_or_apply_files(self):
        proposal = self.proposal()
        result = self.decide(proposal, action="reject")
        self.assertEqual(result["status"], "rejected")
        self.assertFalse(result["publication_performed"])
        self.assertFalse((self.root / self.scope).exists())

    def test_revision_request_requires_a_new_version(self):
        proposal = self.proposal()
        result = self.decide(proposal, action="revise")
        self.assertEqual(result["status"], "revision_requested")
        with self.assertRaisesRegex(WorkflowError, "latest pending"):
            self.decide(proposal)
        self.assertEqual(self.proposal()["version"], "v2")

    def test_destination_change_invalidates_approval(self):
        proposal = self.checked_proposal()
        destination = self.root / self.scope / "solution.py"
        destination.parent.mkdir(parents=True)
        destination.write_text("changed independently", encoding="utf-8")
        self.assertFalse(self.workflow.verify(self.task_id, "v1")["base_matches"])
        with self.assertRaisesRegex(WorkflowError, "destination files changed"):
            self.decide(proposal)

    def test_base_commit_change_invalidates_approval(self):
        with patch.object(self.workflow, "_head", return_value="base-a"):
            proposal = self.checked_proposal()
        with patch.object(self.workflow, "_head", return_value="base-b"):
            self.assertFalse(self.workflow.verify(self.task_id, "v1")["base_matches"])
            with self.assertRaisesRegex(WorkflowError, "Base commit"):
                self.decide(proposal)

    def test_tampered_verification_report_is_rejected(self):
        proposal = self.checked_proposal()
        file = Path(proposal["snapshot_dir"]) / "verification.json"
        report = json.loads(file.read_text(encoding="utf-8"))
        report["stdout"] = "invented result"
        file.write_text(json.dumps(report), encoding="utf-8")
        with self.assertRaisesRegex(WorkflowError, "test evidence"):
            self.decide(proposal)

    def test_historical_approval_does_not_hide_invalidated_evidence(self):
        proposal = self.checked_proposal()
        self.decide(proposal)
        file = Path(proposal["snapshot_dir"]) / "verification.json"
        report = json.loads(file.read_text(encoding="utf-8"))
        report["stdout"] = "changed after decision"
        file.write_text(json.dumps(report), encoding="utf-8")
        result = self.workflow.verify(self.task_id, "v1")
        self.assertTrue(result["integrity"])
        self.assertEqual(result["status"], "approved")
        self.assertFalse(result["test_evidence_valid"])
        self.assertFalse(result["local_approval_valid"])

    def test_failed_rerun_blocks_use_of_an_existing_approval(self):
        proposal = self.checked_proposal()
        self.decide(proposal)
        with patch("workflow.TEST_TIMEOUT_SECONDS", 0.00001):
            self.assertFalse(self.workflow.run_tests(self.task_id, "v1", self.scope)["passed"])
        result = self.workflow.verify(self.task_id, "v1")
        self.assertEqual(result["status"], "approved")
        self.assertFalse(result["local_approval_valid"])
        self.assertTrue(self.workflow.run_tests(self.task_id, "v1", self.scope)["passed"])
        self.assertTrue(self.workflow.verify(self.task_id, "v1")["local_approval_valid"])

    def test_test_process_does_not_inherit_synthetic_secret(self):
        file = self.source / self.scope / "test_solution.py"
        file.write_text(
            "import os, unittest\nclass EnvironmentTests(unittest.TestCase):\n"
            "    def test_environment(self):\n        self.assertNotIn('SYNTHETIC_TEST_SECRET', os.environ)\n",
            encoding="utf-8",
        )
        self.proposal()
        with patch.dict(os.environ, {"SYNTHETIC_TEST_SECRET": "synthetic-fixture-not-a-real-key"}):
            self.assertTrue(self.workflow.run_tests(self.task_id, "v1", self.scope)["passed"])

    def test_timeout_is_a_failed_check(self):
        (self.source / self.scope / "test_solution.py").write_text(
            "import time, unittest\nclass SlowTest(unittest.TestCase):\n"
            "    def test_slow(self):\n        time.sleep(10)\n", encoding="utf-8"
        )
        proposal = self.proposal()
        with patch("workflow.TEST_TIMEOUT_SECONDS", 0.1):
            result = self.workflow.run_tests(self.task_id, "v1", self.scope)
        self.assertFalse(result["passed"])
        self.assertLess(result["returncode"], 0)
        self.assertTrue(result["timed_out"])
        self.assertIn("-second limit", result["stderr"])
        with self.assertRaises(WorkflowError):
            self.decide(proposal)

    def test_timeout_stops_ordinary_descendants(self):
        started = self.base / "descendant_started"
        completed = self.base / "descendant_completed"
        child_code = (
            "import time; from pathlib import Path; "
            f"Path({str(started)!r}).write_text('synthetic'); "
            "time.sleep(1.0); "
            f"Path({str(completed)!r}).write_text('should not happen')"
        )
        (self.source / self.scope / "test_solution.py").write_text(
            "import subprocess, sys, time, unittest\n"
            "class DescendantTest(unittest.TestCase):\n"
            "    def test_child(self):\n"
            f"        subprocess.Popen([sys.executable, '-c', {child_code!r}])\n"
            "        time.sleep(10)\n", encoding="utf-8"
        )
        self.proposal()
        with patch("workflow.TEST_TIMEOUT_SECONDS", 0.4):
            result = self.workflow.run_tests(self.task_id, "v1", self.scope)
        self.assertTrue(result["timed_out"])
        self.assertTrue(started.exists(), "Descendant must have started for this to test cleanup")
        time.sleep(1.1)
        self.assertFalse(completed.exists())

    def test_cli_runs_and_has_no_publish_command(self):
        script = Path(__file__).resolve().parents[1] / "tools/workflow.py"
        result = subprocess.run(
            [sys.executable, str(script), "--root", str(self.root), "status"],
            capture_output=True, text=True, check=False, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)["publication_supported"])
        for command in ("commit", "push", "apply", "publish"):
            result = subprocess.run(
                [sys.executable, str(script), "--root", str(self.root), command],
                capture_output=True, text=True, check=False, timeout=10,
            )
            self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
