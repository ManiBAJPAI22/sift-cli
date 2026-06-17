#!/usr/bin/env bash
#
# sol-audit-pipeline: local tool installer (macOS + Linux).
#
# Installs the full audit toolchain: Foundry, Slither, Aderyn, Medusa, Halmos,
# Solhint, and solc-select. Idempotent — safe to re-run to upgrade.
#
# Usage:
#   curl -fsSL <raw-url>/scripts/install-tools.sh | bash
#
# Tool versions are pinned and MUST stay in sync with
# templates/.github/workflows/audit.yml. Bump in both places together.
set -euo pipefail

# ---- pinned versions (keep in sync with audit.yml) --------------------------
SLITHER_VERSION="0.10.4"
SOLC_SELECT_VERSION="1.0.4"
ADERYN_VERSION="0.1.9"
SOLHINT_VERSION="5.0.3"
MEDUSA_VERSION="v0.1.5"
SOLC_DEFAULT="0.8.28"

bold()  { printf "\033[1m%s\033[0m\n" "$*"; }
green() { printf "\033[32m%s\033[0m\n" "$*"; }
cyan()  { printf "\033[36m%s\033[0m\n" "$*"; }
yellow(){ printf "\033[33m%s\033[0m\n" "$*"; }
red()   { printf "\033[31m%s\033[0m\n" "$*"; }

have() { command -v "$1" &>/dev/null; }

# ---- platform + package-manager detection -----------------------------------
OS="$(uname -s)"
PKG=""           # high-level package manager name
PKG_INSTALL=""   # command prefix to install a package

detect_pkg_manager() {
  case "$OS" in
    Darwin)
      if ! have brew; then
        red "error: Homebrew required on macOS. Install from https://brew.sh"
        exit 1
      fi
      PKG="brew"; PKG_INSTALL="brew install"
      ;;
    Linux)
      if   have apt-get; then PKG="apt";    PKG_INSTALL="sudo apt-get install -y"
      elif have dnf;     then PKG="dnf";    PKG_INSTALL="sudo dnf install -y"
      elif have pacman;  then PKG="pacman"; PKG_INSTALL="sudo pacman -S --noconfirm"
      elif have zypper;  then PKG="zypper"; PKG_INSTALL="sudo zypper install -y"
      else
        red "error: no supported package manager (apt/dnf/pacman/zypper) found."
        echo "Install the base deps manually: git curl python3 python3-pip pipx nodejs npm golang rustc"
        exit 1
      fi
      ;;
    *)
      red "error: unsupported OS '$OS' (need macOS or Linux)."
      exit 1
      ;;
  esac
}

# Map a logical dependency name to the right package name per manager, then install
# only if the underlying command is missing.
install_base() {
  local cmd="$1"; shift
  if have "$cmd"; then return; fi
  local pkg=""
  case "$PKG" in
    brew)   pkg="$1" ;;
    apt)    pkg="$2" ;;
    dnf)    pkg="$3" ;;
    pacman) pkg="$4" ;;
    zypper) pkg="$5" ;;
  esac
  [[ -z "$pkg" ]] && return
  cyan "   installing $cmd ($PKG: $pkg)"
  # shellcheck disable=SC2086
  $PKG_INSTALL $pkg 2>/dev/null || yellow "   warning: failed to install $pkg — continuing"
}

# ---- main -------------------------------------------------------------------
bold "sol-audit-pipeline: local tool installer"
echo "platform: $OS"
detect_pkg_manager
echo "package manager: $PKG"
echo ""

cyan "-> base tooling (git, curl, python, node, go, rust, pipx)"
if [[ "$PKG" == "apt" ]]; then sudo apt-get update -y 2>/dev/null || true; fi
#            cmd       brew        apt              dnf            pacman      zypper
install_base git       git         git              git            git         git
install_base curl      curl        curl             curl           curl        curl
install_base python3   python      python3          python3        python      python3
install_base pipx      pipx        pipx             pipx           python-pipx python3-pipx
install_base node      node        nodejs           nodejs         nodejs      nodejs
install_base npm       node        npm              npm            npm         npm20
install_base go        go          golang-go        golang         go          go
install_base cargo     rust        cargo            cargo          rust        cargo

