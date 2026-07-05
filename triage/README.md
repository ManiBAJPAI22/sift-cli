# AI triage layer

Turns raw scanner output into **adjudicated, de-duplicated, stateful** findings
using a **self-hosted open-weights model** — no paid API, no subscription, end
users pay nothing. The model (a fine-tuned Qwen2.5-Coder, Apache-2.0) is served
locally via [Ollama](https://ollama.com); the runtime here is **pure Python
stdlib**, so `make triage` works in CI with no `pip install`.

## What it does

```
scanners → normalize+fingerprint → baseline-diff → enrich → adjudicate → ledger → report
 (slither,        (schema.py,        (ledger.py)   (enrich   (adjudicate   (ledger  (report.py)
  aderyn)         normalize.py)                      .py)      .py → Ollama)  .py)
```

- **Normalize** Slither SARIF + Aderyn markdown into one schema with a **content
  fingerprint** (detector + file + function + whitespace/comment-normalized
  snippet — *not* line numbers, so unrelated edits don't re-trigger triage).
- **Baseline-diff** against `.audit-ledger.json`: only **NEW** findings hit the
  model; **KNOWN** ones reuse their stored verdict (zero tokens); **RESOLVED**
  ones are reported as fixed. This is what makes it scale and stay consistent.
- **Enrich** each finding with the enclosing function + contract context.
- **Adjudicate** → `{verdict, confidence, severity, reasoning, exploit, fix}`.
- **Ledger** persists verdicts by fingerprint. A `human_override` is **sticky** —
  it survives re-runs and is never overwritten by the model, until the code
  changes (which changes the fingerprint).

## Reliability (never crashes the build)

- `temperature=0`, pinned model, one request at a time → deterministic, no OOM.
- Per-finding timeout + retry; any model failure → verdict `needs_human`.
- Endpoint healthcheck first; if the model is down, new findings become
  `needs_human` and the run still completes — raw scanner reports stay
  authoritative.
- `make triage-gate` is the only path that exits non-zero (CI gate on new
  high-severity real findings).

## Usage

```bash
# point at your self-hosted model (AWS box or local Docker — see serve/)
export OLLAMA_HOST=http://localhost:11434
export TRIAGE_MODEL=sol-audit-triage

make triage           # writes reports/triage.md, updates .audit-ledger.json
make triage-gate      # same, but fails CI on a new high-sev real finding
python -m triage.run --no-model   # dry run: mark everything needs_human
```

Confirming or correcting a verdict: edit the finding's entry in
`.audit-ledger.json`, set `"human_override": true` and the correct `"verdict"`.
It sticks across runs and becomes training data (see `training/`).

## Files

| File | Role |
|---|---|
| `schema.py` | Finding dataclass + stable fingerprint |
| `normalize.py` | Slither SARIF + Aderyn markdown parsers, dedupe |
| `enrich.py` | enclosing-function + contract-context extraction |
| `ledger.py` | fingerprint-keyed memory; NEW/KNOWN/RESOLVED; sticky overrides |
| `adjudicate.py` | Ollama client (stdlib), JSON verdict, timeout → needs_human |
| `report.py` | `reports/triage.md` (new-real vs suppressed split) |
| `run.py` | CLI orchestrator (`python -m triage.run`) |

Serving the model: [`serve/`](../serve). Training/fine-tuning: [`training/`](../training).

> Commit `.audit-ledger.json` to your repo — it's the cross-run memory and is
> meant to be reviewed in PRs. It is **not** added to `.gitignore`.
