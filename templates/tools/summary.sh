#!/usr/bin/env bash
#
# Consolidates the per-tool reports under reports/ into a single Markdown
# summary (reports/summary.md via the Makefile). Safe to run even when some
# reports are missing — each section degrades to a "_No … found._" note.
set -euo pipefail

# Resolve repo root from this script's location so it works regardless of CWD.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

REPORTS_DIR="${REPORTS_DIR:-reports}"

# Count matches without tripping `set -e`: `grep -c` exits 1 on zero matches
# (and still prints "0"), so capture stdout and normalise failures to 0.
count_matches() {
  local pattern="$1" file="$2" n
  n="$(grep -cE "$pattern" "$file" 2>/dev/null || true)"
  # grep -c emits one number; guard against empty (file missing) → 0.
  printf '%s' "${n:-0}"
}

# Portable UTC timestamp.
now_utc() { date -u +"%Y-%m-%d %H:%M UTC"; }

echo "# Audit Summary"
echo ""
echo "_Generated: $(now_utc)_"
echo ""

echo "## Tests & Coverage"
echo ""
if [[ -f "$REPORTS_DIR/coverage.txt" ]]; then
  echo '```'
  grep -E "^\| (src/|Total)" "$REPORTS_DIR/coverage.txt" || echo "(no coverage data)"
  echo '```'
else
  echo "_No coverage report found._"
fi
echo ""

echo "## Aderyn Static Analysis"
echo ""
if [[ -f "$REPORTS_DIR/aderyn.md" ]]; then
  HIGHS="$(count_matches '^## H-' "$REPORTS_DIR/aderyn.md")"
  LOWS="$(count_matches '^## L-' "$REPORTS_DIR/aderyn.md")"
  echo "**Findings:** $HIGHS high, $LOWS low"
  echo ""
  echo "<details><summary>High severity details</summary>"
  echo ""
  awk '/^# High Issues/,/^# Low Issues/' "$REPORTS_DIR/aderyn.md" | sed '$d'
  echo "</details>"
  echo ""
  echo "<details><summary>Low severity details</summary>"
  echo ""
  awk '/^# Low Issues/,0' "$REPORTS_DIR/aderyn.md"
  echo "</details>"
else
  echo "_No aderyn report found._"
fi
echo ""

echo "## Slither Static Analysis"
echo ""
if [[ -f "$REPORTS_DIR/slither.sarif" ]]; then
  RESULTS="$(count_matches '"ruleId"' "$REPORTS_DIR/slither.sarif")"
  echo "**Findings:** $RESULTS total"
  echo ""
  if command -v jq &>/dev/null; then
    echo "<details><summary>Slither findings breakdown</summary>"
    echo ""
    echo '```'
    jq -r '.runs[0].results[] | "- \(.ruleId): \(.message.text)"' "$REPORTS_DIR/slither.sarif" 2>/dev/null \
      | sort | uniq -c | sort -rn | head -20 || echo "(jq parse failed)"
    echo '```'
    echo "</details>"
  fi
else
  echo "_No slither report found._"
fi
echo ""

echo "## Gas Report"
echo ""
if [[ -f "$REPORTS_DIR/gas.txt" ]]; then
  echo "<details><summary>Full gas report</summary>"
  echo ""
  echo '```'
  cat "$REPORTS_DIR/gas.txt"
  echo '```'
  echo "</details>"
else
  echo "_No gas report found._"
fi
echo ""

echo "---"
echo "_Full artifacts available in the run's Artifacts section._"
