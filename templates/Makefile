.PHONY: fmt lint test slither aderyn cov gas fuzz symbolic audit ci reports summary check-tools triage serve

# Python interpreter for the AI triage layer (pure stdlib — no pip install).
PYTHON ?= python3
# DIY self-host: where your own Ollama model is served.
OLLAMA_HOST ?= http://localhost:11434
TRIAGE_MODEL ?= sol-audit-triage
# Paid hosted AI (open-core): set TRIAGE_API_KEY to use the managed service —
# findings are sent to TRIAGE_API_URL instead of a local model. Leave unset for
# the free/DIY paths.
TRIAGE_API_KEY ?=
TRIAGE_API_URL ?= https://api.example.com

# Use bash for recipes (consistent behaviour across macOS/Linux).
SHELL := bash

# If a recipe fails partway, delete the (partial) target it was writing so a
# truncated report can't masquerade as a successful run in the summary.
.DELETE_ON_ERROR:

reports: ; @mkdir -p reports

check-tools: ## verify the audit toolchain is installed
	@missing=0; \
	for t in forge solhint aderyn; do \
	  command -v $$t >/dev/null 2>&1 || { echo "missing: $$t"; missing=1; }; \
	done; \
	for t in slither medusa halmos; do \
	  command -v $$t >/dev/null 2>&1 || echo "optional, not found: $$t"; \
	done; \
	[ $$missing -eq 0 ] && echo "core tools present" || { echo "run scripts/install-tools.sh"; exit 1; }

fmt:      ; forge fmt
lint:     ; solhint 'src/**/*.sol'
test:     ; forge test -vvv
slither:  reports ; rm -f reports/slither.sarif && slither . --config-file slither.config.json
aderyn:   reports ; aderyn --src src --path-excludes lib,test,script -o reports/aderyn.md . || true
cov:      reports ; forge coverage --report lcov --report summary --report-file reports/lcov.info --no-match-coverage "(script|test/mocks|Mock)" > reports/coverage.txt
gas:      reports ; forge test --gas-report > reports/gas.txt
fuzz:
	@if [ ! -f medusa.json ] || ! ls test/invariants/*.sol >/dev/null 2>&1; then \
	  echo "skipping fuzz: need medusa.json + test/invariants/*.sol (see README)"; exit 0; fi
	medusa fuzz --config medusa.json

symbolic:
	@if ! ls test/symbolic/*.sol >/dev/null 2>&1; then \
	  echo "skipping halmos: need test/symbolic/*.sol (see README)"; exit 0; fi
	halmos

summary: reports ; @bash tools/summary.sh > reports/summary.md

# AI triage: adjudicate scanner findings (false-positive vs real), de-dupe vs
# the ledger, and write reports/triage.md. Degrades to needs_human if the model
# endpoint is down — never fails the build (use `make triage-gate` in CI to gate).
triage: reports
	@OLLAMA_HOST=$(OLLAMA_HOST) TRIAGE_MODEL=$(TRIAGE_MODEL) \
	  TRIAGE_API_KEY=$(TRIAGE_API_KEY) TRIAGE_API_URL=$(TRIAGE_API_URL) \
	  $(PYTHON) -m triage.run --reports reports || \
	  echo "triage skipped (triage/ package not vendored or python missing)"

# CI-friendly variant: exit non-zero on a NEW real finding at/above high severity.
triage-gate: reports
	@OLLAMA_HOST=$(OLLAMA_HOST) TRIAGE_MODEL=$(TRIAGE_MODEL) \
	  TRIAGE_API_KEY=$(TRIAGE_API_KEY) TRIAGE_API_URL=$(TRIAGE_API_URL) \
	  $(PYTHON) -m triage.run --reports reports --fail-on high

# Build + run the self-hosted triage model server locally (Ollama in Docker).
serve:
	docker build -t sol-audit-triage:latest -f serve/Dockerfile serve/
	docker run -d --name triage -p 11434:11434 sol-audit-triage:latest

audit: fmt lint test aderyn cov gas summary triage
ci:    audit slither fuzz symbolic
