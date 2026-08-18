#!/usr/bin/env bash
# ===========================================================================
# make_demo.sh — Run the ComputePilot demo suite locally.
#
# Usage:
#   ./scripts/make_demo.sh              # run full suite
#   ./scripts/make_demo.sh --coverage   # run with coverage report
# ===========================================================================

set -euo pipefail
cd "$(git rev-parse --show-toplevel 2>/dev/null || echo "$(dirname "$0")/..")"

COVERAGE=false
if [[ "${1:-}" == "--coverage" ]]; then
    COVERAGE=true
fi

echo "▸ Activating environment..."
if [ -d .venv ]; then
    source .venv/bin/activate
fi

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║           ComputePilot — Demo Suite                         ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# ── Static checks ──────────────────────────────────────────────────────
echo "─── ruff check ───"
ruff check sciflow/ tests/ scripts/
echo "✓ ruff passed"
echo ""

echo "─── mypy --strict ───"
mypy --strict sciflow/
echo "✓ mypy passed"
echo ""

# ── Dependency check ───────────────────────────────────────────────────
echo "─── dependency check ───"
python scripts/check_deps.py
echo ""

# ── Unit + integration tests ──────────────────────────────────────────
echo "─── unit + integration tests ───"
if $COVERAGE; then
    python -m pytest tests/unit/ tests/integration/ \
        --cov=sciflow --cov-report=term --cov-report=html
else
    python -m pytest tests/unit/ tests/integration/ -v
fi
echo ""

# ── E2E demo tests ────────────────────────────────────────────────────
echo "─── e2e demo tests ───"
if $COVERAGE; then
    python -m pytest tests/e2e/ \
        --cov=sciflow --cov-append --cov-report=term --cov-report=html
else
    python -m pytest tests/e2e/ -v
fi
echo ""

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║           All demos passed!                                 ║"
echo "╚══════════════════════════════════════════════════════════════╝"

if $COVERAGE; then
    echo ""
    echo "Coverage report: htmlcov/index.html"
fi