#!/usr/bin/env python3
"""
Convert a hash-based LLM trace to the LLMServingSim .jsonl dataset format.

Expected input format (one JSON object per line):
    {
        "timestamp": <float or int>,        # arrival time (seconds or milliseconds)
        "model_name": "glm-5",              # model identifier
        "hash_trace": [<int>, <int>, ...]    # list of hash values representing KV blocks
    }

The converter maps each unique hash value to a stable integer token ID so that the
RadixAttention prefix cache in LLMServingSim can detect shared prefixes across
requests.  The "hash_trace" list is treated as the sequence of input token IDs
(one hash per token or per block — the simulator only cares about matching prefixes
of the ID sequence).

Output format (LLMServingSim .jsonl):
    {
        "input_toks": <int>,
        "output_toks": <int>,
        "arrival_time_ns": <int>,
        "input_tok_ids": [<int>, ...]
    }

Usage:
    python script/convert_hash_trace.py \\
        --input  /path/to/hash_trace.jsonl \\
        --output dataset/glm5_hash_trace.jsonl \\
        [--output-tokens 128] \\
        [--timestamp-unit s]
"""

import argparse
import json
import sys
import os


def parse_args():
    parser = argparse.ArgumentParser(
        description="Convert hash-based LLM trace to LLMServingSim dataset format"
    )
    parser.add_argument(
        "--input", "-i", required=True,
        help="Path to the input hash trace file (.jsonl)"
    )
    parser.add_argument(
        "--output", "-o", required=True,
        help="Path to write the converted LLMServingSim dataset (.jsonl)"
    )
    parser.add_argument(
        "--output-tokens", type=int, default=128,
        help="Fixed number of output tokens per request (default: 128). "
             "This does not affect prefix cache hit ratio."
    )
    parser.add_argument(
        "--timestamp-unit", choices=["s", "ms", "us", "ns"], default="s",
        help="Unit of the timestamp field in the input trace (default: s). "
             "Converted to nanoseconds for LLMServingSim."
    )
    parser.add_argument(
        "--max-requests", type=int, default=0,
        help="Maximum number of requests to convert (0 = all)"
    )
    parser.add_argument(
        "--model-filter", type=str, default=None,
        help="Only include requests matching this model_name (default: include all)"
    )
    return parser.parse_args()


UNIT_TO_NS = {
    "s": 1_000_000_000,
    "ms": 1_000_000,
    "us": 1_000,
    "ns": 1,
}


def convert_trace(input_path, output_path, output_tokens, timestamp_unit,
                  max_requests, model_filter):
    """Read hash trace and write LLMServingSim .jsonl dataset."""
    multiplier = UNIT_TO_NS[timestamp_unit]
    hash_to_id = {}
    next_id = 1  # start from 1 (0 can be reserved)
    request_count = 0

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    with open(input_path, "r", encoding="utf-8") as fin, \
         open(output_path, "w", encoding="utf-8") as fout:

        for line_no, line in enumerate(fin, 1):
            line = line.strip()
            if not line:
                continue

            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"WARNING: Skipping line {line_no}: {e}", file=sys.stderr)
                continue

            # ---- extract fields ----
            if model_filter and obj.get("model_name", "") != model_filter:
                continue

            timestamp = obj.get("timestamp", 0)
            hash_list = obj.get("hash_trace", [])

            if not hash_list:
                print(f"WARNING: Skipping line {line_no}: empty hash_trace",
                      file=sys.stderr)
                continue

            # ---- map hashes -> stable token IDs ----
            token_ids = []
            for h in hash_list:
                h_key = h  # could be int or string
                if h_key not in hash_to_id:
                    hash_to_id[h_key] = next_id
                    next_id += 1
                token_ids.append(hash_to_id[h_key])

            try:
                arrival_ns = int(float(timestamp) * multiplier)
            except (TypeError, ValueError):
                print(f"WARNING: Skipping line {line_no}: invalid timestamp "
                      f"value {timestamp!r}", file=sys.stderr)
                continue

            record = {
                "input_toks": len(token_ids),
                "output_toks": output_tokens,
                "arrival_time_ns": arrival_ns,
                "input_tok_ids": token_ids,
            }
            fout.write(json.dumps(record, ensure_ascii=False) + "\n")
            request_count += 1

            if max_requests > 0 and request_count >= max_requests:
                break

    print(f"Converted {request_count} requests "
          f"({len(hash_to_id)} unique hash values) -> {output_path}")
    return request_count


def main():
    args = parse_args()
    count = convert_trace(
        input_path=args.input,
        output_path=args.output,
        output_tokens=args.output_tokens,
        timestamp_unit=args.timestamp_unit,
        max_requests=args.max_requests,
        model_filter=args.model_filter,
    )
    if count == 0:
        print("WARNING: No requests were converted. Check your input file "
              "and --model-filter.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
