"""Local review snapshots. No command commits, pushes, or applies a proposal.

Python 3.11+ on Linux/macOS; only the standard library is required.
Tests run in a disposable copy with a limited environment, NOT an OS sandbox.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from zoneinfo import ZoneInfo

TEST_TIMEOUT_SECONDS = 60


class WorkflowError(Exception):
    """A proposal failed a local integrity or decision check."""


def canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def relative_path(value: str) -> str:
    path = PurePosixPath(value)
    forbidden = {".git", ".local", ".venv", "__pycache__"}
    if (
        not value
        or path.is_absolute()
        or str(path) != value
        or ".." in path.parts
        or "\\" in value
        or ":" in value
        or any(part in forbidden for part in path.parts)
        or any(part.startswith(".env") and part != ".env.example" for part in path.parts)
        or path.suffix in {".pem", ".key"}
    ):
        raise WorkflowError(f"Unsafe or private proposal path: {value!r}")
    return value


def _json_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _json_constant(value: str):
    raise ValueError("Nonstandard JSON number")


def load_json(path: Path) -> dict:
    try:
        result = json.loads(path.read_text(encoding="utf-8"),
                            object_pairs_hook=_json_object, parse_constant=_json_constant)
    except (OSError, ValueError) as error:
        raise WorkflowError(f"Cannot read JSON: {path.name}: {error}") from error
    if not isinstance(result, dict):
        raise WorkflowError(f"Expected a JSON object: {path.name}")
    return result


class Workflow:
    def __init__(self, root: Path | str):
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise WorkflowError("Project root must already exist")
        self.local = self.root / ".local"
        self.state_path = self.local / "state.json"

    def _safe_local(self) -> None:
        if self.local.is_symlink():
            raise WorkflowError("Private state must not be a symlink")
        self.local.mkdir(mode=0o700, exist_ok=True)
        self.local.chmod(0o700)
        if self.state_path.is_symlink():
            raise WorkflowError("State file must not be a symlink")

    @contextmanager
    def _lock(self):
        self._safe_local()
        lock = self.local / "workflow.lock"
        if lock.is_symlink():
            raise WorkflowError("Lock must not be a symlink")
        with lock.open("a", encoding="utf-8") as handle:
            os.chmod(lock, 0o600)
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def _state(self) -> dict:
        if self.local.is_symlink() or self.state_path.is_symlink():
            raise WorkflowError("Private state must not be a symlink")
        if not self.state_path.exists():
            result = {"schema_version": 1, "drafts": {}}
        else:
            result = load_json(self.state_path)
        if type(result.get("schema_version")) is not int or result["schema_version"] != 1 or not isinstance(result.get("drafts"), dict):
            raise WorkflowError("Unsupported state format")
        keys = set()
        for task_id, item in result["drafts"].items():
            self._identifiers(task_id, "v1")
            if not isinstance(item, dict) or not isinstance(item.get("task_key"), str) or not re.fullmatch(r"EP-\d{3,}", item["task_key"]):
                raise WorkflowError("Invalid task key in journal")
            if item["task_key"] in keys:
                raise WorkflowError("Duplicate task key in journal")
            keys.add(item["task_key"])
            versions = item.get("versions")
            if not isinstance(versions, list) or not versions:
                raise WorkflowError("Journal tasks must have non-empty versions")
            for number, record in enumerate(versions, 1):
                self._validate_record(task_id, record, number, number == len(versions))
        self._snapshot_inventory(result)
        return result

    @staticmethod
    def _validate_record(task_id: str, record: dict, number: int, latest: bool) -> None:
        if not isinstance(record, dict) or record.get("version") != f"v{number}":
            raise WorkflowError("Journal versions must be contiguous and ordered")
        if "task_id" in record or "task_key" in record:
            raise WorkflowError("Version records must not override task identity")
        status = record.get("status")
        if not isinstance(status, str) or status not in {"pending", "approved", "rejected", "revision_requested", "superseded"}:
            raise WorkflowError("Unknown journal status; refusing to advance the queue")
        if (latest and status == "superseded") or (not latest and status != "superseded"):
            raise WorkflowError("Invalid latest/superseded journal status")
        for field in ("fingerprint", "verification_sha256"):
            if field == "fingerprint" or field in record:
                if not isinstance(record.get(field), str) or not re.fullmatch(r"[0-9a-f]{64}", record[field]):
                    raise WorkflowError("Invalid journal hash")
        if "tests_passed" in record and type(record["tests_passed"]) is not bool:
            raise WorkflowError("Invalid test result in journal")
        if ("tests_passed" in record) != ("verification_sha256" in record):
            raise WorkflowError("Incomplete test result in journal")

        def valid_time(value):
            try:
                return isinstance(value, str) and datetime.fromisoformat(value).utcoffset() is not None
            except ValueError:
                return False

        if not valid_time(record.get("created_at")):
            raise WorkflowError("Invalid creation timestamp in journal")
        decision = record.get("decision")
        actions = {"approve": "Одобряю", "reject": "Отклоняю", "revise": "Доработать"}
        expected_action = {"approved": "approve", "rejected": "reject", "revision_requested": "revise"}.get(status)
        if status == "pending" and "decision" in record:
            raise WorkflowError("Pending journal record must not contain a decision")
        if expected_action or "decision" in record:
            if not isinstance(decision, dict) or not isinstance(decision.get("action"), str) or decision["action"] not in actions:
                raise WorkflowError("Missing or invalid decision in journal")
            action = decision["action"]
            if expected_action and action != expected_action:
                raise WorkflowError("Journal decision/status mismatch")
            if decision.get("evidence") != f"{actions[action]} {task_id} v{number}" or not valid_time(decision.get("recorded_at")):
                raise WorkflowError("Invalid decision evidence in journal")
            if action == "approve" and (
                not isinstance(decision.get("verification_sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", decision["verification_sha256"])
                or "verification_sha256" not in record
            ):
                raise WorkflowError("Approval lacks its historical test evidence hash")

    def _snapshot_inventory(self, state: dict) -> None:
        """Do not silently restart an empty queue after journal loss/truncation."""
        directory = self.local / "drafts"
        if directory.is_symlink():
            raise WorkflowError("Snapshot paths must not cross symlinks")
        expected = {(task_id, record["version"])
                    for task_id, item in state["drafts"].items() for record in item["versions"]}
        actual = set()
        if directory.exists():
            if not directory.is_dir():
                raise WorkflowError("Snapshot inventory must be a directory")
            for task in directory.iterdir():
                if task.is_symlink() or not task.is_dir():
                    raise WorkflowError("Invalid task directory in snapshot inventory")
                for version in task.iterdir():
                    if version.is_symlink() or not version.is_dir():
                        raise WorkflowError("Invalid version directory in snapshot inventory")
                    actual.add((task.name, version.name))
        if actual != expected:
            raise WorkflowError("Journal/snapshot inventory mismatch; manual recovery required")

    def _save(self, state: dict) -> None:
        descriptor, name = tempfile.mkstemp(prefix="state-", suffix=".json", dir=self.local)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(state, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(name, 0o600)
            os.replace(name, self.state_path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def init_state(self) -> dict:
        with self._lock():
            state = self._state()
            if not self.state_path.exists():
                self._save(state)
        return self.status()

    def _head(self) -> str | None:
        if not (self.root / ".git").exists():
            return None
        result = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"], cwd=self.root,
            capture_output=True, text=True, timeout=10, check=False,
        )
        return result.stdout.strip() if result.returncode == 0 else None

    def _destination(self, name: str) -> Path:
        name = relative_path(name)
        target = self.root / name
        for item in (target, *target.parents):
            if item == self.root:
                break
            if item.is_symlink():
                raise WorkflowError(f"Destination crosses a symlink: {name}")
        if target.exists() and not target.is_file():
            raise WorkflowError(f"Destination is not a regular file: {name}")
        return target

    @staticmethod
    def _files(directory: Path) -> dict[str, Path]:
        if directory.is_symlink() or not directory.is_dir():
            raise WorkflowError("Payload must be a real directory")
        files = {}
        for path in sorted(directory.rglob("*")):
            if path.is_symlink():
                raise WorkflowError("Symlinks are not allowed in payloads")
            if path.is_file():
                name = relative_path(path.relative_to(directory).as_posix())
                files[name] = path
        return files

    @staticmethod
    def _identifiers(task_id: str, version: str) -> None:
        if not isinstance(task_id, str) or not re.fullmatch(r"GH-\d{8}", task_id):
            raise WorkflowError("Task ID must have form GH-YYYYMMDD")
        try:
            datetime.strptime(task_id[3:], "%Y%m%d")
        except ValueError as error:
            raise WorkflowError("Invalid task date") from error
        if not isinstance(version, str) or not re.fullmatch(r"v[1-9]\d*", version):
            raise WorkflowError("Version must have form v1, v2, ...")

    def _directory(self, task_id: str, version: str) -> Path:
        self._identifiers(task_id, version)
        directory = self.local / "drafts" / task_id / version
        for path in (directory, *directory.parents):
            if path == self.root:
                break
            if path.is_symlink():
                raise WorkflowError("Snapshot paths must not cross symlinks")
        return directory

    @staticmethod
    def _entry(state: dict, task_id: str, version: str) -> tuple[dict, dict]:
        item = state["drafts"].get(task_id)
        if item is None:
            raise WorkflowError("Unknown task ID")
        for record in item["versions"]:
            if record["version"] == version:
                return item, record
        raise WorkflowError("Unknown task version")

    @staticmethod
    def _latest_tasks(state: dict) -> list[dict]:
        items = []
        for task_id, item in sorted(state["drafts"].items()):
            latest = item["versions"][-1]
            items.append({**latest, "task_id": task_id, "task_key": item["task_key"]})
        return items

    def _gate(self, state: dict) -> dict:
        # Approval is a historical resolution, not current publication readiness.
        # verify() still checks integrity/base/evidence before any use of approval.
        # A real subsequent commit must not re-open all previously resolved tasks.
        blockers = [{field: item[field] for field in ("task_id", "task_key", "version", "status")}
                    for item in self._latest_tasks(state) if item["status"] != "approved"]
        return {"blocked": bool(blockers), "blocker_count": len(blockers),
                "active_task": blockers[0] if blockers else None, "blockers": blockers}

    def status(self) -> dict:
        state = self._state()
        items = self._latest_tasks(state)
        return {
            "schema_version": 1, "tasks": items,
            "status_counts": dict(Counter(item["status"] for item in items)),
            "publication_supported": False,
            **self._gate(state),
        }

    def _next_task(self, state: dict) -> dict:
        backlog = load_json(self.root / "BACKLOG.json")
        items = backlog.get("items")
        if type(backlog.get("schema_version")) is not int or backlog["schema_version"] != 1 or not isinstance(items, list):
            raise WorkflowError("Unsupported backlog format")
        if any(not isinstance(item, dict) or not isinstance(item.get("key"), str) for item in items):
            raise WorkflowError("Invalid backlog item")
        keys = [item.get("key", "") for item in items]
        if len(keys) != len(set(keys)) or any(
            not re.fullmatch(r"EP-\d{3,}", key) for key in keys
        ):
            raise WorkflowError("Backlog keys must be unique EP-NNN identifiers")
        used = {item["task_key"] for item in state["drafts"].values()}
        gate = self._gate(state)
        exhausted = all(key in used for key in keys)
        if gate["blocked"]:
            return {"seed_queue_exhausted": exhausted, "task": None, **gate}
        for item in items:
            if item["key"] not in used:
                return {"seed_queue_exhausted": False, "task": item, **gate}
        number = max([int(key[3:]) for key in (*keys, *used)], default=0) + 1
        return {
            "seed_queue_exhausted": True,
            "task": {"key": f"EP-{number:03d}", "topic": "integration/review",
                     "title": "Propose the next small exercise within the accepted focus"},
            **gate,
        }

    def next_task(self) -> dict:
        return self._next_task(self._state())

    def draft(self, source: Path | str, task_key: str, task_id: str | None = None) -> dict:
        if not isinstance(task_key, str) or not re.fullmatch(r"EP-\d{3,}", task_key):
            raise WorkflowError("Task key must have form EP-NNN")
        if task_id is None:
            task_id = datetime.now(ZoneInfo("America/Vancouver")).strftime("GH-%Y%m%d")
        self._identifiers(task_id, "v1")
        source = Path(source)
        files = self._files(source)
        if not files:
            raise WorkflowError("An empty payload is not a reviewable change")
        with self._lock():
            state = self._state()
            item = state["drafts"].get(task_id)
            if item is not None and item["task_key"] != task_key:
                raise WorkflowError("One task per local date; revise the existing task instead")
            if item is None and any(
                entry["task_key"] == task_key for entry in state["drafts"].values()
            ):
                raise WorkflowError("Task already proposed; revise its original task ID")
            selection = self._next_task(state)
            active = selection["active_task"]
            if active and (item is None or task_id > active["task_id"]):
                raise WorkflowError(
                    f"Approval gate blocked by {active['task_id']} {active['version']}; "
                    "resolve or revise the earliest unresolved task first"
                )
            if item is None and task_key != selection["task"]["key"]:
                raise WorkflowError("Task key must match next; out-of-order drafts are not allowed")
            version = f"v{len(item['versions']) + 1 if item else 1}"
            directory = self._directory(task_id, version)
            if directory.exists():
                raise WorkflowError("Snapshot already exists; refusing to overwrite it")
            manifest_files = []
            contents = {}
            for name, path in files.items():
                content = path.read_bytes()
                contents[name] = content
                try:
                    content.decode("utf-8")
                except UnicodeDecodeError as error:
                    raise WorkflowError("Initial review bundles support UTF-8 text only") from error
                destination = self._destination(name)
                manifest_files.append({
                    "path": name, "sha256": digest(content),
                    "before_sha256": digest(destination.read_bytes()) if destination.exists() else None,
                })
            manifest = {"schema_version": 1, "task_id": task_id, "task_key": task_key,
                        "version": version, "base_commit": self._head(), "files": manifest_files}
            fingerprint = digest(canonical(manifest))
            directory.mkdir(mode=0o700, parents=True)
            try:
                for name, content in contents.items():
                    destination = directory / "payload" / name
                    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                    destination.write_bytes(content)
                    destination.chmod(0o400)
                manifest_path = directory / "manifest.json"
                manifest_path.write_text(
                    json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                manifest_path.chmod(0o400)
                if item is None:
                    item = {"task_key": task_key, "versions": []}
                    state["drafts"][task_id] = item
                if item["versions"]:
                    item["versions"][-1]["status"] = "superseded"
                item["versions"].append({
                    "version": version, "fingerprint": fingerprint,
                    "status": "pending", "created_at": timestamp(),
                })
                self._save(state)
            except BaseException:
                shutil.rmtree(directory)
                raise
        return {"task_id": task_id, "task_key": task_key, "version": version,
                "fingerprint": fingerprint, "status": "pending",
                "snapshot_dir": str(directory), "files": list(files)}

    def _test_evidence_valid(self, directory: Path, record: dict, fingerprint: str) -> bool:
        report_path = directory / "verification.json"
        if report_path.is_symlink():
            return False
        try:
            report = load_json(report_path)
        except WorkflowError:
            return False
        driver = Path(__file__).resolve().with_name("unittest_driver.py")
        return (
            digest(canonical(report)) == record.get("verification_sha256")
            and report.get("fingerprint") == fingerprint
            and report.get("runner_sha256") == digest(driver.read_bytes())
            and report.get("returncode") == 0
            and report.get("tests_run", 0) > 0
            and report.get("tests_succeeded", 0) > 0
            and report.get("driver_completed") is True
            and report.get("timed_out") is False
            and report.get("passed") is True
        )

    def verify(self, task_id: str, version: str) -> dict:
        directory = self._directory(task_id, version)
        state = self._state()
        item, record = self._entry(state, task_id, version)
        manifest_path = directory / "manifest.json"
        if manifest_path.is_symlink():
            raise WorkflowError("Manifest must not be a symlink")
        manifest = load_json(manifest_path)
        fingerprint = digest(canonical(manifest))
        if fingerprint != record["fingerprint"]:
            raise WorkflowError("Manifest fingerprint changed")
        if (manifest.get("task_id"), manifest.get("task_key"), manifest.get("version")) != (
            task_id, item["task_key"], version
        ):
            raise WorkflowError("Snapshot identifiers do not match the journal")
        files = self._files(directory / "payload")
        entries = manifest.get("files", [])
        names = [entry["path"] for entry in entries]
        if len(names) != len(set(names)) or set(files) != set(names):
            raise WorkflowError("Snapshot file list changed")
        changed_targets = []
        for entry in entries:
            name = entry["path"]
            if digest(files[name].read_bytes()) != entry["sha256"]:
                raise WorkflowError(f"Snapshot content changed: {name}")
            target = self._destination(name)
            current = digest(target.read_bytes()) if target.exists() else None
            if current != entry["before_sha256"]:
                changed_targets.append(name)
        current_head = self._head()
        base_matches = current_head == manifest["base_commit"] and not changed_targets
        latest = item["versions"][-1]["version"] == version
        evidence_valid = self._test_evidence_valid(directory, record, fingerprint)
        return {
            "task_id": task_id, "version": version, "status": record["status"],
            "fingerprint": fingerprint, "integrity": True,
            "base_matches": base_matches,
            "base_commit": manifest["base_commit"], "current_commit": current_head,
            "changed_targets": changed_targets,
            "latest": latest,
            "test_evidence_valid": evidence_valid,
            "local_approval_valid": latest and record["status"] == "approved"
                                    and base_matches and evidence_valid,
        }

    def run_tests(self, task_id: str, version: str, start_dir: str) -> dict:
        verified = self.verify(task_id, version)
        start_dir = relative_path(start_dir)
        directory = self._directory(task_id, version)
        if not (directory / "payload" / start_dir).is_dir():
            raise WorkflowError("Test start directory must exist inside the payload")
        scratch = Path(os.environ.get("TMPDIR", str(self.local / "tmp")))
        scratch.mkdir(mode=0o700, parents=True, exist_ok=True)
        driver = Path(__file__).resolve().with_name("unittest_driver.py")
        runner_sha256 = digest(driver.read_bytes())
        with tempfile.TemporaryDirectory(prefix="engineering-check-", dir=scratch) as name:
            workspace = Path(name)
            shutil.copytree(directory / "payload", workspace / "payload")
            (workspace / "home").mkdir()
            (workspace / "tmp").mkdir()
            environment = {
                "PATH": os.environ.get("PATH", os.defpath), "LANG": "C.UTF-8",
                "HOME": str(workspace / "home"), "TMPDIR": str(workspace / "tmp"),
            }
            counters_path = workspace / "driver_result.json"
            command = [sys.executable, "-I", str(driver), "--start-dir", start_dir,
                       "--report", str(counters_path)]
            process = subprocess.Popen(
                command, cwd=workspace / "payload", env=environment,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                start_new_session=True,
            )
            timed_out = False
            try:
                stdout, stderr = process.communicate(timeout=TEST_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                timed_out = True
                # Kill the isolated test process group, including ordinary descendants.
                # A process that deliberately escapes the group is outside this guarantee.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                stdout, stderr = process.communicate(timeout=5)
                stderr += f"\nTest execution exceeded the {TEST_TIMEOUT_SECONDS}-second limit.\n"
            returncode = process.returncode
            try:
                counters = load_json(counters_path)
            except WorkflowError:
                counters = {}
        driver_completed = counters.get("driver_completed") is True
        tests_run = counters.get("tests_run", 0) if driver_completed else 0
        tests_skipped = counters.get("tests_skipped", 0) if driver_completed else 0
        expected_failures = counters.get("expected_failures", 0) if driver_completed else 0
        tests_succeeded = counters.get("tests_succeeded", 0) if driver_completed else 0
        report = {
            "fingerprint": verified["fingerprint"], "run_at": timestamp(),
            "command": command, "returncode": returncode, "tests_run": tests_run,
            "tests_skipped": tests_skipped, "expected_failures": expected_failures,
            "tests_succeeded": tests_succeeded,
            "driver_completed": driver_completed, "runner_sha256": runner_sha256,
            "timed_out": timed_out, "timeout_seconds": TEST_TIMEOUT_SECONDS,
            "passed": returncode == 0 and not timed_out and driver_completed
                      and counters.get("passed") is True and tests_succeeded > 0,
            "stdout": stdout, "stderr": stderr,
            "is_os_sandbox": False,
        }
        with self._lock():
            self.verify(task_id, version)
            state = self._state()
            _, record = self._entry(state, task_id, version)
            report_path = directory / "verification.json"
            if report_path.is_symlink():
                raise WorkflowError("Verification report must not be a symlink")
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            report_path.chmod(0o600)
            record["verification_sha256"] = digest(canonical(report))
            record["tests_passed"] = report["passed"]
            self._save(state)
        return report

    def decide(self, task_id: str, version: str, fingerprint: str, action: str, evidence: str) -> dict:
        expected_words = {"approve": "Одобряю", "reject": "Отклоняю", "revise": "Доработать"}
        if action not in expected_words:
            raise WorkflowError("Unknown decision")
        expected = f"{expected_words[action]} {task_id} {version}"
        if evidence != expected:
            raise WorkflowError(f"Decision evidence must match the actual user command: {expected}")
        with self._lock():
            state = self._state()
            item, record = self._entry(state, task_id, version)
            if item["versions"][-1]["version"] != version or record["status"] != "pending":
                raise WorkflowError("Only the latest pending revision can receive a decision")
            if fingerprint != record["fingerprint"]:
                raise WorkflowError("Approval/rejection fingerprint does not match the proposal")
            if action == "approve":
                verified = self.verify(task_id, version)
                if not verified["base_matches"]:
                    raise WorkflowError("Base commit or destination files changed; prepare a new revision")
                if not verified["test_evidence_valid"]:
                    raise WorkflowError("Matching, passing, non-empty test evidence is required")
            record["status"] = {"approve": "approved", "reject": "rejected", "revise": "revision_requested"}[action]
            record["decision"] = {"action": action, "evidence": evidence, "recorded_at": timestamp()}
            if action == "approve":
                record["decision"]["verification_sha256"] = record["verification_sha256"]
            self._save(state)
            return {"task_id": task_id, "version": version, "status": record["status"],
                    "fingerprint": fingerprint, "publication_performed": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("init-state", "status", "next"):
        commands.add_parser(name)
    draft = commands.add_parser("draft")
    draft.add_argument("--task-key", required=True)
    draft.add_argument("--source", type=Path, required=True)
    draft.add_argument("--task-id")
    for name in ("verify", "test", "decide"):
        child = commands.add_parser(name)
        child.add_argument("--task-id", required=True)
        child.add_argument("--version", required=True)
        if name == "test":
            child.add_argument("--start-dir", required=True)
        if name == "decide":
            child.add_argument("--fingerprint", required=True)
            child.add_argument("--action", choices=("approve", "reject", "revise"), required=True)
            child.add_argument("--evidence", required=True)
    args = parser.parse_args(argv)
    try:
        workflow = Workflow(args.root)
        if args.command == "init-state":
            result = workflow.init_state()
        elif args.command == "status":
            result = workflow.status()
        elif args.command == "next":
            result = workflow.next_task()
        elif args.command == "draft":
            result = workflow.draft(args.source, args.task_key, args.task_id)
        elif args.command == "verify":
            result = workflow.verify(args.task_id, args.version)
        elif args.command == "test":
            result = workflow.run_tests(args.task_id, args.version, args.start_dir)
        else:
            result = workflow.decide(args.task_id, args.version, args.fingerprint, args.action, args.evidence)
    except (WorkflowError, OSError, subprocess.SubprocessError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if args.command == "test" and not result["passed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
