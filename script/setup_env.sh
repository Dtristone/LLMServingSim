#!/bin/bash
# ============================================================================
#  setup_env.sh — Install and build LLMServingSim from scratch
# ============================================================================
#  Run this script ONCE from the repository root:
#      bash script/setup_env.sh
#
#  Prerequisites:
#      - Python 3.8+ with pip
#      - CMake 3.14+, g++ / clang with C++17 support
#      - git (submodules will be initialised automatically)
# ============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
echo "============================================"
echo "  LLMServingSim — Environment Setup"
echo "============================================"
echo "Repository root: ${REPO_ROOT}"
echo ""

# ------------------------------------------------------------------
# 1. Initialise & update git submodules (astra-sim etc.)
# ------------------------------------------------------------------
echo "[1/4] Initialising git submodules..."
cd "${REPO_ROOT}"
git submodule update --init --recursive
echo "      Done."
echo ""

# ------------------------------------------------------------------
# 2. Install Python dependencies
# ------------------------------------------------------------------
echo "[2/4] Installing Python dependencies..."
pip3 install --quiet pyinstrument scikit-learn numpy
echo "      Done."
echo ""

# ------------------------------------------------------------------
# 3. Build Chakra & ASTRA-Sim (same as compile.sh)
# ------------------------------------------------------------------
echo "[3/4] Building Chakra (graph frontend)..."
(
    cd "${REPO_ROOT}/astra-sim/extern/graph_frontend/chakra"
    pip3 install .
)
echo "      Done."
echo ""

echo "[4/4] Building ASTRA-Sim (analytical backend)..."
(
    cd "${REPO_ROOT}/astra-sim"
    bash ./build/astra_analytical/build.sh
)
echo "      Done."
echo ""

# ------------------------------------------------------------------
# Verification
# ------------------------------------------------------------------
BINARY="${REPO_ROOT}/astra-sim/build/astra_analytical/build/AnalyticalAstra/bin/AnalyticalAstra"
if [ -x "${BINARY}" ]; then
    echo "============================================"
    echo "  Build successful!"
    echo "  Binary: ${BINARY}"
    echo "============================================"
else
    echo "============================================"
    echo "  WARNING: Binary not found at expected path."
    echo "  Expected: ${BINARY}"
    echo "  The build may have failed — check output above."
    echo "============================================"
    exit 1
fi
