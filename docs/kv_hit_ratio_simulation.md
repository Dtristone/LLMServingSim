# KV Cache Hit Ratio Simulation Guide

This guide explains how to simulate **KV cache prefix hit ratio** across different
hardware memory configurations (HBM + DRAM) using LLMServingSim, starting from a
hash-based LLM request trace.

## Quick Start

```bash
# 1. Install & build LLMServingSim (one-time setup)
bash script/setup_env.sh

# 2. Run the full simulation sweep with your hash trace
bash script/run_kv_hit_ratio_sweep.sh \
    --hash-trace /path/to/your_hash_trace.jsonl \
    --num-req 200 \
    --model-filter glm-5
```

Results will be printed to the terminal and saved under `output/kv_hit_ratio/`.

---

## Components

| File | Description |
| --- | --- |
| `script/setup_env.sh` | One-time environment setup (submodules, Chakra, ASTRA-Sim build) |
| `script/convert_hash_trace.py` | Convert hash trace → LLMServingSim `.jsonl` dataset |
| `script/run_kv_hit_ratio_sweep.sh` | Orchestrate simulations across DRAM configs |
| `script/parse_hit_ratio_results.py` | Parse log files and produce summary tables |
| `cluster_config/kv_hit_ratio_dram_512gb.json` | H100 (80 GB HBM) + 512 GB DRAM |
| `cluster_config/kv_hit_ratio_dram_1tb.json` | H100 (80 GB HBM) + 1 TB DRAM |
| `cluster_config/kv_hit_ratio_dram_2tb.json` | H100 (80 GB HBM) + 2 TB DRAM |
| `model_config/glm-5/glm-5.json` | GLM-5 model architecture config |

---

## Input Hash Trace Format

Your input trace file should be a `.jsonl` file (one JSON object per line):

```json
{"timestamp": 0.0, "model_name": "glm-5", "hash_trace": [1001, 2002, 3003, 4004, 5005]}
{"timestamp": 0.5, "model_name": "glm-5", "hash_trace": [1001, 2002, 3003, 6006, 7007]}
{"timestamp": 1.0, "model_name": "glm-5", "hash_trace": [1001, 2002, 8008, 9009]}
```

| Field | Type | Description |
| --- | --- | --- |
| `timestamp` | float | Request arrival time (seconds by default; see `--timestamp-unit`) |
| `model_name` | string | Model identifier (e.g., `"glm-5"`) |
| `hash_trace` | list[int] | Hash values representing the KV blocks / token sequence |

The converter maps each unique hash value to a stable integer token ID. Shared
prefixes in the hash trace (e.g., `[1001, 2002, 3003]` above) will be
detected by the RadixAttention prefix cache during simulation.

---

## Step-by-Step Workflow

### Step 1: Install & Build

```bash
bash script/setup_env.sh
```

This initialises git submodules, installs Chakra, and compiles ASTRA-Sim.

### Step 2: Convert Hash Trace

```bash
python3 script/convert_hash_trace.py \
    --input /path/to/hash_trace.jsonl \
    --output dataset/glm5_trace.jsonl \
    --timestamp-unit s \
    --model-filter glm-5
```

Options:
- `--output-tokens N` — Fixed output tokens per request (default: 128; does not affect hit ratio)
- `--max-requests N` — Limit requests (0 = all)
- `--timestamp-unit {s,ms,us,ns}` — Unit of the `timestamp` field

### Step 3: Run Simulation Sweep

```bash
bash script/run_kv_hit_ratio_sweep.sh \
    --dataset dataset/glm5_trace.jsonl \
    --num-req 200
```

Or run individual configurations manually:

```bash
python3 main.py \
    --cluster-config cluster_config/kv_hit_ratio_dram_1tb.json \
    --fp 16 --block-size 16 \
    --enable-prefix-caching \
    --enable-prefix-sharing --prefix-storage CPU \
    --dataset dataset/glm5_trace.jsonl \
    --output output/kv_hit_ratio/dram_1tb.csv \
    --num-req 200 --log-interval 1.0
```

