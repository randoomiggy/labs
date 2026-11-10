"""Read-only pre-run gate: pending work must never wake a new exercise agent."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


def check(root: Path) -> dict:
    """Consult the normal workflow CLI; fail closed on missing or invalid state."""
    local = root / '.local'
    state_path = local / 'state.json'
    if local.is_symlink() or state_path.is_symlink() or not state_path.is_file():
        raise ValueError('private decision journal is missing or unsafe')
    try:
        state = json.loads(state_path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        raise ValueError('private decision journal cannot be read') from error
    if not isinstance(state, dict) or state.get('schema_version') != 1 or not isinstance(state.get('drafts'), dict):
        raise ValueError('private decision journal has an unsupported format')
    helper = root / 'tools' / 'workflow.py'
    if helper.is_symlink() or not helper.is_file():
        raise ValueError('workflow helper is missing or unsafe')
    result = subprocess.run(
        [sys.executable, '-B', str(helper), '--root', str(root), 'next'],
        cwd=root, capture_output=True, text=True, encoding='utf-8', errors='strict',
        timeout=15, check=False,
    )
    if result.returncode != 0:
        raise ValueError('workflow refused to select an exercise; inspect the local journal')
    try:
        selection = json.loads(result.stdout)
    except ValueError as error:
        raise ValueError('workflow returned invalid selection JSON') from error
    if not isinstance(selection, dict) or type(selection.get('blocked')) is not bool:
        raise ValueError('workflow has no explicit approval gate')
    blockers = selection.get('blockers')
    if not isinstance(blockers, list):
        raise ValueError('workflow blocker list is missing')
    if selection['blocked']:
        if not blockers or selection.get('task') is not None:
            raise ValueError('workflow returned inconsistent blocked state')
        active = blockers[0]
        required = ('task_id', 'task_key', 'version', 'status')
        if not isinstance(active, dict) or any(not isinstance(active.get(key), str) or not active[key] for key in required):
            raise ValueError('workflow active exercise is invalid')
        return {'wakeAgent': False, 'reason': 'awaiting_live_approval',
                'active': {key: active[key] for key in required}, 'blocked_count': len(blockers)}
    task = selection.get('task')
    if blockers or not isinstance(task, dict) or not isinstance(task.get('key'), str):
        raise ValueError('workflow returned inconsistent ready state')
    return {'wakeAgent': True, 'reason': 'previous_exercises_approved', 'task_key': task['key']}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    try:
        result = check(args.root)
    except (ValueError, OSError, subprocess.SubprocessError, UnicodeError):
        print('daily-gate: cannot safely select an exercise; inspect local workflow state', file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
