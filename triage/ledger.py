"""Fingerprint-keyed verdict ledger — the cross-run memory.

This is what makes triage scale and stay consistent:

  * Only NEW findings are sent to the model. KNOWN ones reuse their stored
    verdict (zero tokens). RESOLVED ones (in ledger, gone from this run) are
    marked fixed.
  * A `human_override` verdict is sticky — it survives re-runs and is never
    overwritten by the model. It only loses authority when the underlying code
    changes (which changes the fingerprint, making it a NEW finding again).

Stored as plain JSON (`.audit-ledger.json`) so it diffs cleanly in git and can
be hand-edited. No DB dependency.
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any

from .schema import Finding

DEFAULT_LEDGER = ".audit-ledger.json"
SCHEMA_VERSION = 1


def load(path: str = DEFAULT_LEDGER) -> dict[str, dict[str, Any]]:
    """Return the fingerprint -> record map. Empty dict if absent/corrupt."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    return doc.get("findings", {}) if isinstance(doc, dict) else {}


def save(records: dict[str, dict[str, Any]], path: str = DEFAULT_LEDGER) -> None:
    """Atomically write the ledger (temp file + rename) so a crash mid-write
    can't corrupt it."""
    doc = {"schema_version": SCHEMA_VERSION, "findings": records}
    body = json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False)
    d = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".ledger-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(body)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def bucket(
    findings: list[Finding], records: dict[str, dict[str, Any]], run_stamp: str
) -> tuple[list[Finding], list[Finding], list[dict[str, Any]]]:
    """Split this run's findings against the ledger.

    Returns (new, known, resolved):
      * new     — fingerprint not in ledger; must be adjudicated.
      * known   — already adjudicated; verdict + reasoning copied onto the
                  Finding from the ledger (model not called).
      * resolved— ledger records whose fingerprint did not appear this run.
    A sticky human override is always honored for `known`.
    """
    seen: set[str] = set()
    new: list[Finding] = []
    known: list[Finding] = []

    for f in findings:
        fp = f.ensure_fingerprint()
        seen.add(fp)
        rec = records.get(fp)
        if rec is None:
            f.state = "new"
            new.append(f)
            continue
        # Reuse the stored verdict.
        f.state = "known"
        f.verdict = rec.get("verdict", "")
        f.confidence = rec.get("confidence", 0.0)
        f.reasoning = rec.get("reasoning", "")
        f.exploit_scenario = rec.get("exploit_scenario", "")
        f.suggested_fix = rec.get("suggested_fix", "")
        f.adjudicated_by = rec.get("adjudicated_by", "")
        f.human_override = bool(rec.get("human_override", False))
        known.append(f)

    resolved = [
        {**rec, "fingerprint": fp}
        for fp, rec in records.items()
        if fp not in seen
    ]
    return new, known, resolved


def upsert(
    records: dict[str, dict[str, Any]],
    findings: list[Finding],
    run_stamp: str,
) -> dict[str, dict[str, Any]]:
    """Write verdicts back to the ledger. Never clobbers a human_override with a
    model verdict. `run_stamp` is passed in (callers stamp time) so this module
    stays free of wall-clock calls."""
    for f in findings:
        fp = f.ensure_fingerprint()
        prior = records.get(fp, {})

        if prior.get("human_override"):
            # Keep the human verdict; only refresh last_seen.
            prior["last_seen"] = run_stamp
            records[fp] = prior
            continue

        records[fp] = {
            "detector": f.detector_id,
            "tool": f.tool,
            "file": f.file_path,
            "function": f.function,
            "severity": f.severity,
            "verdict": f.verdict,
            "confidence": f.confidence,
            "reasoning": f.reasoning,
            "exploit_scenario": f.exploit_scenario,
            "suggested_fix": f.suggested_fix,
            "adjudicated_by": f.adjudicated_by,
            "human_override": False,
            "first_seen": prior.get("first_seen", run_stamp),
            "last_seen": run_stamp,
        }
    return records
