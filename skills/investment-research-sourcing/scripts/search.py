"""Run offline assignment sourcing or the legacy Exa retrieval helper."""

from __future__ import annotations

import argparse
import importlib.util
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
MAX_RESULTS = 20
MAX_HIGHLIGHT_CHARS = 400
MAX_STDERR_CHARS = 2000


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


def serialize_results(results, *, limit: int) -> list[dict]:
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
        if len(serialized) >= min(limit, MAX_RESULTS):
            break
    return serialized


def atomic_write_json(path: str | Path, value) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
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


def _seed_text(input_data: dict) -> str:
    seed = input_data.get("seed") if isinstance(input_data, dict) else None
    if not isinstance(seed, dict) or seed.get("type") not in {"topic", "urls", "feed"}:
        raise RetrievalError("seed.type must be topic, urls, or feed", EXIT_INPUT)
    value = seed.get("value")
    if seed["type"] == "urls":
        if not isinstance(value, list) or not value:
            raise RetrievalError("seed.value must be a non-empty URL list", EXIT_INPUT)
        return ", ".join(str(item) for item in value)
    if not isinstance(value, str) or not value.strip():
        raise RetrievalError("seed.value must be non-empty", EXIT_INPUT)
    return value.strip()


def _target_count(input_data: dict) -> int:
    sourcing = input_data.get("sourcing", {}) if isinstance(input_data, dict) else {}
    value = sourcing.get("target_count", 15) if isinstance(sourcing, dict) else 15
    if isinstance(value, bool) or not isinstance(value, int) or not 10 <= value <= MAX_RESULTS:
        raise RetrievalError("sourcing.target_count must be an integer from 10 through 20", EXIT_INPUT)
    return value


def build_envelope(
    *, query: str, results, status: str = "ok", exit_code: int = 0,
    error: str | None = None, stderr: str | None = None, limit: int = MAX_RESULTS,
) -> dict:
    payload = {
        "query": query,
        "provider": "exa",
        "retrieved_at": utc_now(),
        "status": status,
        "exit_code": exit_code,
        "results": serialize_results(results, limit=limit),
    }
    if error:
        payload["error"] = error
    if stderr:
        payload["stderr"] = stderr[:MAX_STDERR_CHARS]
    return payload


def search_candidates(input_data: dict, thesis: str, api_key: str | None) -> dict:
    seed_text = _seed_text(input_data)
    target_count = _target_count(input_data)
    if not thesis.strip():
        raise RetrievalError("thesis must be non-empty", EXIT_INPUT)
    if not api_key:
        raise RetrievalError("EXA_API_KEY is unavailable; use the native web fallback", EXIT_AUTH)
    if Exa is None:
        raise RetrievalError("exa-py is unavailable; use the native web fallback", EXIT_RUNTIME)
    query = f"Startup companies for: {seed_text}. Investment thesis: {thesis.strip()}"
    try:
        response = Exa(api_key=api_key).search(
            query,
            category="company",
            num_results=target_count,
            contents={"highlights": True},
        )
    except Exception as error:
        raise RetrievalError(f"Exa sourcing failed: {error}", provider_failure_code(error)) from error
    try:
        payload = build_envelope(query=query, results=response.results, limit=target_count)
    except (AttributeError, TypeError, ValueError) as error:
        raise RetrievalError(f"Exa sourcing response could not be serialized: {error}", EXIT_WRITE) from error
    payload.update(
        {
            "requested_count": target_count,
            "actual_result_count": len(payload["results"]),
        }
    )
    return payload


def _failure_envelope(query: str, error: RetrievalError, api_key: str | None) -> dict:
    message = str(error).replace(api_key, "[redacted]") if api_key else str(error)
    payload = build_envelope(
        query=query,
        results=[],
        status="failed",
        exit_code=error.code,
        error=message,
        stderr=message,
    )
    payload.update({"requested_count": None, "actual_result_count": 0})
    return payload


def _legacy_main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--thesis", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    api_key, _ = load_api_key()
    query = "unavailable"
    try:
        input_data = json.loads(args.input.read_text(encoding="utf-8"))
        thesis = args.thesis.read_text(encoding="utf-8")
        query = f"Startup companies for: {_seed_text(input_data)}. Investment thesis: {thesis.strip()}"
        payload = search_candidates(input_data, thesis, api_key)
        code = 0
    except (OSError, json.JSONDecodeError) as error:
        retrieval_error = RetrievalError(f"invalid input artifact: {error}", EXIT_INPUT)
        payload = _failure_envelope(query, retrieval_error, api_key)
        code = retrieval_error.code
    except RetrievalError as error:
        payload = _failure_envelope(query, error, api_key)
        code = error.code
    try:
        atomic_write_json(args.output, payload)
    except (OSError, TypeError, ValueError) as error:
        print(json.dumps({"status": "failed", "exit_code": EXIT_WRITE, "error": str(error)}), file=sys.stderr)
        return EXIT_WRITE
    print(
        json.dumps(
            {
                "status": payload["status"],
                "provider": "exa",
                "output": str(args.output),
                "exit_code": code,
                "result_count": len(payload["results"]),
            },
            separators=(",", ":"),
        )
    )
    if code:
        print(payload.get("error", "retrieval failed"), file=sys.stderr)
    return code


def _load_source_adapters():
    path = Path(__file__).with_name("sources.py")
    spec = importlib.util.spec_from_file_location("assignment_source_adapters", path)
    if spec is None or spec.loader is None:
        raise RetrievalError("assignment source adapters are unavailable", EXIT_RUNTIME)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _snapshot_main(argv) -> int:
    parser = argparse.ArgumentParser(
        description="Normalize Product Hunt and YC snapshots with optional HN enrichment."
    )
    parser.add_argument("--product-hunt", type=Path, required=True)
    parser.add_argument("--yc", type=Path, required=True)
    parser.add_argument("--hacker-news", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        adapters = _load_source_adapters()
        product_hunt = adapters.parse_product_hunt_atom(
            args.product_hunt.read_text(encoding="utf-8")
        )
        yc = adapters.normalize_yc_snapshot(
            json.loads(args.yc.read_text(encoding="utf-8"))
        )
        candidates, excluded = adapters.normalize_candidates(product_hunt + yc)
        if args.hacker_news is not None:
            items = json.loads(args.hacker_news.read_text(encoding="utf-8"))
            candidates = adapters.enrich_with_hacker_news(candidates, items)
        payload = {
            "provider": "official_snapshots",
            "actual_count": len(candidates),
            "candidates": candidates,
            "excluded": excluded,
        }
    except (OSError, json.JSONDecodeError, SyntaxError, RetrievalError) as error:
        print(
            json.dumps(
                {"status": "failed", "exit_code": EXIT_INPUT, "error": str(error)},
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return EXIT_INPUT
    try:
        atomic_write_json(args.output, payload)
    except (OSError, TypeError, ValueError) as error:
        print(
            json.dumps(
                {"status": "failed", "exit_code": EXIT_WRITE, "error": str(error)},
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return EXIT_WRITE
    print(
        json.dumps(
            {
                "status": "ok",
                "provider": payload["provider"],
                "output": str(args.output),
                "exit_code": 0,
                "result_count": payload["actual_count"],
            },
            separators=(",", ":"),
        )
    )
    return 0


def main(argv=None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments[:1] == ["snapshots"]:
        return _snapshot_main(arguments[1:])
    return _legacy_main(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