### Step 4: Parse Results

```bash
python3 script/parse_hit_ratio_results.py \
    --results-dir output/kv_hit_ratio \
    --output-json output/kv_hit_ratio/summary.json
```

---

## Hardware Configurations

The three provided cluster configs simulate different DRAM sizes paired with an
NVIDIA H100 GPU (80 GB HBM3):

| Config | NPU (HBM) | DRAM (CPU Memory) | HBM BW | DRAM BW |
| --- | --- | --- | --- | --- |
| `kv_hit_ratio_dram_512gb.json` | 80 GB | 512 GB | 3350 GB/s | 512 GB/s |
| `kv_hit_ratio_dram_1tb.json` | 80 GB | 1024 GB (1 TB) | 3350 GB/s | 512 GB/s |
| `kv_hit_ratio_dram_2tb.json` | 80 GB | 2048 GB (2 TB) | 3350 GB/s | 512 GB/s |

The simulator uses:
- **NPU memory (HBM)** as the primary KV cache (RadixAttention prefix cache)
- **CPU memory (DRAM)** as the second-tier prefix cache pool (`--prefix-storage CPU`)

With `--enable-prefix-caching` and `--enable-prefix-sharing --prefix-storage CPU`,
the simulator reports:
- **NPU prefix hit ratio**: fraction of prompt tokens served from HBM KV cache
- **CPU prefix hit ratio**: fraction served from DRAM after HBM miss
- **Total prefix hit ratio**: combined hit ratio across both tiers

Larger DRAM means more room for evicted KV blocks, increasing the total hit ratio.

---

## Customising Configurations

### Add more DRAM sizes

Copy an existing config and change `cpu_mem.mem_size`:

```json
{
    "nodes": [{
        "cpu_mem": { "mem_size": 4096, "mem_bw": 512, "mem_latency": 0 },
        ...
    }]
}
```

Then add the path to the `--configs` option:

```bash
bash script/run_kv_hit_ratio_sweep.sh \
    --configs "cluster_config/kv_hit_ratio_dram_512gb.json cluster_config/kv_hit_ratio_dram_1tb.json cluster_config/kv_hit_ratio_dram_2tb.json cluster_config/kv_hit_ratio_dram_4tb.json"
```

### Use a different GPU

Change `npu_mem.mem_size` and `hardware` in the cluster config. The simulator
has built-in performance models for `A6000` (48 GB) and `H100` (80 GB).

### Use the GLM-5 model config

The provided `model_config/glm-5/glm-5.json` file defines GLM-5 architecture
parameters. To use it in simulations, set `"model_name": "glm-5/glm-5"` in your
cluster config **and** provide a matching performance model under
`llm_profile/perf_models/{hardware}/glm-5/glm-5/tp{N}/layers.csv`.

> **Note:** The default cluster configs use `meta-llama/Llama-3.1-8B` which has
> existing performance models. The KV cache hit ratio depends only on the token
> ID sequences in your trace, not on the model's computation profile, so results
> are representative regardless of which model config is used for the simulation
> backend.

---

## Output

### Terminal output

```
======================================================================
  KV Cache Hit Ratio vs. DRAM Size Summary
======================================================================
  DRAM Size                NPU (HBM) Hit%         Total Hit%
----------------------------------------------------------------------
  512GB                             24.00              40.00
  1TB                               24.00              54.00
  2TB                               24.00              62.00
======================================================================
```

### Output files

| File | Description |
| --- | --- |
| `output/kv_hit_ratio/*.log` | Full simulation stdout per config |
| `output/kv_hit_ratio/*.csv` | Per-request latency metrics (TTFT, TPOT, ITL) |
| `output/kv_hit_ratio/summary.json` | Machine-readable parsed results |
