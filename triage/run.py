#!/usr/bin/env python3
"""Triage CLI — the orchestrator wired by `make triage`.

Flow:  parse -> enrich -> dedupe -> baseline-diff (ledger) -> adjudicate NEW
       -> write verdicts back -> render report.

Reliability: if the model endpoint is down, NEW findings are recorded as
needs_human and the run still completes (raw scanner reports remain the source
of truth). The only non-zero exit is `--fail-on` gating for CI.

Usage:
  python -m triage.run [--reports reports] [--repo-root .] [--no-model]
                       [--fail-on {high,medium,low,none}]
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import sys

from . import adjudicate, enrich, ledger, normalize, report
from .schema import SEVERITY_RANK


def _utc_stamp() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="triage", description="AI triage for scanner output")
    ap.add_argument("--reports", default="reports", help="reports directory")
    ap.add_argument("--repo-root", default=".", help="source root for enrichment")
    ap.add_argument("--ledger", default=ledger.DEFAULT_LEDGER)
    ap.add_argument("--out", default=None, help="output markdown (default reports/triage.md)")
    ap.add_argument("--no-model", action="store_true",
                    help="skip model calls; mark new findings needs_human")
    ap.add_argument("--fail-on", choices=["high", "medium", "low", "none"],
                    default="none", help="exit non-zero if a NEW real finding >= this severity")
    args = ap.parse_args(argv)

    sarif = os.path.join(args.reports, "slither.sarif")
    aderyn = os.path.join(args.reports, "aderyn.md")
    out_path = args.out or os.path.join(args.reports, "triage.md")
    run_stamp = _utc_stamp()

    # 1. parse -> 2. enrich -> 3. dedupe (post-enrich, so function is in identity)
    findings = normalize.parse_slither_sarif(sarif) + normalize.parse_aderyn_md(aderyn)
    findings = enrich.enrich_all(findings, repo_root=args.repo_root)
    findings = normalize.dedupe(findings)
    findings.sort(key=lambda f: (-f.severity_rank, f.file_path, f.detector_id))

    # 4. baseline-diff against the ledger
    records = ledger.load(args.ledger)
    new, known, resolved = ledger.bucket(findings, records, run_stamp)

    # 5. adjudicate only NEW findings (KNOWN reuse stored verdicts).
    #    Mode auto-selects: TRIAGE_API_KEY set -> hosted SaaS (paid); else local
    #    Ollama (DIY self-host); --no-model forces a dry run (free tier default).
    cfg = adjudicate.AdjudicatorConfig()
    model_tag = cfg.model
    model_ok = False
    if args.no_model:
        for f in new:
            f.verdict = "needs_human"
            f.reasoning = "model disabled (--no-model)"
            f.adjudicated_by = "(disabled)"
        model_tag = "(disabled)"
    elif not new:
        model_ok = True  # nothing to adjudicate
    elif adjudicate.using_remote():
        rc = adjudicate.RemoteConfig()
        model_tag = f"hosted:{rc.api_url}"
        adjudicate.remote_adjudicate_all(new, rc)
        # "ok" unless every finding came back needs_human due to transport error.
        model_ok = any(f.verdict != "needs_human" for f in new) or not new
    else:
        model_ok, detail = adjudicate.healthcheck(cfg)
        if model_ok:
            adjudicate.adjudicate_all(new, cfg)
        else:
            print(f"[triage] model unavailable: {detail}", file=sys.stderr)
            for f in new:
                f.verdict = "needs_human"
                f.reasoning = f"model unavailable: {detail}"
                f.adjudicated_by = cfg.model

    # 6. write verdicts back (NEW + refreshed KNOWN), persist atomically
    records = ledger.upsert(records, new + known, run_stamp)
    ledger.save(records, args.ledger)

    # 7. render report
    md = report.render(new, known, resolved, run_stamp, model_tag, model_ok)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(md)

    real_new = [f for f in new if f.is_real]
    print(
        f"[triage] {len(findings)} findings · {len(new)} new "
        f"({len(real_new)} real) · {len(known)} known · {len(resolved)} resolved "
        f"-> {out_path}"
    )

    # 8. optional CI gate on NEW real findings at/above a severity
    if args.fail_on != "none":
        threshold = SEVERITY_RANK[args.fail_on]
        blocking = [f for f in real_new if f.severity_rank >= threshold]
        if blocking:
            print(
                f"[triage] FAIL: {len(blocking)} new real finding(s) "
                f">= {args.fail_on}",
                file=sys.stderr,
            )
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
