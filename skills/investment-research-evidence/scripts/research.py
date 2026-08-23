"""Retrieve one bounded evidence pass for a selected company."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

try:
    from exa_py import Exa
except ImportError:
    Exa = None


EXIT_INPUT = 2
EXIT_RUNTIME = 3
EXIT_AUTH = 4
EXIT_PROVIDER = 5
EXIT_WRITE = 6
MAX_RESULTS = 5
MAX_HIGHLIGHT_CHARS = 400
MAX_STDERR_CHARS = 2000
ALLOWED_CATEGORIES = ("team", "product", "market", "traction", "competitors", "freshness")


class RetrievalError(RuntimeError):
    def __init__(self, message: str, code: int):
        super().__init__(message)
        self.code = code


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def provider_failure_code(error: Exception) -> int:
    status = getattr(error, "status_code", None)
    response = getattr(error, "response", None)
    status = status or getattr(response, "status_code", None)
    message = str(error).lower()
    if status in {401, 403} or "unauthorized" in message or "authentication" in message:
        return EXIT_AUTH
    return EXIT_PROVIDER


def load_api_key(cwd: str | Path | None = None) -> tuple[str | None, str]:
    value = os.environ.get("EXA_API_KEY")
    if value:
        return value, "environment"
    path = _find_env_local(Path(cwd or Path.cwd()))
    if path is None:
        path = _find_env_local(Path(__file__).resolve().parent)
    if path is None:
        return None, "missing"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None, "missing"
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, raw = (part.strip() for part in line.split("=", 1))
        if key != "EXA_API_KEY":
            continue
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
            raw = raw[1:-1]
        return (raw or None), "env_local" if raw else "missing"
    return None, "missing"


def _find_env_local(start: Path) -> Path | None:
    current = start.resolve()
    if current.is_file():
        current = current.parent
    lineage = (current, *current.parents)
    repository_index = next(
        (index for index, directory in enumerate(lineage) if (directory / ".git").exists()),
        None,
    )
    search_directories = lineage[: repository_index + 1] if repository_index is not None else (current,)
    for directory in search_directories:
        candidate = directory / ".env.local"
        if candidate.is_file():
            return candidate
    return None


def canonicalize_url(url: str | None) -> str | None:
    if not url:
        return None
    text = str(url).strip()
    parsed = urlsplit(text)
    if not parsed.scheme or not parsed.hostname:
        return text or None
    scheme = parsed.scheme.lower()
    host = parsed.hostname.lower()
    try:
        port = parsed.port
    except ValueError:
        port = None
    netloc = host
    if port and not ((scheme == "https" and port == 443) or (scheme == "http" and port == 80)):
        netloc = f"{host}:{port}"
    return urlunsplit((scheme, netloc, parsed.path.rstrip("/"), parsed.query, ""))


def _attribute(value, name, default=None):
    return value.get(name, default) if isinstance(value, dict) else getattr(value, name, default)


def _text(value, limit: int = 500) -> str | None:
    return None if value is None else str(value)[:limit]


def serialize_results(results) -> list[dict]:
    seen = set()
    serialized = []
    for result in results:
        url = canonicalize_url(_attribute(result, "url"))
        key = url or f"title:{_attribute(result, 'title', '')}"
        if key in seen:
            continue
        seen.add(key)
        raw_highlights = list(_attribute(result, "highlights", []) or [])
        highlights = [str(raw_highlights[0])[:MAX_HIGHLIGHT_CHARS]] if raw_highlights else []
        serialized.append(
            {
                "title": _text(_attribute(result, "title")),
                "url": url,
                "published_date": _text(_attribute(result, "published_date"), 100),
                "highlights": highlights,
            }
        )
        if len(serialized) >= MAX_RESULTS:
            break
    return serialized


def atomic_write_json(path: str | Path, value) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=destination.parent,
            prefix=f".{destination.name}.", suffix=".tmp", delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(value, handle, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        json.loads(temporary.read_text(encoding="utf-8"))
        os.replace(temporary, destination)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()
    return destination


def normalize_focus(categories) -> list[str]:
    if not isinstance(categories, (list, tuple)) or not categories:
        raise RetrievalError("retry focus must contain at least one missing category", EXIT_INPUT)
    normalized = []
    for category in ALLOWED_CATEGORIES:
        if category in categories:
            normalized.append(category)
    invalid = sorted({str(item) for item in categories if item not in ALLOWED_CATEGORIES})
    if invalid:
        raise RetrievalError(f"unsupported missing categories: {', '.join(invalid)}", EXIT_INPUT)
    return normalized


def research_company(
    company_name: str, website: str | None, focus, api_key: str | None,
) -> dict:
    if not isinstance(company_name, str) or not company_name.strip():
        raise RetrievalError("company name must be non-empty", EXIT_INPUT)
    categories = normalize_focus(focus) if focus is not None else []
    if not api_key:
        raise RetrievalError("EXA_API_KEY is unavailable; use the native web fallback", EXIT_AUTH)
    if Exa is None:
        raise RetrievalError("exa-py is unavailable; use the native web fallback", EXIT_RUNTIME)
    focus_text = ", ".join(categories) if categories else "team, product, market, traction, competitors, freshness"
    site_text = f" Official website: {website}." if website else ""
    query = f'Research startup "{company_name.strip()}" for investment evidence about {focus_text}.{site_text}'
    try:
        response = Exa(api_key=api_key).search(
            query,
            num_results=MAX_RESULTS,
            contents={"highlights": True},
        )
    except Exception as error:
        raise RetrievalError(f"Exa research failed: {error}", provider_failure_code(error)) from error
    try:
        results = serialize_results(response.results)
    except (AttributeError, TypeError, ValueError) as error:
        raise RetrievalError(f"Exa research response could not be serialized: {error}", EXIT_WRITE) from error
    return {
        "query": query,
        "provider": "exa",
        "retrieved_at": utc_now(),
        "status": "ok",
        "exit_code": 0,
        "missing_categories": categories,
        "results": results,
    }


def _find_candidate(path: Path, slug: str) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RetrievalError(f"invalid candidates artifact: {error}", EXIT_INPUT) from error
    if not isinstance(payload, dict):
        raise RetrievalError("candidates artifact must be a JSON object", EXIT_INPUT)
    retained = payload.get("retained_candidates", payload.get("candidates", []))
    if not isinstance(retained, list):
        raise RetrievalError("candidates must be an array", EXIT_INPUT)
    matches = [item for item in retained if isinstance(item, dict) and item.get("slug") == slug]
    if len(matches) != 1:
        raise RetrievalError(f"candidate slug must match exactly once: {slug}", EXIT_INPUT)
    return matches[0]


def _failure_envelope(error: RetrievalError, api_key: str | None, focus) -> dict:
    message = str(error).replace(api_key, "[redacted]") if api_key else str(error)
    return {
        "query": "unavailable",
        "provider": "exa",
        "retrieved_at": utc_now(),
        "status": "failed",
        "exit_code": error.code,
        "error": message,
        "stderr": message[:MAX_STDERR_CHARS],
        "missing_categories": list(focus or []),
        "results": [],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--focus", nargs="*")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    api_key, _ = load_api_key()
    try:
        if args.focus == []:
            raise RetrievalError("--focus cannot be empty", EXIT_INPUT)
        candidate = _find_candidate(args.candidates, args.slug)
        payload = research_company(
            candidate.get("name"), candidate.get("website"), args.focus, api_key
        )
        code = 0
    except RetrievalError as error:
        payload = _failure_envelope(error, api_key, args.focus)
        code = error.code
    try:
        atomic_write_json(args.output, payload)
    except (OSError, TypeError, ValueError) as error:
        print(json.dumps({"status": "failed", "exit_code": EXIT_WRITE, "error": str(error)}), file=sys.stderr)
        return EXIT_WRITE
    print(json.dumps({
        "status": payload["status"], "provider": "exa", "output": str(args.output),
        "exit_code": code, "result_count": len(payload["results"]),
    }, separators=(",", ":")))
    if code:
        print(payload.get("error", "retrieval failed"), file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
