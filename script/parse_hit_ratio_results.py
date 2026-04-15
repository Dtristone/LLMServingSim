#!/usr/bin/env python3
"""
Parse KV hit ratio results from LLMServingSim output logs.

Reads simulation stdout log files produced by run_kv_hit_ratio_sweep.sh and
extracts prefix-cache hit ratio metrics grouped by hardware configuration.

Usage:
    python script/parse_hit_ratio_results.py --results-dir output/kv_hit_ratio
"""

import argparse
import json
import os
import re
import sys


def parse_log(log_path):
    """Extract key metrics from a single simulation log file."""
    metrics = {}
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            m = re.search(r"Total requested prompt tokens:\s+(\d+)", line)
            if m:
                metrics["total_requested_tokens"] = int(m.group(1))

            m = re.search(r"NPU prefix hit prompt tokens:\s+(\d+)", line)
            if m:
                metrics["npu_hit_tokens"] = int(m.group(1))

            m = re.search(r"NPU prefix hit ratio \(%\):\s+([\d.]+)", line)
            if m:
                metrics["npu_hit_ratio_pct"] = float(m.group(1))

            m = re.search(r"CPU prefix hit prompt tokens:\s+(\d+)", line)
            if m:
                metrics["cpu_hit_tokens"] = int(m.group(1))

            m = re.search(r"CPU prefix hit ratio \(%\):\s+([\d.]+)", line)
            if m:
                metrics["cpu_hit_ratio_pct"] = float(m.group(1))

            m = re.search(r"Total prefix hit ratio \(%\):\s+([\d.]+)", line)
            if m:
                metrics["total_hit_ratio_pct"] = float(m.group(1))

            m = re.search(r"Total requests:\s+(\d+)", line)
            if m:
                metrics["total_requests"] = int(m.group(1))

            m = re.search(r"Request throughput \(req/s\):\s+([\d.]+)", line)
            if m:
                metrics["request_throughput"] = float(m.group(1))

            m = re.search(r"Total token throughput \(tok/s\):\s+([\d.]+)", line)
            if m:
                metrics["token_throughput"] = float(m.group(1))

            m = re.search(r"Total simulation time:\s+(.+)", line)
            if m:
                metrics["simulation_time"] = m.group(1).strip()

    return metrics


def main():
    parser = argparse.ArgumentParser(
        description="Parse KV hit ratio simulation results"
    )
    parser.add_argument(
        "--results-dir", "-d", required=True,
        help="Directory containing simulation log files (*.log)"
    )
    parser.add_argument(
        "--output-json", "-o", default=None,
        help="Optional: write parsed results as JSON to this path"
    )
    args = parser.parse_args()

    results_dir = args.results_dir
    if not os.path.isdir(results_dir):
        print(f"ERROR: Directory not found: {results_dir}", file=sys.stderr)
        sys.exit(1)

    log_files = sorted(
        f for f in os.listdir(results_dir) if f.endswith(".log")
    )

    if not log_files:
        print(f"ERROR: No .log files found in {results_dir}", file=sys.stderr)
        sys.exit(1)

    all_results = []
    print("=" * 90)
    print(f"{'Config':<40} {'NPU Hit%':>10} {'CPU Hit%':>10} "
          f"{'Total Hit%':>10} {'Reqs':>8}")
    print("=" * 90)

    for log_file in log_files:
        log_path = os.path.join(results_dir, log_file)
        metrics = parse_log(log_path)
        config_name = os.path.splitext(log_file)[0]

        npu_hit = metrics.get("npu_hit_ratio_pct", 0.0)
        cpu_hit = metrics.get("cpu_hit_ratio_pct", 0.0)
        total_hit = metrics.get("total_hit_ratio_pct", 0.0)
        reqs = metrics.get("total_requests", 0)

        print(f"{config_name:<40} {npu_hit:>10.2f} {cpu_hit:>10.2f} "
              f"{total_hit:>10.2f} {reqs:>8}")

        metrics["config_name"] = config_name
        all_results.append(metrics)

    print("=" * 90)

    # Summary table: group by DRAM size
    print("\n")
    print("=" * 70)
    print("  KV Cache Hit Ratio vs. DRAM Size Summary")
    print("=" * 70)
    print(f"  {'DRAM Size':<20} {'NPU (HBM) Hit%':>18} {'Total Hit%':>18}")
    print("-" * 70)

    for r in all_results:
        name = r["config_name"]
        # Try to extract DRAM size from config name
        dram_label = name
        m = re.search(r"dram_(\d+[a-zA-Z]+)", name)
        if m:
            dram_label = m.group(1).upper()

        npu_hit = r.get("npu_hit_ratio_pct", 0.0)
        total_hit = r.get("total_hit_ratio_pct", 0.0)
        print(f"  {dram_label:<20} {npu_hit:>18.2f} {total_hit:>18.2f}")

    print("=" * 70)

    if args.output_json:
        os.makedirs(os.path.dirname(args.output_json) or ".", exist_ok=True)
        with open(args.output_json, "w", encoding="utf-8") as f:
            json.dump(all_results, f, indent=2)
        print(f"\nJSON results written to: {args.output_json}")


if __name__ == "__main__":
    main()
