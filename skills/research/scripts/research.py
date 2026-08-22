"""Retrieve URL-backed Exa evidence for a single startup as JSON."""

import argparse
import json
import os
import sys
from pathlib import Path

try:
    from exa_py import Exa
except ImportError:  # Allows tests to replace the client without the SDK installed.
    Exa = None


DEFAULT_FOCUS = (
    "team and founders, product, target customer and market, traction and freshness, "
    "funding, competitors, technical signals, risks, and unanswered questions"
)


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


def research_company(name, website, focus, api_key):
    """Return Exa evidence results for one company and an optional missing area."""
    if not api_key:
        raise RuntimeError("EXA_API_KEY is required.")
    if Exa is None:
        raise RuntimeError("exa-py is required. Install it with: pip install exa-py")

    focus_text = focus or DEFAULT_FOCUS
    website_text = website or "website unknown"
    query = f"Research startup {name} ({website_text}): {focus_text}"
    response = Exa(api_key=api_key).search(
        query,
        type="auto",
        num_results=10,
        contents={"highlights": True},
    )
    return {
        "company": name,
        "website": website,
        "focus": focus,
        "query": query,
        "results": [_serialize(result) for result in response.results],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True)
    parser.add_argument("--website")
    parser.add_argument(
        "--focus",
        help="A single missing evidence area for the one permitted targeted retry.",
    )
    args = parser.parse_args()

    try:
        output = research_company(
            args.name, args.website, args.focus, _load_api_key()
        )
    except Exception as error:
        print(f"Exa research failed: {error}", file=sys.stderr)
        return 1

    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
