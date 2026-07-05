"""Render adjudicated findings into reports/triage.md.

The report leads with what engineers actually act on — NEW + real findings, each
with an exploit scenario and a fix — and keeps the noise (false positives,
known/suppressed) collapsed. This is the signal-over-noise payoff of the whole
layer.
"""

from __future__ import annotations

from typing import Any

from .schema import Finding


def _fmt_finding(f: Finding) -> str:
    lines = [
        f"### {f.severity.upper()} — {f.title or f.detector_id}",
        f"- **File:** `{f.file_path}`"
        + (f" · function `{f.function}`" if f.function else ""),
        f"- **Detector:** `{f.detector_id}` ({f.tool})"
        + (f" · confidence {f.confidence:.2f}" if f.confidence else ""),
    ]
    if f.reasoning:
        lines.append(f"- **Why:** {f.reasoning}")
    if f.exploit_scenario:
        lines.append(f"- **Exploit:** {f.exploit_scenario}")
    if f.suggested_fix:
        lines.append(f"- **Suggested fix:** {f.suggested_fix}")
    lines.append(f"- `fingerprint: {f.fingerprint}`")
    return "\n".join(lines)


def render(
    new: list[Finding],
    known: list[Finding],
    resolved: list[dict[str, Any]],
    run_stamp: str,
    model_tag: str,
    model_ok: bool,
) -> str:
    real_new = [f for f in new if f.is_real]
    fp_new = [f for f in new if f.is_false_positive]
    review_new = [f for f in new if f.verdict == "needs_human"]
    known_real = [f for f in known if f.is_real]
    suppressed = [f for f in known if f.is_false_positive]
    # Carried-over findings still awaiting a verdict (e.g. the model was down on a
    # prior run). Surface them so they never silently disappear between runs.
    review_carried = [f for f in known if f.verdict == "needs_human"]

    out: list[str] = []
    out.append("# AI Triage Report")
    out.append("")
    out.append(f"_Generated: {run_stamp} · model: `{model_tag}`_")
    if not model_ok:
        out.append("")
        out.append(
            "> ⚠️ **Model endpoint was unavailable** — new findings are marked "
            "`needs_human`. Raw scanner reports are still authoritative."
        )
    out.append("")
    out.append(
        f"**New:** {len(real_new)} real · {len(fp_new)} false-positive · "
        f"{len(review_new)} needs-review  |  "
        f"**Carried:** {len(known_real)} real · {len(suppressed)} suppressed · "
        f"{len(review_carried)} needs-review  |  "
        f"**Resolved:** {len(resolved)}"
    )
    out.append("")

    out.append("## 🔴 New real findings")
    out.append("")
    if real_new:
        for f in real_new:
            out.append(_fmt_finding(f))
            out.append("")
    else:
        out.append("_None._")
        out.append("")

    review_all = review_new + review_carried
    if review_all:
        out.append("## 🟡 Needs human review")
        out.append("")
        for f in review_all:
            out.append(_fmt_finding(f))
            out.append("")

    if known_real:
        out.append("## 🟠 Carried-over real findings (still open)")
        out.append("")
        for f in known_real:
            out.append(_fmt_finding(f))
            out.append("")

    out.append("<details><summary>"
               f"🔇 {len(fp_new) + len(suppressed)} suppressed false positives</summary>")
    out.append("")
    for f in fp_new + suppressed:
        tag = " (human-confirmed)" if f.human_override else ""
        out.append(f"- `{f.detector_id}` in `{f.file_path}`{tag} — {f.reasoning}")
    if not (fp_new or suppressed):
        out.append("_None._")
    out.append("")
    out.append("</details>")
    out.append("")

    if resolved:
        out.append("<details><summary>"
                   f"✅ {len(resolved)} resolved since last run</summary>")
        out.append("")
        for r in resolved:
            out.append(f"- `{r.get('detector')}` in `{r.get('file')}`")
        out.append("")
        out.append("</details>")
        out.append("")

    return "\n".join(out)
