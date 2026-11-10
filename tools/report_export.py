"""Export a separate UTF-8 report with best-effort masking, not a security scan.

Raw evidence and immutable snapshots are never rewritten. Review the exported
file manually before sharing: names, identifiers, obfuscated/unknown secrets and
other sensitive context cannot be comprehensively detected by these patterns.
Only the Python standard library is required.
"""
from __future__ import annotations

import argparse
from collections.abc import Iterable
import json
import os
from pathlib import Path
import re
import sys


class ExportError(Exception):
    """The report could not be safely exported; no report should be published."""


HOME = re.compile(r"/(?:home|Users)/[^/\s\"'<>\\\[\]{}(),;:]+")
EMAIL = re.compile(
    r"(?<![\w.+-])[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)*\.[A-Za-z]{2,63}\b"
)
INTERNATIONAL_PHONE = re.compile(r"(?<![\w+])\+\d(?:[(). -]*\d){7,14}(?![\w]|[(). -]*\d)")
FORMATTED_PHONE = re.compile(r"(?<!\w)(?:\([2-9]\d{2}\)[ .-]?|[2-9]\d{2}[.-])\d{3}[.-]\d{4}(?!\w)")
LABELED_PHONE = re.compile(
    r"(?P<prefix>\b(?:phone|telephone|mobile|tel)[\"']?[ \t]*[:=][ \t]*[\"']?)"
    r"\+?\d(?:[(). -]*\d){6,14}(?![\w]|[(). -]*\d)", re.IGNORECASE
)
BATTLETAG = re.compile(r"(?<!\w)[A-Za-z][A-Za-z0-9_]{2,11}#[0-9]{4,10}(?!\w)")
KNOWN_TOKEN = re.compile(
    r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"
    r"|sk-(?:proj-|ant-)?[A-Za-z0-9_-]{16,}|xox[abprs]-[A-Za-z0-9-]{16,}"
    r"|(?:AKIA|ASIA)[A-Z0-9]{16}"
    r"|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,})\b"
)
TOKEN_MARKER = re.compile(r"\b(?:gh[pousr]_|github_pat_|sk-(?:proj-|ant-)?|xox[abprs]-|(?:AKIA|ASIA)[A-Z0-9]{8,}|eyJ[A-Za-z0-9_-]+\.)")
BEARER = re.compile(r"\bBearer[ \t]+[A-Za-z0-9._~+/-]+=*", re.IGNORECASE)
SECRET_FIELD = (
    r"(?:api[_-]?key|access[_-]?token|refresh[_-]?token|auth[_-]?token|token|"
    r"password|secret|client[_-]?secret|authorization|cookie|set-cookie)"
)
SECRET_PREFIX = rf"\b{SECRET_FIELD}[\"']?[ \t]*(?::(?!=)|=(?!=))[ \t]*"
SECRET_MARKER = re.compile(SECRET_PREFIX, re.IGNORECASE)
SECRET_ASSIGNMENT = re.compile(
    rf"(?P<prefix>{SECRET_PREFIX})"
    r"(?P<value>\"(?:\\.|[^\"\\\r\n])*\"|'(?:\\.|[^'\\\r\n])*'|<[^<>\r\n]+>|[A-Za-z0-9_./+~=:-]+)"
    r"(?=$|[\s,;}\]])",
    re.IGNORECASE,
)
SAFE_SECRET_VALUES = {"", "none", "null", "true", "false", "<token>", "<redacted>", "<secret>", "<cookie>"}
NOTICE = {"masking": "best-effort", "comprehensive_security_scan": False, "manual_review_required": True}


def _secret_value(match: re.Match) -> str:
    value = match["value"]
    unquoted = value[1:-1] if value[:1] in {"'", '"'} else value
    if unquoted.lower() in SAFE_SECRET_VALUES:
        return match[0]
    quote = value[0] if value[:1] in {"'", '"'} else ""
    return match["prefix"] + quote + "<token>" + quote


def _project_root(value: Path | str | None) -> str | None:
    if value is None:
        return None
    root = str(Path(value).resolve())
    if root in {os.path.sep, "/home", "/Users"}:
        raise ExportError("Project root must identify a specific project directory")
    return root


