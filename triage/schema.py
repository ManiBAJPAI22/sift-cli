"""Unified finding schema + stable content fingerprint.

The fingerprint is the backbone of cross-run identity: it must stay the same
when unrelated lines shift (an added import) and change only when the offending
code itself changes. So we hash *content*, never line numbers:

    detector_id + repo-relative file + enclosing function + normalized snippet

`normalize_snippet` strips comments and collapses whitespace so reformatting
alone doesn't re-trigger triage.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

# Severity ordering for sorting / gating.
SEVERITY_RANK = {
    "high": 4,
    "medium": 3,
    "low": 2,
    "informational": 1,
    "info": 1,
    "unknown": 0,
}

VALID_VERDICTS = {"true_positive", "false_positive", "needs_human"}


def normalize_snippet(code: str) -> str:
    """Whitespace/comment-insensitive form of a code snippet for fingerprinting.

    Removes // line comments and /* */ block comments, collapses runs of
    whitespace to a single space, and strips. Two snippets that differ only in
    formatting or comments produce the same normalized string.
    """
    if not code:
        return ""
    # Strip block comments first, then line comments.
    code = re.sub(r"/\*.*?\*/", " ", code, flags=re.DOTALL)
    code = re.sub(r"//[^\n]*", " ", code)
    code = re.sub(r"\s+", " ", code)
    return code.strip()


def compute_fingerprint(
    detector_id: str,
    file_path: str,
    function: str,
    snippet: str,
) -> str:
    """Stable 16-hex-char identity for a finding. Order-fixed, content-based."""
    basis = "\x1f".join(
        [
            (detector_id or "").strip(),
            (file_path or "").strip(),
            (function or "").strip(),
            normalize_snippet(snippet),
        ]
    )
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


@dataclass
class Finding:
    """One normalized scanner finding, enriched and (later) adjudicated."""

    # --- identity / source ---
    detector_id: str
    tool: str  # "slither" | "aderyn"
    file_path: str
    severity: str = "unknown"
    title: str = ""
    message: str = ""
    function: str = ""
    line: Optional[int] = None  # advisory only — never part of the fingerprint
    snippet: str = ""
    cwe: str = ""

    # --- enrichment (filled by enrich.py) ---
    context: str = ""  # function body + call-graph neighborhood

    # --- identity (computed) ---
    fingerprint: str = ""

    # --- adjudication (filled by adjudicate.py) ---
    verdict: str = ""  # one of VALID_VERDICTS
    confidence: float = 0.0
    reasoning: str = ""
    exploit_scenario: str = ""
    suggested_fix: str = ""
    adjudicated_by: str = ""  # model name@digest, or "" if not adjudicated

    # --- bucketing (filled by ledger.py) ---
    state: str = ""  # "new" | "known" | "resolved"
    human_override: bool = False

    def ensure_fingerprint(self) -> str:
        if not self.fingerprint:
            self.fingerprint = compute_fingerprint(
                self.detector_id, self.file_path, self.function, self.snippet
            )
        return self.fingerprint

    @property
    def severity_rank(self) -> int:
        return SEVERITY_RANK.get((self.severity or "unknown").lower(), 0)

    @property
    def is_real(self) -> bool:
        return self.verdict == "true_positive"

    @property
    def is_false_positive(self) -> bool:
        return self.verdict == "false_positive"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Finding":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})
