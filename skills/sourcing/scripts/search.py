"""Search Exa for startup candidates and emit retrieval results as JSON."""

import argparse
import json
import os
import sys

try:
    from exa_py import Exa
except ImportError:  # Allows the module's pure serialization to be tested without the SDK.
    Exa = None


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
            args.topic, args.thesis, args.target_count, os.environ.get("EXA_API_KEY")
        )
    except Exception as error:
        print(f"Exa sourcing failed: {error}", file=sys.stderr)
        return 1

    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
