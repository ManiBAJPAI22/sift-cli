# sift-cli  
v0.2.0

Drop-in smart contract audit pipeline for Foundry projects. One command scaffolds a complete CI/CD setup with static analysis, coverage, gas reporting, and consolidated audit summaries posted as PR comments.

## Support

If this saved you time, consider:

- ⭐ **[Starring the repo](https://github.com/ManiBAJPAI22/sift-cli)** — helps others find it
- 🍴 **[Forking](https://github.com/ManiBAJPAI22/sift-cli/fork)** — customize the templates for your team's conventions and point your projects at your fork via `AUDIT_PIPELINE_REPO` env var:
```bash
  AUDIT_PIPELINE_REPO=https://raw.githubusercontent.com/YourUser/sift-cli/main \
    curl -fsSL $AUDIT_PIPELINE_REPO/install.sh | bash
```
- 🐛 **[Opening an issue](https://github.com/ManiBAJPAI22/sift-cli/issues/new)** — bug reports and feature requests welcome
- 📣 **Sharing** — if you use this on a project, a mention in your repo's README helps the tool grow

---

## What you get

**Local pipeline** (`make audit`):
- Formatting (`forge fmt`)
- Linting (`solhint`)
- Tests (`forge test`)
- Static analysis (`aderyn`)
- Coverage (`forge coverage` with LCOV output)
- Gas report
- Consolidated markdown summary

**On-demand extras:**
- Slither (`make slither`) — SARIF output
- Medusa property-based fuzzing (`make fuzz`) — requires `medusa.json`
- Halmos symbolic execution (`make symbolic`)

**GitHub Actions workflow:**
- Runs on every pull request
- Uploads full audit report as a downloadable artifact
- Posts consolidated summary as a sticky PR comment (auto-updates on push)
- Nightly medusa fuzzing at 02:00 UTC (opt-in)

## Hosted AI triage with `sift` (Pro/Team)

The open-source pipeline lists findings and marks them `needs_human`. **Sift** adds an AI
layer that judges each finding **real vs false-positive** (with a suggested fix) — cutting
~85% of the noise so you only read what matters.

1. **Get your API key** at **[thesift.xyz](https://thesift.xyz)** (the key is
   shown once — save it).
2. **Install the `sift` CLI** (once per machine):

```bash
npm install -g sift-audit
sift setup
```

`sift setup` installs the scanner toolchain (Foundry, Solhint, Aderyn, Slither). No npm?
The curl equivalent:

```bash
sudo curl -fsSL https://raw.githubusercontent.com/ManiBAJPAI22/sift-cli/main/bin/sift -o /usr/local/bin/sift && sudo chmod +x /usr/local/bin/sift
```

3. **Run it from your Foundry repo's root** (where `foundry.toml` lives). `sift init` is
   once per repo — it vendors the Makefile + `triage/`; results land in `reports/triage.md`:

```bash
export SIFT_API_KEY=sk_live_YOUR_KEY
sift init
sift scan
```

Without `SIFT_API_KEY`, `sift scan` runs the **free** path (scanners only, findings marked
`needs_human`). To **self-host** the AI instead, point `OLLAMA_HOST` at your own model. The
first hosted call can take ~90s while the model warms up.

> `sift` is a thin wrapper over `make audit` / `make triage` — both still work directly with
> `TRIAGE_API_KEY` / `TRIAGE_API_URL` if you prefer.

## Quick start

### 1. Install audit tools (once per machine)

```bash
curl -fsSL https://raw.githubusercontent.com/ManiBAJPAI22/sift-cli/main/scripts/install-tools.sh | bash
```

Works on **macOS and Linux**. Detects your package manager (Homebrew on macOS; apt/dnf/pacman/zypper on Linux), installs missing base dependencies, then installs the audit toolchain:
- `foundry` (forge, cast, anvil, chisel) — via the official `foundryup`
- `slither-analyzer`
- `@cyfrin/aderyn`
- `medusa`
- `halmos`
- `solhint`
- `solc-select` (with 0.8.28 as default)

The script is idempotent (safe to re-run to upgrade) and verifies every tool at the end. If a tool shows `✗`, open a new terminal so the updated `PATH` loads (pipx → `~/.local/bin`, foundry → `~/.foundry/bin`, medusa → `$(go env GOPATH)/bin`).

> On macOS, Homebrew is required (install from https://brew.sh). On Linux, `sudo` is used for base-package installs.

### 2. Install the pipeline in a project (once per repo)

Inside any Foundry project root:

```bash
curl -fsSL https://raw.githubusercontent.com/ManiBAJPAI22/sift-cli/main/install.sh | bash
```

The installer:
- Fetches the latest templates from this repo
- Auto-detects your `solc` version from `foundry.toml`
- Asks before overwriting existing files (with diff option)
- Offers to pin `evm_version = "cancun"` if unset (aderyn compatibility)
- Offers to add `reports/` to `.gitignore`

### 3. Run the audit

```bash
make audit
```

Outputs land in `reports/`:
- `aderyn.md` — static analysis findings
- `lcov.info` — coverage data
- `coverage.txt` — coverage summary table
- `gas.txt` — gas usage report
- `summary.md` — consolidated markdown (aggregates all of the above)
- `triage.md` — AI triage: false-positive vs real, with fixes (if enabled)

## AI triage (free, self-hosted — no paid API)

`make triage` runs an **AI layer over the scanners** that decides false-positive
vs real bug, proposes fixes, and stays consistent across runs. It uses a
**self-hosted open-weights model** (a fine-tuned Qwen2.5-Coder, Apache-2.0,
served via [Ollama](https://ollama.com)) — **no API key, no subscription, end
users pay nothing**. The runtime is pure Python stdlib, so it works in CI with no
`pip install`.

How it stays useful at scale and across runs:
- **Content fingerprints** (not line numbers) give each finding a stable identity.
- **Baseline-diff** against a committed `.audit-ledger.json`: only *new* findings
  are sent to the model; known ones reuse their verdict; fixed ones are reported
  resolved.
- **Sticky human overrides** — confirm/correct a verdict once in the ledger and it
  survives re-runs (until the code changes).
- **Never crashes the build** — if the model endpoint is down, findings fall back
  to `needs_human` and raw scanner reports stay authoritative.

`make triage` runs in one of three modes, auto-selected:

| Mode | How | Who |
|---|---|---|
| **Free** | no key, no model | scanners + reports only; findings marked `needs_human` |
| **DIY self-host** | `make serve` (your own Ollama) + `OLLAMA_HOST` | free, open-source model, you run the GPU |
| **Paid hosted** | `TRIAGE_API_KEY=sk_… make triage` | managed service — best fine-tuned model, no setup |

```bash
# DIY self-host
make serve                                        # Ollama on :11434 (serve/)
OLLAMA_HOST=http://localhost:11434 make triage    # → reports/triage.md

# Paid hosted (open-core SaaS)
TRIAGE_API_KEY=sk_live_xxx make triage            # sends findings to the API
```

In CI, set repo variable `TRIAGE_OLLAMA_HOST` (DIY) or secret `TRIAGE_API_KEY`
(paid); if neither is set, triage degrades gracefully and the build still passes.

Details: [`triage/`](triage) (runtime + remote client), [`serve/`](serve) (model
server), [`training/`](training) (fine-tune your own model), [`server/`](server)
(the paid SaaS backend: API keys, Stripe, tier gating — what *we* host).

## Enabling Medusa fuzzing

`make fuzz` (and the nightly CI job) are opt-in. With no config present, the Makefile prints `skipping fuzz: …` and exits cleanly. To activate fuzzing, add two files to your project:

**1. `medusa.json`** — Medusa runtime config. Minimal shape:

```json
{
  "fuzzing": {
    "workers": 6,
    "timeout": 600,
    "testLimit": 50000,
    "callSequenceLength": 100,
    "corpusDirectory": "corpus",
    "coverageEnabled": true,
    "targetContracts": ["YourInvariants"],
    "deployerAddress": "0x30000",
    "senderAddresses": ["0x10000", "0x20000", "0x30000"],
    "testing": {
      "assertionTesting": { "enabled": true, "testViewMethods": false },
      "propertyTesting": {
        "enabled": true,
        "testPrefixes": ["invariant_", "property_"]
      }
    },
    "chainConfig": {
      "codeSizeCheckDisabled": true,
      "cheatCodes": { "cheatCodesEnabled": true, "enableFFI": false }
    }
  },
  "compilation": {
    "platform": "crytic-compile",
    "platformConfig": {
      "target": ".",
      "solcVersion": "",
      "args": ["--foundry-compile-all"]
    }
  },
  "logging": { "level": "info", "logDirectory": "" }
}
```

Key knobs: `targetContracts` (the harness Medusa drives), `testLimit` / `timeout` (stopping conditions), `workers` (parallelism), `testPrefixes` (function-name prefixes Medusa treats as invariants).

**2. `test/invariants/YourInvariants.sol`** — harness contract. Deploys your system in its constructor, exposes `handler_*` functions Medusa calls with random args, and `invariant_*` / `property_*` predicates that must hold between every call.

Skeleton:

```solidity
// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Vm } from "forge-std/Vm.sol";
import { YourToken } from "../../src/YourToken.sol";

contract YourInvariants {
    Vm internal constant vm = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));

    YourToken internal token;
    uint256 internal initialSupply;

    constructor() {
        token = new YourToken();
        initialSupply = token.totalSupply();
    }

    // Medusa calls handlers with random args — bound them to sensible ranges.
    function handler_transfer(address to, uint256 amount) public {
        amount = amount % token.balanceOf(address(this));
        if (amount == 0 || to == address(0)) return;
        token.transfer(to, amount);
    }

    // Predicates checked between every handler call. Return false = invariant broken.
    function invariant_totalSupplyConstant() public view returns (bool) {
        return token.totalSupply() == initialSupply;
    }
}
```

Cheatcodes available under `vm.*` include `sign`, `prank`, `warp`, `addr` — enough to fuzz EIP-712 signed flows, time-based logic, and multi-caller scenarios.

Once both files exist, `make fuzz` runs Medusa; otherwise it skips.

## Make targets

| Target | What it does |
|--------|--------------|
| `make fmt` | `forge fmt` |
| `make lint` | Run solhint on `src/**/*.sol` |
| `make test` | `forge test -vvv` |
| `make slither` | Slither static analysis → SARIF |
| `make aderyn` | Aderyn static analysis → markdown |
| `make cov` | Coverage report (excludes scripts/mocks) |
| `make gas` | Gas report |
| `make fuzz` | Medusa property-based fuzzing |
| `make symbolic` | Halmos symbolic execution |
| `make summary` | Aggregate all reports into `reports/summary.md` |
| `make triage` | AI triage: adjudicate findings (FP vs real) → `reports/triage.md` |
| `make triage-gate` | Triage + fail CI on a new high-severity real finding |
| `make serve` | Build + run the self-hosted triage model server (Ollama/Docker) |
| `make check-tools` | Verify the audit toolchain is installed |
| `make audit` | fmt + lint + test + aderyn + cov + gas + summary |
| `make ci` | audit + slither + fuzz + symbolic (heavy, for scheduled jobs) |

## CI behavior

The generated workflow (`.github/workflows/audit.yml`) runs on:
- **Every PR** — full audit + slither, posts sticky comment with summary
- **Nightly at 02:00 UTC** — runs `make fuzz` (skipped if no property tests)
- **Manual trigger** — via Actions tab → "Run workflow"

It does not run on pushes to `main` to avoid duplicate runs after merge.

### Example PR comment

The bot comment includes:
- Coverage table for contracts under `src/`
- Aderyn finding counts (high/low) with collapsible details
- Slither finding breakdown (top 20)
- Full gas report (collapsible)
- Link to the full artifact for deeper inspection

## Customization

All files land in your project and are yours to edit:

### Stricter static analysis gates

`slither.config.json`:

```json
{ "fail_on": "high" }
```

(Default is `"medium"`.)

### Different solc version

```bash
solc-select install 0.8.29 && solc-select use 0.8.29
```

Also update `foundry.toml` and `.github/workflows/audit.yml` to match.

### Disable slither in CI

Remove the `Run slither` and `Rebuild summary with slither findings` steps from `.github/workflows/audit.yml`.

### Custom coverage exclusions

In `Makefile`:

```makefile
cov: reports ; forge coverage ... --no-match-coverage "(script|test/mocks|Mock|YourPattern)"
```

## Requirements

- **macOS or Linux**
- **A package manager** — Homebrew (macOS) or apt/dnf/pacman/zypper (Linux); `install-tools.sh` uses it to pull in any missing base deps
- **Node.js ≥ 18** (for aderyn + solhint via npm)
- **Python ≥ 3.8** (for slither + halmos via pipx; also runs the AI triage layer — stdlib only)
- **Docker** (optional — only to self-host the triage model via `make serve`)
- **Foundry** (installed by `install-tools.sh` if missing)

## Troubleshooting

### `aderyn` panics with `Unknown evm version: osaka`

Your `foundry.toml` or a submodule's `foundry.toml` is using EVM version `osaka`, which older aderyn versions can't parse. The installer offers to pin `evm_version = "cancun"` — accept this.

For submodule configs (e.g. OpenZeppelin's `foundry.toml`), the Makefile's `aderyn` target uses `--path-excludes lib,test,script` which should bypass them.

### `JSON Error in .solhint.json`

Check the file didn't get corrupted by an editor (e.g. TextEdit's smart quotes). Re-fetch cleanly:

```bash
curl -fsSL https://raw.githubusercontent.com/ManiBAJPAI22/sift-cli/main/templates/.solhint.json -o .solhint.json
```

### `make audit` fails on `cov` with stack-too-deep

Heavy contracts with `via_ir = false` can hit this under coverage instrumentation. Add `--ir-minimum`:

```makefile
cov: reports ; forge coverage --ir-minimum ...
```

### Slither finds too many false positives

AA/upgradeable patterns trigger Slither's `arbitrary-send-erc20` and `timestamp` detectors. Either:
1. Add inline `// slither-disable-next-line <detector>` with a justification comment
2. Lower the `fail_on` threshold in `slither.config.json`
3. Remove Slither from the critical path (`make audit`), run it on-demand with `make slither`

### PR comment not appearing

The `sticky-pull-request-comment` action needs `pull-requests: write` permission. The workflow declares this at the top:

```yaml
permissions:
  contents: read
  pull-requests: write
```

If you're on a fork or restricted runner, the comment may be skipped silently. Check the action logs for permission errors.

## Roadmap

Future improvements being considered:

- **Composite GitHub Action** — consolidate workflow logic so project workflows become 6 lines instead of a full copy
- **Foundry template repo** — scaffold a new project with `npx degit` including pipeline pre-installed
- **Auto-install in Makefile** — `make audit` bootstraps missing tools (trade-off: more Makefile complexity)
- **Report diffing** — compare findings between commits, flag only *new* issues

## Project structure

```
sol-audit-pipeline/
├── install.sh                          # per-project installer
├── scripts/
│   └── install-tools.sh                # per-machine tool installer
├── templates/
│   ├── Makefile                        # audit targets
│   ├── slither.config.json             # Slither config
│   ├── .solhint.json                   # Solhint rules
│   ├── tools/
│   │   └── summary.sh                  # consolidated report generator
│   └── .github/
│       └── workflows/
│           └── audit.yml               # CI workflow
└── README.md
```

## Contributing

This is a personal tooling repo, but fixes are welcome:

1. Fork and clone
2. Make changes in `templates/` or scripts
3. Test end-to-end:

   ```bash
   cd ~/Desktop
   forge init --no-git test-project
   cd test-project
   AUDIT_PIPELINE_REPO=https://raw.githubusercontent.com/YourFork/sol-audit-pipeline/your-branch \
     curl -fsSL $AUDIT_PIPELINE_REPO/install.sh | bash
   make audit
   ```

4. Open PR

## License

MIT

## Credits

Built on top of excellent work from:
- [Foundry](https://github.com/foundry-rs/foundry) — the testing framework
- [Slither](https://github.com/crytic/slither) & [Medusa](https://github.com/crytic/medusa) — Trail of Bits
- [Aderyn](https://github.com/Cyfrin/aderyn) & [Halmos](https://github.com/a16z/halmos) — static & symbolic analysis
- [Solhint](https://github.com/protofire/solhint) — linting
- [sticky-pull-request-comment](https://github.com/marocchino/sticky-pull-request-comment) — PR comment management
