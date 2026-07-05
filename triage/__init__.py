"""sol-audit-pipeline AI triage layer.

Turns raw scanner output (Slither SARIF + Aderyn markdown) into adjudicated,
de-duplicated findings using a self-hosted open-weights model. Stateless across
the scanners; stateful across runs via a fingerprint-keyed ledger.

Pure-stdlib at runtime (urllib for the Ollama call) so it ships and runs in CI
without pulling a dependency tree. The training/ tree is separate and is the
only part that needs heavy ML deps.
"""

__version__ = "0.1.0"
