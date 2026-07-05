"""Parse Slither SARIF + Aderyn markdown into a unified, de-duplicated list of
Finding objects.

Both parsers are tolerant: missing fields degrade to empty strings rather than
raising, because scanner output format drifts between versions and a triage run
must never crash on a parse miss (it just produces a less-enriched finding).
"""

from __future__ import annotations

import json
import os
import re
from typing import Optional

from .schema import Finding, SEVERITY_RANK

# SARIF level -> our severity vocabulary.
_SARIF_LEVEL = {
    "error": "high",
    "warning": "medium",
    "note": "low",
    "none": "informational",
}


def _read_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def _repo_relative(path: str) -> str:
    """Strip leading ./ and any absolute prefix down to a repo-relative path."""
    if not path:
        return ""
    path = path.replace("\\", "/")
    path = re.sub(r"^file://", "", path)
    path = re.sub(r"^\./", "", path)
    return path


def parse_slither_sarif(path: str) -> list[Finding]:
    """Parse reports/slither.sarif into Findings. Returns [] if absent/invalid."""
    raw = _read_text(path)
    if not raw.strip():
        return []
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError:
        return []

    findings: list[Finding] = []
    for run in doc.get("runs", []) or []:
        # Build a ruleId -> {name, severity, cwe} map from the driver rules.
        rules: dict[str, dict] = {}
        driver = (run.get("tool", {}) or {}).get("driver", {}) or {}
        for rule in driver.get("rules", []) or []:
            rid = rule.get("id", "")
            sev = (
                (rule.get("defaultConfiguration", {}) or {}).get("level")
                or rule.get("properties", {}).get("precision")
                or ""
            )
            rules[rid] = {
                "name": rule.get("name", rid),
                "level": sev,
            }

        for res in run.get("results", []) or []:
            rule_id = res.get("ruleId", "") or ""
            level = res.get("level") or rules.get(rule_id, {}).get("level") or ""
            severity = _SARIF_LEVEL.get(str(level).lower(), "unknown")
            message = ((res.get("message", {}) or {}).get("text", "") or "").strip()

            file_path, line, snippet = "", None, ""
            locs = res.get("locations", []) or []
            if locs:
                phys = (locs[0].get("physicalLocation", {}) or {})
                art = (phys.get("artifactLocation", {}) or {})
                file_path = _repo_relative(art.get("uri", ""))
                region = phys.get("region", {}) or {}
                line = region.get("startLine")
                snippet = ((region.get("snippet", {}) or {}).get("text", "") or "")

            f = Finding(
                detector_id=rule_id,
                tool="slither",
                file_path=file_path,
                severity=severity,
                title=rules.get(rule_id, {}).get("name", rule_id),
                message=message,
                line=line,
                snippet=snippet,
            )
            f.ensure_fingerprint()
            findings.append(f)
    return findings


# Aderyn markdown shapes we tolerate:
#   # High Issues / # Low Issues          (section headers -> severity)
#   ## H-1: Title text                     (finding header)
#   - Found in src/Foo.sol [Line: 42]...   (location line)
_ADERYN_SECTION = re.compile(r"^#\s+(High|Low|Medium|Informational)\s+Issues", re.I)
_ADERYN_HEADER = re.compile(r"^##\s+([HLMI])-(\d+):\s*(.*)$")
_ADERYN_LOC = re.compile(r"Found in\s+([^\s,]+\.sol).*?Line:\s*(\d+)", re.I)
_SEV_LETTER = {"H": "high", "M": "medium", "L": "low", "I": "informational"}


def parse_aderyn_md(path: str) -> list[Finding]:
    """Parse reports/aderyn.md into Findings. Returns [] if absent/empty."""
    raw = _read_text(path)
    if not raw.strip():
        return []

    findings: list[Finding] = []
    section_sev = "unknown"
    cur: Optional[dict] = None

    def flush(block: Optional[dict]) -> None:
        if not block:
            return
        # A finding may reference several files; emit one Finding per location so
        # each gets its own fingerprint. If none, emit a single file-less entry.
        locs = block["locs"] or [("", None)]
        for fpath, line in locs:
            f = Finding(
                detector_id=block["detector_id"],
                tool="aderyn",
                file_path=_repo_relative(fpath),
                severity=block["severity"],
                title=block["title"],
                message=block["body"].strip(),
                line=line,
            )
            f.ensure_fingerprint()
            findings.append(f)

    for line in raw.splitlines():
        sec = _ADERYN_SECTION.match(line)
        if sec:
            section_sev = sec.group(1).lower()
            continue
        hdr = _ADERYN_HEADER.match(line)
        if hdr:
            flush(cur)
            letter, num, title = hdr.group(1), hdr.group(2), hdr.group(3)
            cur = {
                "detector_id": f"aderyn-{letter}-{num}",
                "title": title.strip(),
                "severity": _SEV_LETTER.get(letter, section_sev),
                "body": "",
                "locs": [],
            }
            continue
        if cur is not None:
            cur["body"] += line + "\n"
            for m in _ADERYN_LOC.finditer(line):
                cur["locs"].append((m.group(1), int(m.group(2))))
    flush(cur)
    return findings


def dedupe(findings: list[Finding]) -> list[Finding]:
    """Collapse findings that share a fingerprint (e.g. Slither and Aderyn
    flagging the same line). Keeps the higher-severity record and records both
    tools in `tool`."""
    by_fp: dict[str, Finding] = {}
    for f in findings:
        fp = f.ensure_fingerprint()
        existing = by_fp.get(fp)
        if existing is None:
            by_fp[fp] = f
            continue
        # Merge: keep higher severity, union the tool names.
        keep = existing if existing.severity_rank >= f.severity_rank else f
        other = f if keep is existing else existing
        tools = sorted({*keep.tool.split("+"), *other.tool.split("+")})
        keep.tool = "+".join(tools)
        if not keep.message and other.message:
            keep.message = other.message
        by_fp[fp] = keep
    return list(by_fp.values())


def collect(
    sarif_path: str = "reports/slither.sarif",
    aderyn_path: str = "reports/aderyn.md",
) -> list[Finding]:
    """Top-level: parse both reports, dedupe, sort by severity (high first)."""
    findings = parse_slither_sarif(sarif_path) + parse_aderyn_md(aderyn_path)
    findings = dedupe(findings)
    findings.sort(key=lambda f: (-f.severity_rank, f.file_path, f.detector_id))
    return findings
