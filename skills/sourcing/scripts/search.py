"""Search Exa for startup candidates and emit retrieval results as JSON."""

import argparse
import json
import os
import sys
from pathlib import Path

try:
    from exa_py import Exa
except ImportError:  # Allows the module's pure serialization to be tested without the SDK.
    Exa = None


def _load_api_key():
    api_key = os.environ.get("EXA_API_KEY")
    if api_key:
        return api_key

    try:
        lines = (Path.cwd() / ".env.local").read_text(encoding="utf-8").splitlines()
    except OSError:
        return None

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            if line == "EXA_API_KEY":
                return None
            continue
        key, value = (part.strip() for part in line.split("=", 1))
        if key != "EXA_API_KEY":
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        return value or None
    return None


def _serialize(result):
    return {
        "title": getattr(result, "title", None),
        "url": getattr(result, "url", None),
        "published_date": getattr(result, "published_date", None),
        "highlights": list(getattr(result, "highlights", None) or []),
    }


def search_candidates(topic, thesis, target_count, api_key):
    """Return Exa company-search results for a sourcing stage."""
    if not api_key:
        raise RuntimeError("EXA_API_KEY is required.")
    if Exa is None:
        raise RuntimeError("exa-py is required. Install it with: pip install exa-py")

    query = f"Startup companies for: {topic}. Investment thesis: {thesis}"
    response = Exa(api_key=api_key).search(
        query,
        category="company",
        num_results=target_count,
        contents={"highlights": True},
    )
    return {"query": query, "results": [_serialize(result) for result in response.results]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topic", required=True)
    parser.add_argument("--thesis", required=True)
    parser.add_argument("--target-count", type=int, default=15)
    args = parser.parse_args()

    if args.target_count < 1:
        parser.error("--target-count must be at least 1")

    try:
        output = search_candidates(
            args.topic, args.thesis, args.target_count, _load_api_key()
        )
    except Exception as error:
        print(f"Exa sourcing failed: {error}", file=sys.stderr)
        return 1

    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
