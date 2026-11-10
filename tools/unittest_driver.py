"""Run unittest and write counters only after normal runner completion.

Human-readable stderr is not the machine result: a test's printed text or an
 early sys.exit(0) must not be mistaken for an executed, passing test suite.
This is a trusted completion driver, not a sandbox for hostile Python.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import unittest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-dir", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    suite = unittest.defaultTestLoader.discover(args.start_dir)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    succeeded = max(0, result.testsRun - len(result.failures) - len(result.errors)
                    - len(result.skipped) - len(result.expectedFailures)
                    - len(result.unexpectedSuccesses))
    report = {
        "driver_completed": True,
        "tests_run": result.testsRun,
        "tests_skipped": len(result.skipped),
        "expected_failures": len(result.expectedFailures),
        "failures": len(result.failures),
        "errors": len(result.errors),
        "unexpected_successes": len(result.unexpectedSuccesses),
        "tests_succeeded": succeeded,
        "passed": result.wasSuccessful() and succeeded > 0,
    }
    # No report exists if discovery or a test exits the interpreter prematurely.
    with args.report.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, sort_keys=True)
        handle.write("\n")
    if report["passed"]:
        return 0
    return 1 if not result.wasSuccessful() else 5


if __name__ == "__main__":
    raise SystemExit(main())
