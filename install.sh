#!/usr/bin/env bash
# sol-audit-pipeline installer (macOS + Linux)
#
# Scaffolds the audit pipeline into the current Foundry project.
#
# Usage:
#   curl -fsSL <raw-url>/install.sh | bash
#   curl -fsSL <raw-url>/install.sh | bash -s -- --yes   # non-interactive, keep existing files
#
# Flags:
#   -y, --yes     non-interactive; accept defaults, never overwrite existing files
#   -h, --help    show this help

set -euo pipefail

REPO_RAW="${AUDIT_PIPELINE_REPO:-https://raw.githubusercontent.com/ManiBAJPAI22/sol-audit-pipeline/main}"
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

bold()   { printf "\033[1m%s\033[0m\n" "$*"; }
cyan()   { printf "\033[36m%s\033[0m\n" "$*"; }
yellow() { printf "\033[33m%s\033[0m\n" "$*"; }
red()    { printf "\033[31m%s\033[0m\n" "$*"; }
green()  { printf "\033[32m%s\033[0m\n" "$*"; }

usage() { sed -n '2,14p' "$0" 2>/dev/null | sed 's/^# \{0,1\}//'; }

# ---- argument parsing (flags accepted in any position) ----------------------
WANT_YES=0
for arg in "$@"; do
  case "$arg" in
    -y|--yes) WANT_YES=1 ;;
    -h|--help) usage; exit 0 ;;
    *) red "unknown argument: $arg"; usage; exit 2 ;;
  esac
done

# Detect non-interactive mode: CI env, explicit --yes/-y flag, or no usable TTY.
NONINTERACTIVE=0
if [[ "${CI:-}" == "true" ]] || (( WANT_YES == 1 )) || [[ ! -t 0 && ! -r /dev/tty ]]; then
  NONINTERACTIVE=1
fi

# Wrapper around `read` so every prompt honours NONINTERACTIVE. In non-interactive
# mode the default answer is returned without blocking on /dev/tty.
ask() {
  local prompt="$1" default="$2" var
  if (( NONINTERACTIVE == 1 )); then
    echo "  [non-interactive] $prompt — using default: $default"
    REPLY="$default"; return
  fi
  read -r -p "$prompt" var </dev/tty
  REPLY="${var:-$default}"
}

# ---- preconditions ----------------------------------------------------------
if ! command -v curl &>/dev/null; then
  red "error: curl is required but not installed"
  exit 1
fi

if [[ ! -f foundry.toml ]]; then
  red "error: no foundry.toml in current directory"
  echo "run this inside a Foundry project root (where foundry.toml lives)"
  exit 1
fi

bold "sol-audit-pipeline installer"
echo "target: $(pwd)"
echo "source: $REPO_RAW"
if (( NONINTERACTIVE == 1 )); then yellow "mode: non-interactive (CI or --yes)"; fi
echo ""

# ---- fetch templates --------------------------------------------------------
cyan "fetching templates..."
FILES=(
  "templates/Makefile:Makefile"
  "templates/slither.config.json:slither.config.json"
  "templates/.solhint.json:.solhint.json"
  "templates/tools/summary.sh:tools/summary.sh"
  "templates/.github/workflows/audit.yml:.github/workflows/audit.yml"
  # AI triage runtime — pure stdlib, vendored so `make triage` works in-project.
  "triage/__init__.py:triage/__init__.py"
  "triage/schema.py:triage/schema.py"
  "triage/normalize.py:triage/normalize.py"
  "triage/enrich.py:triage/enrich.py"
  "triage/ledger.py:triage/ledger.py"
  "triage/adjudicate.py:triage/adjudicate.py"
  "triage/report.py:triage/report.py"
  "triage/run.py:triage/run.py"
  # Self-hosted model server (Ollama) for AWS/local.
  "serve/Modelfile:serve/Modelfile"
  "serve/Dockerfile:serve/Dockerfile"
)

for pair in "${FILES[@]}"; do
  src="${pair%%:*}"
  dst="${pair##*:}"
  mkdir -p "$TMPDIR/$(dirname "$dst")"
  if ! curl -fsSL "$REPO_RAW/$src" -o "$TMPDIR/$dst"; then
    red "error: failed to fetch $src from $REPO_RAW"
    echo "check the URL / your network, or set AUDIT_PIPELINE_REPO to a valid raw base"
    exit 1
  fi
