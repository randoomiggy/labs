"""Summarize the exact EP-001 synthetic log format in one pass.

This module performs no file, network, or subprocess operations.
"""
from collections.abc import Iterable
import re
from typing import TypedDict


_LINE = re.compile(
    r"[0-9]+ [A-Z]+ /[A-Za-z0-9/_-]* (?P<status>[1-5][0-9]{2})"
)


class Summary(TypedDict):
    """Static shape of the returned dictionary, not a runtime wrapper."""

    valid_lines: int
    malformed_lines: int
    status_counts: dict[int, int]


def summarize(lines: Iterable[str]) -> Summary:
    """Count valid/malformed strings and return sparse integer status counts.

    Remove at most one terminal LF or CRLF, not arbitrary whitespace.
    Non-string items raise TypeError; errors from the input iterator propagate.
    No partial summary is returned if iteration fails.
    """
    valid_lines = 0
    malformed_lines = 0
    status_counts: dict[int, int] = {}

    for line in lines:
        if not isinstance(line, str):
            raise TypeError("each input item must be a string")
        if line.endswith("\r\n"):
            line = line[:-2]
        elif line.endswith("\n"):
            line = line[:-1]

        match = _LINE.fullmatch(line)
        if match is None:
            malformed_lines += 1
            continue

        status = int(match.group("status"))
        valid_lines += 1
        status_counts[status] = status_counts.get(status, 0) + 1

    return {
        "valid_lines": valid_lines,
        "malformed_lines": malformed_lines,
        "status_counts": status_counts,
    }
