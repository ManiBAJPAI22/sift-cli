"""Enrich each finding with the code the model needs to judge it.

Dependency-free source extraction: given a file + line, pull the enclosing
function (brace-matched) plus lightweight contract context (pragma, contract
name, state variables, modifier names). That dossier — not the raw one-line
alert — is what the model adjudicates, which is the single biggest lever on
verdict quality (see ZeroFalse's "structured contract" finding).

The enclosing-function name is only known after this step, so we (re)compute
the fingerprint here. Run order is therefore: parse -> enrich -> dedupe ->
bucket. Slither's call-graph IR can be plugged in later for callers/callees;
this gives correct, reliable context with zero extra deps today.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache

from .schema import Finding

# Matches a Solidity function/modifier/constructor signature line.
_FUNC_SIG = re.compile(
    r"^\s*(function\s+\w+|constructor|modifier\s+\w+|fallback|receive)\b"
)
_FUNC_NAME = re.compile(r"(?:function|modifier)\s+(\w+)|(\bconstructor\b)")
_CONTRACT = re.compile(r"^\s*(?:abstract\s+)?(?:contract|library|interface)\s+(\w+)")
_PRAGMA = re.compile(r"^\s*pragma\s+solidity[^;]*;")
_STATE_VAR = re.compile(
    r"^\s*(?:mapping|address|uint\d*|int\d*|bool|bytes\d*|string|"
    r"[A-Z]\w*)\s+(?:public|private|internal|constant|immutable|\s)*\w+\s*[;=]"
)

MAX_CONTEXT_CHARS = 6000  # keep the prompt bounded for small models / CI


@lru_cache(maxsize=256)
def _read_lines(path: str) -> tuple[str, ...]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return tuple(fh.read().splitlines())
    except OSError:
        return tuple()


def _enclosing_function(lines: tuple[str, ...], line_idx: int) -> tuple[str, str]:
    """Return (function_name, function_source) for the function containing the
    0-based line_idx, via backward scan to the signature then brace matching."""
    if not lines or line_idx < 0 or line_idx >= len(lines):
        return "", ""

    # Walk up to the nearest function-like signature.
    start = None
    for i in range(min(line_idx, len(lines) - 1), -1, -1):
        if _FUNC_SIG.match(lines[i]):
            start = i
            break
    if start is None:
        return "", ""

    name_m = _FUNC_NAME.search(lines[start])
    name = ""
    if name_m:
        name = name_m.group(1) or name_m.group(2) or ""

    # Brace-match from the signature to the closing brace.
    depth = 0
    seen_open = False
    end = start
    for i in range(start, len(lines)):
        depth += lines[i].count("{") - lines[i].count("}")
        if "{" in lines[i]:
            seen_open = True
        end = i
        if seen_open and depth <= 0:
            break
    body = "\n".join(lines[start : end + 1])
    return name, body


def _contract_context(lines: tuple[str, ...]) -> str:
    """A compact header: pragma, contract decl, and a sample of state vars /
    modifiers, so the model knows the surrounding trust model."""
    pieces: list[str] = []
    state_vars: list[str] = []
    for ln in lines:
        if _PRAGMA.match(ln):
            pieces.append(ln.strip())
        elif _CONTRACT.match(ln):
            pieces.append(ln.strip().rstrip("{").strip())
        elif _STATE_VAR.match(ln) and len(state_vars) < 12:
            state_vars.append(ln.strip())
    if state_vars:
        pieces.append("// state:")
        pieces.extend(state_vars)
    return "\n".join(pieces)


def enrich(finding: Finding, repo_root: str = ".") -> Finding:
    """Fill `function`, a source-derived `snippet`, and `context`; then refresh
    the fingerprint now that the function name is known."""
    path = os.path.join(repo_root, finding.file_path) if finding.file_path else ""
    lines = _read_lines(path) if path else tuple()

    if lines and finding.line:
        name, body = _enclosing_function(lines, finding.line - 1)
        if name:
            finding.function = name
        if body:
            # Prefer the real function body as the snippet (stable, meaningful).
            finding.snippet = body
        header = _contract_context(lines)
        context = (header + "\n\n" + body).strip() if body else header
        finding.context = context[:MAX_CONTEXT_CHARS]
    elif not finding.context:
        # No source available — fall back to whatever the scanner gave us.
        finding.context = (finding.snippet or finding.message)[:MAX_CONTEXT_CHARS]

    # Function name participates in identity — recompute now that we know it.
    finding.fingerprint = ""
    finding.ensure_fingerprint()
    return finding


def enrich_all(findings: list[Finding], repo_root: str = ".") -> list[Finding]:
    return [enrich(f, repo_root) for f in findings]