done

# ---- solc version substitution ----------------------------------------------
SOLC="$(grep -E '^\s*solc\s*=' foundry.toml | sed -E 's/.*"([0-9.]+)".*/\1/' | head -1 || true)"
SOLC="${SOLC:-0.8.28}"
cyan "detected solc version: $SOLC"

# sed -i.bak is portable across BSD (macOS) and GNU (Linux). The placeholder
# only appears in audit.yml today, but sweeping all files keeps it future-proof.
find "$TMPDIR" -type f \( -name "*.yml" -o -name "*.json" -o -name "*.sh" -o -name "Makefile" \) \
  -exec sed -i.bak "s/{{SOLC_VERSION}}/$SOLC/g" {} \;
find "$TMPDIR" -name "*.bak" -delete

# ---- copy into project ------------------------------------------------------
copy_file() {
  local src="$1"
  local dst="$2"

  if [[ -e "$dst" ]]; then
    if (( NONINTERACTIVE == 1 )); then
      yellow "exists: $dst — skipped (re-run interactively to overwrite)"
      return
    fi
    yellow "exists: $dst"
    ask "  overwrite? [y/N/d(iff)] " "n"
    case "$REPLY" in
      y|Y) cp "$src" "$dst" && green "  overwritten" ;;
      d|D)
        diff -u "$dst" "$src" || true
        ask "  overwrite after diff? [y/N] " "n"
        if [[ "$REPLY" =~ ^[yY]$ ]]; then cp "$src" "$dst" && green "  overwritten"; else yellow "  skipped"; fi
        ;;
      *) yellow "  skipped" ;;
    esac
  else
    mkdir -p "$(dirname "$dst")"
    cp "$src" "$dst"
    green "new:   $dst"
  fi
}

for pair in "${FILES[@]}"; do
  dst="${pair##*:}"
  copy_file "$TMPDIR/$dst" "$dst"
done

chmod +x tools/summary.sh 2>/dev/null || true

# ---- foundry.toml: pin evm_version for aderyn compatibility ------------------
if ! grep -q 'evm_version' foundry.toml; then
  echo ""
  yellow "foundry.toml has no evm_version set."
  echo "  aderyn 0.1.x can't parse 'osaka'. recommend pinning to cancun."
  ask "  add evm_version = cancun to [profile.default]? [Y/n] " "y"
  if [[ ! "$REPLY" =~ ^[nN]$ ]]; then
    if grep -q '^\[profile\.default\]' foundry.toml; then
      awk '/^\[profile\.default\]/ { print; print "evm_version = \"cancun\""; next } { print }' foundry.toml > foundry.toml.tmp
      mv foundry.toml.tmp foundry.toml
      green "  added evm_version = cancun"
    else
      yellow "  no [profile.default] section found — add evm_version = \"cancun\" manually"
    fi
  fi
fi

# ---- .gitignore additions: reports/, Medusa corpus, crytic-compile exports ---
append_gitignore_entry() {
  local entry="$1" prompt="$2"
  # Create .gitignore if absent so audit artifacts don't get committed by accident.
  if [[ -f .gitignore ]] && grep -qxF "$entry" .gitignore; then return; fi
  echo ""
  ask "$prompt [Y/n] " "y"
  if [[ ! "$REPLY" =~ ^[nN]$ ]]; then
    echo "$entry" >> .gitignore
    green "  added $entry"
  fi
}

append_gitignore_entry "reports/"        "add reports/ to .gitignore?"
append_gitignore_entry "corpus/"         "add corpus/ to .gitignore (Medusa runtime output)?"
append_gitignore_entry "crytic-export/"  "add crytic-export/ to .gitignore (Slither/Medusa compile cache)?"

echo ""
bold "done."
echo ""
echo "next steps:"
echo "  1. install local audit tools (once per machine):"
echo "     curl -fsSL $REPO_RAW/scripts/install-tools.sh | bash"
echo "  2. run the pipeline:"
echo "     make audit"
echo "  3. (optional) enable Medusa fuzzing — see README section 'Enabling Medusa fuzzing'"