def redact_report(text: str, project_root: Path | str | None = None,
                  sensitive_values: Iterable[str] = ()) -> str:
    """Mask only recognizable patterns and explicitly provided literal values.

    Digests, task/version IDs, plain numbers and ordinary code are not generic
    PII patterns. Supply additional identifiers locally via sensitive_values.
    """
    if any(ord(char) < 32 and char not in "\t\r\n" for char in text) or "\x7f" in text:
        raise ExportError("Input must be UTF-8 text, not binary/control-character data")
    if isinstance(sensitive_values, (str, bytes)):
        raise ExportError("Sensitive values must be a collection of literal strings")
    values = list(sensitive_values)
    if any(not isinstance(value, str) or not value or not value.strip() for value in values):
        raise ExportError("Sensitive values must be non-empty literal strings")
    root = _project_root(project_root)
    root_pattern = re.compile(re.escape(root) + r"(?![\w.-])") if root else None
    if root:
        text = root_pattern.sub("<project>", text)
    for value in sorted(set(values), key=lambda value: (-len(value), value)):
        text = text.replace(value, "<redacted>")
    text = HOME.sub("<home>", text)
    text = EMAIL.sub("<email>", text)
    text = LABELED_PHONE.sub(lambda match: match["prefix"] + "<phone>", text)
    text = INTERNATIONAL_PHONE.sub("<phone>", text)
    text = FORMATTED_PHONE.sub("<phone>", text)
    text = BATTLETAG.sub("<battletag>", text)
    text = KNOWN_TOKEN.sub("<token>", text)
    text = BEARER.sub("Bearer <token>", text)
    text = SECRET_ASSIGNMENT.sub(_secret_value, text)

    # Fail closed on recognizable leftovers, not a claim to detect arbitrary PII.
    patterns = (HOME, EMAIL, LABELED_PHONE, INTERNATIONAL_PHONE, FORMATTED_PHONE,
                BATTLETAG, KNOWN_TOKEN, TOKEN_MARKER, BEARER)
    if any(pattern.search(text) for pattern in patterns):
        raise ExportError("Recognizable sensitive material remains; review raw evidence locally")
    if re.search(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", text):
        raise ExportError("Private-key material requires a separate manual review")
    if (root_pattern and root_pattern.search(text)) or any(value in text for value in values):
        raise ExportError("An explicit sensitive value or project path remains")
    for marker in SECRET_MARKER.finditer(text):
        assignment = SECRET_ASSIGNMENT.match(text, marker.start())
        if assignment:
            value = assignment["value"]
            unquoted = value[1:-1] if value[:1] in {"'", '"'} else value
            if unquoted.lower() in SAFE_SECRET_VALUES:
                continue
        remainder = text[marker.end():]
        if not remainder or remainder.startswith(("\r", "\n")):
            continue  # A field name alone is not a raw secret value.
        if re.match(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*(?:\(|\[)", remainder):
            continue  # An ordinary code expression, not a literal credential.
        raise ExportError("An unrecognized secret field requires local manual review")
    return text


def _plain_path(value: Path | str) -> Path:
    path = Path(value)
    if ".." in path.parts:
        raise ExportError("Report paths must not contain parent traversal")
    path = path.absolute()
    if any(item.is_symlink() for item in (path, *path.parents)):
        raise ExportError("Report paths must not cross symlinks")
    return path


def _protected_output(path: Path) -> bool:
    parts = path.parts
    return (
        path.name == "manifest.json"
        or "payload" in parts
        or any(parts[index:index + 2] == (".local", "drafts") for index in range(len(parts) - 1))
        or any((parent / "manifest.json").exists() and (parent / "payload").is_dir()
               for parent in path.parents)
    )


def export_report(input_path: Path | str, output_path: Path | str,
                  project_root: Path | str | None = None,
                  sensitive_values: Iterable[str] = ()) -> dict:
    """Create a new private report; never overwrite raw input or existing output."""
    source = _plain_path(input_path)
    output = _plain_path(output_path)
    if source == output:
        raise ExportError("Output must differ from raw input")
    if _protected_output(output):
        raise ExportError("Output must be outside immutable snapshots, payloads and manifests")
    if not source.is_file():
        raise ExportError("Input must be a regular file")
    if output.exists():
        raise ExportError("Output must be a new file; refusing to overwrite")
    if not output.parent.is_dir():
        raise ExportError("Output parent must already be a real directory")
    try:
        text = source.read_bytes().decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ExportError("Input must be valid UTF-8 text") from error
    encoded = redact_report(text, project_root, sensitive_values).encode("utf-8", errors="strict")
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    return dict(NOTICE)


def _sensitive_file(path: Path) -> list[str]:
    path = _plain_path(path)
    if not path.is_file():
        raise ExportError("Sensitive-values file must be a regular UTF-8 JSON file")
    try:
        values = json.loads(path.read_bytes().decode("utf-8", errors="strict"))
    except (UnicodeError, ValueError) as error:
        raise ExportError("Sensitive-values file must contain a UTF-8 JSON array of strings") from error
    if not isinstance(values, list) or any(not isinstance(value, str) or not value.strip() for value in values):
        raise ExportError("Sensitive-values file must contain an array of non-empty strings")
    return values


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1],
                        help="project path to replace with <project>")
    parser.add_argument("--sensitive-file", type=Path,
                        help="local UTF-8 JSON array of additional literal values to mask; never shared")
    args = parser.parse_args(argv)
    try:
        values = _sensitive_file(args.sensitive_file) if args.sensitive_file else []
        if args.sensitive_file and args.output.absolute() == args.sensitive_file.absolute():
            raise ExportError("Output must not overwrite the sensitive-values file")
        result = export_report(args.input, args.output, args.root, values)
    except (ExportError, OSError) as error:
        # Do not echo raw paths, contents or secret values in CLI diagnostics.
        message = str(error) if isinstance(error, ExportError) else "Report I/O failed; inspect paths locally"
        print(json.dumps({"error": message}), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
