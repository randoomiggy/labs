"""Exercise the scheduler gate with real harmless helper subprocesses."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'tools' / 'daily_gate.py'
spec = importlib.util.spec_from_file_location('daily_gate_under_test', SOURCE)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class DailyGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='daily-gate-test-', dir=os.environ.get('TMPDIR'))
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / '.local').mkdir()
        self.state = self.root / '.local' / 'state.json'
        self.state.write_text(json.dumps({'schema_version': 1, 'drafts': {}}), encoding='utf-8')
        (self.root / 'tools').mkdir()
        self.helper = self.root / 'tools' / 'workflow.py'
        self.blocker = {'task_id': 'GH-20260101', 'task_key': 'EP-001', 'version': 'v1', 'status': 'pending'}

    def helper_json(self, value):
        self.helper.write_text('import json\nprint(json.dumps(' + repr(value) + '))\n', encoding='utf-8')

    def blocked(self):
        return {'blocked': True, 'blockers': [self.blocker], 'task': None}

    def test_pending_suppresses_agent_and_preserves_journal(self):
        before = self.state.read_bytes()
        self.helper_json(self.blocked())
        result = gate.check(self.root)
        self.assertIs(result['wakeAgent'], False)
        self.assertEqual(result['active'], self.blocker)
        self.assertEqual(result['blocked_count'], 1)
        self.assertEqual(self.state.read_bytes(), before)

    def test_ready_wakes_only_the_selected_task(self):
        self.helper_json({'blocked': False, 'blockers': [], 'task': {'key': 'EP-002'}})
        self.assertEqual(gate.check(self.root), {'wakeAgent': True, 'reason': 'previous_exercises_approved', 'task_key': 'EP-002'})

    def test_missing_journal_fails_closed(self):
        self.state.unlink()
        self.helper_json(self.blocked())
        with self.assertRaises(ValueError):
            gate.check(self.root)

    def test_corrupt_journal_fails_closed(self):
        self.state.write_text('{', encoding='utf-8')
        with self.assertRaises(ValueError):
            gate.check(self.root)

    def test_unsupported_state_fails_closed(self):
        for value in ([], {'schema_version': 2, 'drafts': {}}, {'schema_version': 1, 'drafts': []}):
            with self.subTest(value=value):
                self.state.write_text(json.dumps(value), encoding='utf-8')
                with self.assertRaises(ValueError):
                    gate.check(self.root)

    def test_symlink_journal_fails_closed(self):
        alternate = self.root / 'alternate.json'
        self.state.rename(alternate)
        self.state.symlink_to(alternate)
        with self.assertRaises(ValueError):
            gate.check(self.root)

    def test_missing_helper_fails_closed(self):
        with self.assertRaises(ValueError):
            gate.check(self.root)

    def test_helper_failure_is_not_read_as_success(self):
        self.helper.write_text('raise SystemExit(2)\n', encoding='utf-8')
        with self.assertRaises(ValueError):
            gate.check(self.root)

    def test_invalid_helper_json_fails_closed(self):
        self.helper.write_text('print("not JSON")\n', encoding='utf-8')
        with self.assertRaises(ValueError):
            gate.check(self.root)

    def test_old_helper_without_gate_fails_closed(self):
        self.helper_json({'task': {'key': 'EP-006'}})
        with self.assertRaises(ValueError):
            gate.check(self.root)

    def test_gate_flag_must_be_boolean(self):
        for value in (0, 1, None, 'false'):
            with self.subTest(value=value):
                self.helper_json({'blocked': value, 'blockers': [], 'task': {'key': 'EP-002'}})
                with self.assertRaises(ValueError):
                    gate.check(self.root)

    def test_contradictory_selections_fail_closed(self):
        cases = [
            {'blocked': True, 'blockers': [], 'task': None},
            {'blocked': True, 'blockers': [self.blocker], 'task': {'key': 'EP-006'}},
            {'blocked': False, 'blockers': [self.blocker], 'task': {'key': 'EP-006'}},
            {'blocked': False, 'blockers': [], 'task': None},
            {'blocked': False, 'blockers': [], 'task': {'key': None}},
            {'blocked': True, 'blockers': [{}], 'task': None},
            {'blocked': False, 'task': {'key': 'EP-002'}},
        ]
        for value in cases:
            with self.subTest(value=value):
                self.helper_json(value)
                with self.assertRaises(ValueError):
                    gate.check(self.root)

    def test_real_cli_blocked_returns_wake_false(self):
        self.helper_json(self.blocked())
        result = subprocess.run([sys.executable, '-B', str(SOURCE), '--root', str(self.root)], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        self.assertIs(json.loads(result.stdout)['wakeAgent'], False)

    def test_real_cli_error_has_empty_stdout_and_no_private_root(self):
        self.state.unlink()
        result = subprocess.run([sys.executable, '-B', str(SOURCE), '--root', str(self.root)], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, '')
        self.assertNotIn(str(self.root), result.stderr)


if __name__ == '__main__':
    unittest.main()