# pipx may be installed but not on PATH yet for this session.
if have pipx; then
  pipx ensurepath >/dev/null 2>&1 || true
  export PATH="$HOME/.local/bin:$PATH"
fi

cyan "-> Foundry (forge, cast, anvil, chisel)"
if have forge; then
  green "   forge present — running foundryup to update"
  foundryup 2>/dev/null || yellow "   foundryup not on PATH; skipping update"
else
  curl -fsSL https://foundry.paradigm.xyz | bash
  # foundryup is dropped in ~/.foundry/bin; make it usable this session.
  export PATH="$HOME/.foundry/bin:$PATH"
  if have foundryup; then foundryup; else yellow "   foundryup not found — open a new shell and run 'foundryup'"; fi
fi

cyan "-> slither, halmos, solc-select (via pipx)"
if have pipx; then
  pipx install "slither-analyzer==$SLITHER_VERSION" 2>/dev/null || pipx upgrade slither-analyzer || true
  pipx install halmos 2>/dev/null || pipx upgrade halmos || true
  pipx install "solc-select==$SOLC_SELECT_VERSION" 2>/dev/null || true
else
  yellow "   pipx unavailable — skipping slither/halmos/solc-select"
fi

cyan "-> default solc $SOLC_DEFAULT"
if have solc-select; then
  solc-select install "$SOLC_DEFAULT" && solc-select use "$SOLC_DEFAULT"
else
  yellow "   solc-select unavailable — skipping"
fi

cyan "-> aderyn + solhint (via npm)"
if have npm; then
  npm i -g "@cyfrin/aderyn@$ADERYN_VERSION" || yellow "   aderyn install failed (try: sudo npm i -g @cyfrin/aderyn@$ADERYN_VERSION)"
  npm i -g "solhint@$SOLHINT_VERSION"        || yellow "   solhint install failed (try: sudo npm i -g solhint@$SOLHINT_VERSION)"
else
  yellow "   npm unavailable — skipping aderyn/solhint"
fi

cyan "-> medusa (via go install)"
if have go; then
  go install "github.com/crytic/medusa@$MEDUSA_VERSION" || yellow "   medusa install failed"
  export PATH="$(go env GOPATH 2>/dev/null)/bin:$PATH"
else
  yellow "   go unavailable — skipping medusa"
fi

cyan "-> sift CLI"
SIFT_BIN="$HOME/.local/bin"
mkdir -p "$SIFT_BIN"
if curl -fsSL "${RAW_BASE:-https://raw.githubusercontent.com/ManiBAJPAI22/sol-audit-pipeline/main}/bin/sift" -o "$SIFT_BIN/sift" 2>/dev/null; then
  chmod +x "$SIFT_BIN/sift"
  export PATH="$SIFT_BIN:$PATH"
  green "   sift -> $SIFT_BIN/sift"
else
  yellow "   sift CLI download failed — skipping"
fi

# ---- verification -----------------------------------------------------------
echo ""
bold "verifying installation"
verify() {
  local name="$1" cmd="$2"
  if have "$cmd"; then
    green "  ✓ $name ($(command -v "$cmd"))"
  else
    yellow "  ✗ $name — not on PATH (may need a new shell)"
  fi
}
verify "forge"       forge
verify "slither"     slither
verify "aderyn"      aderyn
verify "solhint"     solhint
verify "medusa"      medusa
verify "halmos"      halmos
verify "solc-select" solc-select
verify "sift"        sift

echo ""
green "done."
echo ""
yellow "If any tool shows ✗, open a NEW terminal (so updated PATH entries load) and re-check."
echo "PATH additions used by these tools:"
echo "  \$HOME/.local/bin     (pipx)"
echo "  \$HOME/.foundry/bin   (foundry)"
echo "  \$(go env GOPATH)/bin (medusa)"
