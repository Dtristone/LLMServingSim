#!/bin/bash
# ============================================================================
#  run_kv_hit_ratio_sweep.sh
#
#  End-to-end pipeline to simulate KV cache prefix hit ratio across different
#  hardware memory configurations (HBM + DRAM) using LLMServingSim.
#
#  Steps:
#    1. (Optional) Convert a user-provided hash trace to LLMServingSim format
#    2. Run prefix-caching simulations for each DRAM config (512 GB / 1 TB / 2 TB)
#    3. Parse and summarise hit-ratio results
#
#  Usage:
#    # With a hash trace file:
#    bash script/run_kv_hit_ratio_sweep.sh \
#        --hash-trace /path/to/hash_trace.jsonl \
#        --num-req 200
#
#    # With an already-converted LLMServingSim dataset:
#    bash script/run_kv_hit_ratio_sweep.sh \
#        --dataset dataset/my_converted_trace.jsonl \
#        --num-req 200
#
#    # Quick test with the bundled example trace:
#    bash script/run_kv_hit_ratio_sweep.sh --num-req 10
#
#  See --help for all options.
# ============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# ----------------------------- defaults ------------------------------------
HASH_TRACE=""
DATASET=""
NUM_REQ=100
OUTPUT_TOKENS=128
TIMESTAMP_UNIT="s"
MODEL_FILTER=""
BLOCK_SIZE=16
FP=16
LOG_LEVEL="WARNING"
RESULTS_DIR="${REPO_ROOT}/output/kv_hit_ratio"

# Cluster configs to sweep (DRAM sizes)
CONFIGS=(
    "cluster_config/kv_hit_ratio_dram_512gb.json"
    "cluster_config/kv_hit_ratio_dram_1tb.json"
    "cluster_config/kv_hit_ratio_dram_2tb.json"
)

# ----------------------------- arg parsing ---------------------------------
usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Options:
  --hash-trace PATH      Path to the input hash trace (.jsonl)
  --dataset PATH         Path to an already-converted LLMServingSim dataset (.jsonl)
                          If neither --hash-trace nor --dataset is given, the bundled
                          example_trace.jsonl is used.
  --num-req N            Number of requests to simulate (default: 100)
  --output-tokens N      Output tokens per request during conversion (default: 128)
  --timestamp-unit UNIT  Timestamp unit in hash trace: s|ms|us|ns (default: s)
  --model-filter NAME    Only include requests with this model_name during conversion
  --block-size N         KV cache block size in tokens (default: 16)
  --fp BITS              Floating-point precision in bits (default: 16)
  --log-level LEVEL      Log level: WARNING|INFO|DEBUG (default: WARNING)
  --results-dir DIR      Directory for output logs and results (default: output/kv_hit_ratio)
  --configs "A B C"      Space-separated list of cluster config paths (overrides defaults)
  -h, --help             Show this help message
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --hash-trace)     HASH_TRACE="$2"; shift 2;;
        --dataset)        DATASET="$2"; shift 2;;
        --num-req)        NUM_REQ="$2"; shift 2;;
        --output-tokens)  OUTPUT_TOKENS="$2"; shift 2;;
        --timestamp-unit) TIMESTAMP_UNIT="$2"; shift 2;;
        --model-filter)   MODEL_FILTER="$2"; shift 2;;
        --block-size)     BLOCK_SIZE="$2"; shift 2;;
        --fp)             FP="$2"; shift 2;;
        --log-level)      LOG_LEVEL="$2"; shift 2;;
        --results-dir)    RESULTS_DIR="$2"; shift 2;;
        --configs)        IFS=' ' read -r -a CONFIGS <<< "$2"; shift 2;;
        -h|--help)        usage; exit 0;;
        *) echo "Unknown option: $1"; usage; exit 1;;
    esac
done

# ----------------------------- Step 0: resolve dataset ----------------------
if [[ -n "${HASH_TRACE}" ]]; then
    echo "============================================================"
    echo "  Step 1: Converting hash trace -> LLMServingSim dataset"
    echo "============================================================"
    TRACE_BASENAME="$(basename "${HASH_TRACE}" .jsonl)"
    CONVERTED="${REPO_ROOT}/dataset/${TRACE_BASENAME}_converted.jsonl"

    CONVERT_ARGS=(
        --input "${HASH_TRACE}"
        --output "${CONVERTED}"
        --output-tokens "${OUTPUT_TOKENS}"
        --timestamp-unit "${TIMESTAMP_UNIT}"
    )
    if [[ -n "${MODEL_FILTER}" ]]; then
        CONVERT_ARGS+=(--model-filter "${MODEL_FILTER}")
    fi
    if [[ "${NUM_REQ}" -gt 0 ]]; then
        CONVERT_ARGS+=(--max-requests "${NUM_REQ}")
    fi

    python3 "${REPO_ROOT}/script/convert_hash_trace.py" "${CONVERT_ARGS[@]}"
    DATASET="${CONVERTED}"
    echo ""
elif [[ -z "${DATASET}" ]]; then
    DATASET="${REPO_ROOT}/dataset/example_trace.jsonl"
    echo "No --hash-trace or --dataset given; using bundled example_trace.jsonl"
fi

echo "Dataset: ${DATASET}"
echo "Requests: ${NUM_REQ}"
echo ""

# ----------------------------- Step 1: run simulations ---------------------
mkdir -p "${RESULTS_DIR}"

echo "============================================================"
echo "  Step 2: Running prefix-caching simulations"
echo "============================================================"
echo "  Configs to sweep:"
for cfg in "${CONFIGS[@]}"; do
    echo "    - ${cfg}"
done
echo ""

for cfg in "${CONFIGS[@]}"; do
    cfg_name="$(basename "${cfg}" .json)"
    log_file="${RESULTS_DIR}/${cfg_name}.log"
    csv_file="${RESULTS_DIR}/${cfg_name}.csv"

    echo "--------------------------------------------------------------"
    echo "  Running: ${cfg_name}"
    echo "  Log:     ${log_file}"
    echo "--------------------------------------------------------------"

    python3 "${REPO_ROOT}/main.py" \
        --cluster-config "${cfg}" \
        --fp "${FP}" \
        --block-size "${BLOCK_SIZE}" \
        --enable-prefix-caching \
        --enable-prefix-sharing \
        --prefix-storage CPU \
        --dataset "${DATASET}" \
        --output "${csv_file}" \
        --num-req "${NUM_REQ}" \
        --log-interval 1.0 \
        --log-level "${LOG_LEVEL}" \
        2>&1 | tee "${log_file}"

    echo ""
done

# ----------------------------- Step 2: parse results -----------------------
echo "============================================================"
echo "  Step 3: Parsing results"
echo "============================================================"
python3 "${REPO_ROOT}/script/parse_hit_ratio_results.py" \
    --results-dir "${RESULTS_DIR}" \
    --output-json "${RESULTS_DIR}/summary.json"

echo ""
echo "============================================================"
echo "  All done! Results are in: ${RESULTS_DIR}/"
echo "============================================================"
