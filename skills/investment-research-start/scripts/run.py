"""Manage, atomically promote, and validate investment-research runs."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


EXIT_INPUT = 2
EXIT_RUNTIME = 3
EXIT_AUTH = 4
EXIT_PROVIDER = 5
EXIT_WRITE = 6
EXIT_VALIDATION = 7

STATUSES = {"pending", "running", "completed", "partial", "failed", "skipped"}
STAGES = {"sourcing", "research", "analysis", "memo", "validation"}
CATEGORIES = ("team", "product", "market", "traction", "competitors", "freshness")
CLAIM_TYPES = {"verified_fact", "company_claim", "secondary_report", "inference", "unknown"}
SOURCE_QUALITIES = {"first_party", "primary_record", "credible_secondary", "unknown"}
PROVIDERS = {"exa", "web", "source_snapshots"}
CONFIDENCES = {"high", "medium", "low"}
SCORE_LABELS = (
    "Team",
    "Product differentiation",
    "Market",
    "Traction",
    "Thesis alignment",
)
ORIGIN_HOSTS = {
    "product_hunt": {"producthunt.com", "www.producthunt.com"},
    "yc": {"ycombinator.com", "www.ycombinator.com"},
}
SCORE_COVERAGE = {
    "Team": "team",
    "Product differentiation": "product",
    "Market": "market",
    "Traction": "traction",
}
COMPANY_CLAIM_CAPPED_CATEGORIES = {"Team", "Market", "Traction"}


def _load_assignment_v2_module():
    module_path = Path(__file__).with_name("assignment_v2.py")
    spec = importlib.util.spec_from_file_location("investment_assignment_v2", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load assignment-v2 lifecycle module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ASSIGNMENT_V2 = _load_assignment_v2_module()


class ArtifactWriteError(OSError):
    """Raised when an artifact cannot be serialized or written atomically."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_api_key(cwd: str | Path | None = None) -> tuple[str | None, str]:
    value = os.environ.get("EXA_API_KEY")
    if value:
        return value, "environment"
    env_path = _find_env_local(Path(cwd or Path.cwd()))
    if env_path is None:
        env_path = _find_env_local(Path(__file__).resolve().parent)
    if env_path is None:
        return None, "missing"
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
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


def probe_network() -> str:
    request = urllib.request.Request("https://www.producthunt.com/feed", method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=4):
            return "reachable"
    except urllib.error.HTTPError:
        return "reachable"
    except (OSError, urllib.error.URLError):
        return "unreachable"


def preflight(
    *,
    cwd: str | Path | None = None,
    sdk_available: bool | None = None,
    network_status: str | None = None,
) -> dict:
    key, key_source = load_api_key(cwd)
    runtime_usable = bool(sys.executable and sys.version_info >= (3, 10))
    if sdk_available is None:
        sdk_available = importlib.util.find_spec("exa_py") is not None
    if network_status is None:
        network_status = "not_checked"

    failures = []
    if not runtime_usable:
        failures.append(
            {
                "class": "runtime_unavailable",
                "remediation": "Use a working Python 3.10+ interpreter; do not rely on a broken alias.",
            }
        )
    if network_status == "unreachable":
        failures.append(
            {
                "class": "network_unavailable",
                "remediation": "Retry the Codex source pipeline where Product Hunt and YC snapshot access is allowed, or provide local snapshots.",
            }
        )

    exa_ready = bool(
        runtime_usable and key and sdk_available and network_status != "unreachable"
    )
    snapshot_pipeline_ready = runtime_usable
    failure_class = failures[0]["class"] if failures else None
    if network_status == "unreachable":
        failure_class = "network_unavailable"
    return {
        "status": "ready" if snapshot_pipeline_ready else "blocked",
        "runtime": {
            "usable": runtime_usable,
            "executable": sys.executable,
            "version": list(sys.version_info[:3]),
        },
        "api_key_present": bool(key),
        "api_key_source": key_source,
        "exa_sdk_available": bool(sdk_available),
        "network_status": network_status,
        "exa_ready": exa_ready,
        "snapshot_pipeline_ready": snapshot_pipeline_ready,
        "recommended_provider": (
            "source_snapshots" if snapshot_pipeline_ready else "none"
        ),
        "failure_class": failure_class,
        "failures": failures,
    }


def canonicalize_url(url: str | None) -> str | None:
    if not isinstance(url, str) or not url.strip() or re.search(r"\s", url):
        return None
    text = url.strip()
    parsed = urlsplit(text)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return None
    if parsed.username is not None or parsed.password is not None:
        return None
    scheme = parsed.scheme.lower()
    host = parsed.hostname.lower()
    try:
        port = parsed.port
    except ValueError:
        return None
    netloc = f"[{host}]" if ":" in host else host
    if port and not ((scheme == "https" and port == 443) or (scheme == "http" and port == 80)):
        netloc = f"{host}:{port}"
    path = parsed.path.rstrip("/")
    return urlunsplit((scheme, netloc, path, parsed.query, ""))


def _provenance_url(value: object) -> str | None:
    canonical = canonicalize_url(value if isinstance(value, str) else None)
    if canonical is None:
        return None
    parsed = urlsplit(canonical)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


def _url_host(value: object) -> str | None:
    canonical = canonicalize_url(value)
    if not canonical:
        return None
    parsed = urlsplit(canonical)
    return parsed.hostname.lower() if parsed.hostname else None


def _canonical_domain(value: object) -> str | None:
    host = _url_host(value)
    return host.removeprefix("www.") if host else None


def _host_matches_candidate(value: object, website: object) -> bool:
    source_host = _url_host(value)
    website_host = _url_host(website)
    if source_host is None or website_host is None:
        return False
    source_host = source_host.removeprefix("www.")
    website_host = website_host.removeprefix("www.")
    return source_host == website_host or source_host.endswith(f".{website_host}")


def _normalized_company_name(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def _is_official_hn_item(value: object) -> bool:
    canonical = canonicalize_url(value)
    if not canonical:
        return False
    parsed = urlsplit(canonical)
    query = parsed.query.split("&") if parsed.query else []
    return (
        parsed.scheme == "https"
        and parsed.hostname == "news.ycombinator.com"
        and parsed.path == "/item"
        and len(query) == 1
        and re.fullmatch(r"id=\d+", query[0]) is not None
    )


def _origin_error(origin: object) -> str | None:
    if not isinstance(origin, dict):
        return "must be an object"
    source = origin.get("source")
    if source not in ORIGIN_HOSTS:
        return "must identify Product Hunt or YC"
    canonical = canonicalize_url(origin.get("canonical_url"))
    parsed = urlsplit(canonical or "")
    if parsed.scheme != "https" or parsed.hostname not in ORIGIN_HOSTS[source]:
        return f"{source} URL must use its enforced source domain"
    record_path = {
        "product_hunt": r"/posts/[A-Za-z0-9][A-Za-z0-9._~-]*",
        "yc": r"/companies/[A-Za-z0-9][A-Za-z0-9._~-]*",
    }[source]
    if re.fullmatch(record_path, parsed.path.rstrip("/")) is None:
        return f"must use a record-specific {record_path} URL"
    source_id = origin.get("source_id")
    if not isinstance(source_id, str) or not source_id.strip():
        return "requires a nonempty string source_id"
    publication = origin.get("publication_or_batch_date")
    if not isinstance(publication, str) or not publication.strip():
        return "requires a nonempty string publication_or_batch_date"
    return None


def _allowed_signal_source(value: object, origins: list[dict], website: object) -> bool:
    canonical = canonicalize_url(value)
    if not canonical:
        return False
    if _is_official_hn_item(canonical):
        return True
    if _host_matches_candidate(canonical, website):
        return True
    return _provenance_url(canonical) in {
        _provenance_url(origin.get("canonical_url"))
        for origin in origins
        if isinstance(origin, dict) and _origin_error(origin) is None
    }


def _allowed_claim_source(value: object, candidate: dict) -> bool:
    canonical = canonicalize_url(value)
    if not canonical:
        return False
    host = _url_host(canonical)
    if host in ORIGIN_HOSTS["product_hunt"] | ORIGIN_HOSTS["yc"]:
        return _provenance_url(canonical) in {
            _provenance_url(origin.get("canonical_url"))
            for origin in candidate.get("origins", [])
            if isinstance(origin, dict) and _origin_error(origin) is None
        }
    if _is_official_hn_item(canonical):
        return True
    return _host_matches_candidate(canonical, candidate.get("website"))


def _is_company_originated(value: object, website: object) -> bool:
    return canonicalize_url(value) is not None and _host_matches_candidate(value, website)


def _validate_origin_list(
    origins: object,
    errors: list[str],
    label: str,
    retrieval_results: object = None,
) -> list[dict]:
    if not isinstance(origins, list) or not origins:
        errors.append(f"{label} requires at least one Product Hunt or YC origin")
        return []
    valid: list[dict] = []
    seen = set()
    for index, origin in enumerate(origins):
        problem = _origin_error(origin)
        if problem:
            errors.append(f"{label} origin {index} {problem}")
            continue
        key = (
            origin["source"],
            canonicalize_url(origin["canonical_url"]),
            str(origin["source_id"]),
        )
        if key in seen:
            errors.append(f"{label} has duplicate origin provenance at index {index}")
            continue
        seen.add(key)
        valid.append(origin)
        if retrieval_results is not None:
            results = retrieval_results if isinstance(retrieval_results, list) else []
            matches = [
                result for result in results
                if isinstance(result, dict)
                and _provenance_url(result.get("url")) == _provenance_url(origin["canonical_url"])
            ]
            if not matches:
                errors.append(
                    f"{label} origin {index} is absent from sourcing provenance"
                )
                continue
            source_matches = [
                result for result in matches
                if result.get("source") in {None, origin["source"]}
            ]
            if not source_matches:
                errors.append(
                    f"{label} origin {index} provider/source does not match sourcing provenance"
                )
                continue
            if not any(
                result.get("source_id") in {None, origin["source_id"]}
                for result in source_matches
            ):
                errors.append(
                    f"{label} origin {index} source_id does not match sourcing provenance"
                )
    return valid


def _validate_assignment_candidate(
    candidate: object,
    index: int,
    errors: list[str],
    retrieval_results: object = None,
) -> dict | None:
    if not isinstance(candidate, dict):
        errors.append(f"candidate[{index}] must be an object")
        return None
    name = str(candidate.get("name", "")).strip() or f"candidate[{index}]"
    label = f"candidate {name}"
    for field in ("name", "slug", "website", "one_line_description"):
        if not str(candidate.get(field, "")).strip():
            errors.append(f"{label} requires {field}")
    slug = candidate.get("slug")
    if not isinstance(slug, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        errors.append(f"{label} has invalid slug: {slug}")
    website = canonicalize_url(candidate.get("website"))
    if not website:
        errors.append(f"{label} requires an absolute HTTP(S) website URL with a hostname")
    origins = _validate_origin_list(
        candidate.get("origins"), errors, label, retrieval_results
    )
    if "team_signal" not in candidate:
        errors.append(f"{label} requires nullable team_signal")
    team_signal = candidate.get("team_signal")
    if team_signal is not None:
        if not isinstance(team_signal, dict) or not _allowed_signal_source(
            team_signal.get("source_url") if isinstance(team_signal, dict) else None,
            origins,
            website,
        ):
            errors.append(f"{label} team_signal requires an allowed source URL")
    signals = candidate.get("freshness_or_traction_signals")
    if not isinstance(signals, list) or not signals:
        errors.append(f"{label} requires at least one freshness_or_traction_signal")
    else:
        for signal_index, signal in enumerate(signals):
            if (
                not isinstance(signal, dict)
                or signal.get("kind") not in {"freshness", "traction"}
                or not _allowed_signal_source(
                    signal.get("source_url") if isinstance(signal, dict) else None,
                    origins,
                    website,
                )
            ):
                errors.append(
                    f"{label} signal {signal_index} requires freshness/traction and an allowed source URL"
                )
    reasons = candidate.get("thesis_fit_reasons")
    if not isinstance(reasons, list) or not reasons or not all(
        isinstance(reason, str) and reason.strip() for reason in reasons
    ):
        errors.append(f"{label} requires nonempty thesis_fit_reasons")
    rank = candidate.get("rank")
    if isinstance(rank, bool) or not isinstance(rank, int) or rank != index + 1:
        errors.append(f"{label} rank must be deterministic and equal {index + 1}")
    return candidate


def _validate_assignment_sourcing(
    sourcing: object,
    errors: list[str],
    retrieval: object = None,
) -> tuple[list[dict], list[dict]]:
    if not isinstance(sourcing, dict):
        errors.append("candidates.json must be an object")
        return [], []
    candidates_value = sourcing.get("candidates")
    excluded_value = sourcing.get("excluded")
    if not isinstance(candidates_value, list) or not isinstance(excluded_value, list):
        errors.append("candidates and excluded must be arrays")
        return [], []
    candidates: list[dict] = []
    seen_names: dict[str, str] = {}
    seen_domains: dict[str, str] = {}
    retrieval_results = retrieval.get("results") if isinstance(retrieval, dict) else None
    for index, value in enumerate(candidates_value):
        candidate = _validate_assignment_candidate(
            value, index, errors, retrieval_results
        )
        if candidate is None:
            continue
        candidates.append(candidate)
        name = str(candidate.get("name", "")).strip()
        normalized_name = _normalized_company_name(name)
        domain = _canonical_domain(candidate.get("website"))
        if normalized_name in seen_names:
            errors.append(f"duplicate candidate name: {name} matches {seen_names[normalized_name]}")
        else:
            seen_names[normalized_name] = name
        if domain in seen_domains:
            errors.append(f"duplicate candidate domain: {name} matches {seen_domains[domain]} ({domain})")
        elif domain:
            seen_domains[domain] = name
    excluded: list[dict] = []
    for index, value in enumerate(excluded_value):
        label = f"exclusion[{index}]"
        if not isinstance(value, dict):
            errors.append(f"{label} must be an object")
            continue
        name = str(value.get("name", "")).strip()
        if not name or value.get("candidate_type") != "excluded" or not str(value.get("reason", "")).strip():
            errors.append(f"{label} requires name, candidate_type excluded, and reason")
        _validate_origin_list(
            value.get("origins"),
            errors,
            f"exclusion {name or index}",
            retrieval_results,
        )
        excluded.append(value)
    return candidates, excluded


def _candidate_by_slug(run_dir: Path, slug: str, errors: list[str]) -> dict | None:
    sourcing = _add_json_error(
        run_dir / "sourcing" / "candidates.json", errors, "candidates"
    )
    if not isinstance(sourcing, dict) or not isinstance(sourcing.get("candidates"), list):
        errors.append(f"unable to resolve retained candidate for company {slug}")
        return None
    matches = [
        candidate
        for candidate in sourcing["candidates"]
        if isinstance(candidate, dict) and candidate.get("slug") == slug
    ]
    if len(matches) != 1:
        errors.append(f"company {slug} must match exactly one retained candidate")
        return None
    return matches[0]


def _validate_evidence_identity_and_sources(
    evidence: object,
    candidate: dict,
    errors: list[str],
) -> dict[str, dict]:
    name = str(candidate.get("name") or candidate.get("slug") or "unknown")
    if not isinstance(evidence, dict):
        errors.append(f"evidence for {name} must be an object")
        return {}
    company = evidence.get("company")
    expected_identity = (
        str(candidate.get("name", "")).strip(),
        str(candidate.get("slug", "")).strip(),
        canonicalize_url(candidate.get("website")),
    )
    actual_identity = (
        str(company.get("name", "")).strip() if isinstance(company, dict) else "",
        str(company.get("slug", "")).strip() if isinstance(company, dict) else "",
        canonicalize_url(company.get("website")) if isinstance(company, dict) else None,
    )
    if actual_identity != expected_identity:
        errors.append(f"evidence company identity mismatch for {name}")
    claims = evidence.get("claims")
    if not isinstance(claims, list):
        return {}
    claim_ids: dict[str, dict] = {}
    for index, claim in enumerate(claims):
        if not isinstance(claim, dict):
            continue
        claim_id = claim.get("id")
        if isinstance(claim_id, str) and claim_id.strip() and claim_id not in claim_ids:
            claim_ids[claim_id] = claim
        source_url = claim.get("source_url")
        if claim.get("claim_type") != "unknown" and not _allowed_claim_source(
            source_url, candidate
        ):
            if _url_host(source_url) in ORIGIN_HOSTS["product_hunt"] | ORIGIN_HOSTS["yc"]:
                errors.append(
                    f"claim source does not match a recorded origin for {name} at claim "
                    f"{claim_id or index}: {source_url}"
                )
            else:
                errors.append(
                    f"unsupported claim source for {name} at claim {claim_id or index}: {source_url}"
                )
        if (
            claim.get("claim_type") == "company_claim"
            and not _is_company_originated(source_url, candidate.get("website"))
        ):
            errors.append(
                f"company claim must use the official company website for {name}: {claim_id or index}"
            )
    return claim_ids


def _validate_json_text(text: str):
    return json.loads(text)


def _validate_text(text: str):
    if not text.strip():
        raise ValueError("text artifact must not be empty")
    return text


def atomic_write_text(path: str | Path, text: str) -> Path:
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
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except OSError as error:
        raise ArtifactWriteError(str(error)) from error
    finally:
        if temporary and temporary.exists():
            temporary.unlink()
    return destination


def atomic_write_json(path: str | Path, value) -> Path:
    try:
        text = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    except (TypeError, ValueError) as error:
        raise ArtifactWriteError(str(error)) from error
    return atomic_write_text(path, text)


def atomic_promote(source: str | Path, destination: str | Path, *, kind: str) -> Path:
    source_path = Path(source).resolve()
    destination_path = Path(destination).resolve()
    if source_path.parent != destination_path.parent:
        raise ValueError("temporary source must be a sibling of the destination")
    text = source_path.read_text(encoding="utf-8")
    if kind == "json":
        _validate_json_text(text)
    elif kind == "text":
        _validate_text(text)
    else:
        raise ValueError("kind must be json or text")
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    with source_path.open("r+b") as handle:
        os.fsync(handle.fileno())
    os.replace(source_path, destination_path)
    return destination_path


def read_json(path: str | Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def normalize_input(value: dict) -> dict:
    return ASSIGNMENT_V2.normalize_input(value)


def _fingerprint(input_data: dict, thesis: str) -> str:
    return ASSIGNMENT_V2.input_fingerprint(input_data, thesis)


def _stage_record() -> dict:
    return {
        "status": "pending",
        "attempt_count": 0,
        "provider": None,
        "exit_code": None,
        "error": None,
        "artifacts": [],
        "completed_at": None,
    }


def _load_assignment_sources(
    input_path: str | Path,
    thesis_path: str | Path,
    rubric_path: str | Path | None,
) -> tuple[dict, str, dict]:
    if rubric_path is None:
        raise ValueError("rubric.json is required to initialize an assignment-v2 run")
    input_data = normalize_input(read_json(input_path))
    thesis = Path(thesis_path).read_text(encoding="utf-8")
    if not thesis.strip():
        raise ValueError("thesis.md must not be empty")
    rubric = read_json(rubric_path)
    ASSIGNMENT_V2.validate_rubric(rubric, thesis)
    return input_data, thesis, rubric


def _stored_v2_assignment(
    run_dir: Path,
    manifest: dict,
    *,
    require_active: bool = False,
    validate_links: bool = True,
) -> tuple[dict, str, dict, str]:
    errors = ASSIGNMENT_V2.validate_stored_assignment(
        run_dir, manifest, validate_links=validate_links
    )
    if errors:
        raise ValueError("; ".join(errors))
    if require_active and manifest.get("superseded_by"):
        raise ValueError("existing run has been superseded and cannot continue")
    try:
        input_data = normalize_input(read_json(run_dir / "input.json"))
        thesis = (run_dir / "thesis.md").read_text(encoding="utf-8")
        if not thesis.strip():
            raise ValueError("thesis.md must not be empty")
        rubric = read_json(run_dir / "rubric.json")
        ASSIGNMENT_V2.validate_rubric(rubric, thesis)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"stored run assignment is invalid: {error}") from error
    fingerprint = ASSIGNMENT_V2.assignment_fingerprint(input_data, thesis, rubric)
    return input_data, thesis, rubric, fingerprint


def _initialization_marker(
    run_dir: Path,
    fingerprint: str,
    rubric_fingerprint: str,
    assignment_fingerprint: str,
    supersedes_run_id: str | None,
    supersedes_run_path: str | None,
) -> dict:
    return {
        "version": 2,
        "run_id": run_dir.name,
        "input_fingerprint": fingerprint,
        "rubric_fingerprint": rubric_fingerprint,
        "assignment_fingerprint": assignment_fingerprint,
        "supersedes_run_id": supersedes_run_id,
        "supersedes_run_path": supersedes_run_path,
    }


def _validate_initialization_destination(run_dir: Path, expected_marker: dict) -> Path:
    marker_path = run_dir / ASSIGNMENT_V2.INITIALIZATION_MARKER
    if not run_dir.exists() or not any(run_dir.iterdir()):
        run_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(marker_path, expected_marker)
        return marker_path
    if not marker_path.is_file():
        raise ValueError("run directory is not empty and has no initialization marker")
    try:
        marker = read_json(marker_path)
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"initialization marker is invalid: {error}") from error
    if marker != expected_marker:
        raise ValueError("initialization marker does not match the requested assignment")
    allowed = {
        ASSIGNMENT_V2.INITIALIZATION_MARKER,
        "input.json",
        "thesis.md",
        "rubric.json",
        "sourcing",
        "companies",
    }
    unexpected = sorted(path.name for path in run_dir.iterdir() if path.name not in allowed)
    if unexpected:
        raise ValueError(
            "initialization directory contains unrelated files: " + ", ".join(unexpected)
        )
    for directory_name in ("sourcing", "companies"):
        directory = run_dir / directory_name
        if directory.exists() and (not directory.is_dir() or any(directory.iterdir())):
            raise ValueError(
                f"initialization directory contains unrelated {directory_name} artifacts"
            )
    return marker_path


def initialize_run(
    run_dir: str | Path,
    input_path: str | Path,
    thesis_path: str | Path,
    rubric_path: str | Path | None = None,
    *,
    _supersedes_run_id: str | None = None,
    _supersedes_run_path: str | None = None,
) -> dict:
    if (_supersedes_run_id is None) != (_supersedes_run_path is None):
        raise ValueError("superseding initialization requires both run id and path")
    run_dir = Path(run_dir)
    input_data, thesis, rubric = _load_assignment_sources(
        input_path, thesis_path, rubric_path
    )
    fingerprint = _fingerprint(input_data, thesis)
    rubric_fingerprint = ASSIGNMENT_V2.rubric_fingerprint(rubric)
    assignment_fingerprint = ASSIGNMENT_V2.assignment_fingerprint(
        input_data, thesis, rubric
    )
    manifest_path = run_dir / "manifest.json"
    expected_marker = _initialization_marker(
        run_dir,
        fingerprint,
        rubric_fingerprint,
        assignment_fingerprint,
        _supersedes_run_id,
        _supersedes_run_path,
    )
    marker_path = run_dir / ASSIGNMENT_V2.INITIALIZATION_MARKER
    if manifest_path.exists():
        if marker_path.exists():
            try:
                marker = read_json(marker_path)
            except (OSError, json.JSONDecodeError) as error:
                raise ValueError(f"initialization marker is invalid: {error}") from error
            if marker != expected_marker:
                raise ValueError("initialization marker does not match the durable manifest")
        manifest = read_json(manifest_path)
        stored_input, stored_thesis, _, stored_assignment_fingerprint = (
            _stored_v2_assignment(run_dir, manifest, require_active=True)
        )
        if manifest.get("input_fingerprint") != _fingerprint(stored_input, stored_thesis):
            raise ValueError("stored run fingerprint does not match input.json and thesis.md")
        if stored_assignment_fingerprint != assignment_fingerprint:
            raise ValueError(
                "existing run assignment does not match; create a linked run with supersede"
            )
        if manifest.get("validation", {}).get("status") == "completed":
            raise ValueError("existing run is already completed")
        if marker_path.exists():
            marker_path.unlink()
        return {"resumed": True, "manifest": manifest}

    marker_path = _validate_initialization_destination(run_dir, expected_marker)
    (run_dir / "sourcing").mkdir(exist_ok=True)
    (run_dir / "companies").mkdir(exist_ok=True)
    now = utc_now()
    manifest = {
        "version": 2,
        "run_id": run_dir.name,
        "created_at": now,
        "updated_at": now,
        "input_fingerprint": fingerprint,
        "rubric_fingerprint": rubric_fingerprint,
        "assignment_fingerprint": assignment_fingerprint,
        "supersedes_run_id": _supersedes_run_id,
        "supersedes_run_path": _supersedes_run_path,
        "superseded_by": None,
        "stages": {"sourcing": _stage_record()},
        "companies": {},
        "validation": _stage_record(),
    }
    atomic_write_json(run_dir / "input.json", input_data)
    atomic_write_text(run_dir / "thesis.md", thesis)
    atomic_write_json(run_dir / "rubric.json", rubric)
    atomic_write_json(manifest_path, manifest)
    marker_path.unlink()
    return {"resumed": False, "manifest": manifest}


def supersede_run(
    supersedes_run_dir: str | Path,
    run_dir: str | Path,
    input_path: str | Path,
    thesis_path: str | Path,
    rubric_path: str | Path,
) -> dict:
    """Create a distinct assignment-v2 run and link both manifests safely."""
    old_dir = Path(supersedes_run_dir).resolve()
    new_dir = Path(run_dir).resolve()
    if old_dir == new_dir or old_dir in new_dir.parents:
        raise ValueError("superseding run must use a separate directory outside the old run")
    old_manifest_path = old_dir / "manifest.json"
    old_manifest = read_json(old_manifest_path)
    _, _, _, old_fingerprint = _stored_v2_assignment(old_dir, old_manifest)
    input_data, thesis, rubric = _load_assignment_sources(
        input_path, thesis_path, rubric_path
    )
    new_fingerprint = ASSIGNMENT_V2.assignment_fingerprint(input_data, thesis, rubric)
    if new_fingerprint == old_fingerprint:
        raise ValueError("superseding run must change input, thesis, or rubric")
    expected_backlink = {
        "run_id": new_dir.name,
        "path": str(new_dir),
        "assignment_fingerprint": new_fingerprint,
    }
    old_link = old_manifest.get("superseded_by")
    if old_link is not None and any(
        old_link.get(field) != value for field, value in expected_backlink.items()
    ):
        raise ValueError("existing run has a conflicting superseded_by link")

    new_manifest_path = new_dir / "manifest.json"
    if new_manifest_path.is_file():
        marker_path = new_dir / ASSIGNMENT_V2.INITIALIZATION_MARKER
        if marker_path.exists():
            expected_marker = _initialization_marker(
                new_dir,
                _fingerprint(input_data, thesis),
                ASSIGNMENT_V2.rubric_fingerprint(rubric),
                new_fingerprint,
                old_manifest["run_id"],
                str(old_dir),
            )
            try:
                marker = read_json(marker_path)
            except (OSError, json.JSONDecodeError) as error:
                raise ValueError(f"initialization marker is invalid: {error}") from error
            if marker != expected_marker:
                raise ValueError("initialization marker conflicts with destination manifest")
        new_manifest = read_json(new_manifest_path)
        _, _, _, stored_new_fingerprint = _stored_v2_assignment(
            new_dir, new_manifest, require_active=True, validate_links=False
        )
        if (
            stored_new_fingerprint != new_fingerprint
            or new_manifest.get("run_id") != new_dir.name
            or new_manifest.get("supersedes_run_id") != old_manifest.get("run_id")
            or new_manifest.get("supersedes_run_path") != str(old_dir)
        ):
            raise ValueError("existing destination has conflicting superseding linkage")
        if marker_path.exists():
            marker_path.unlink()
        result = {"resumed": True, "manifest": new_manifest}
    else:
        if old_link is not None:
            raise ValueError("superseded_by link points to a missing destination run")
        result = initialize_run(
            new_dir,
            input_path,
            thesis_path,
            rubric_path,
            _supersedes_run_id=old_manifest["run_id"],
            _supersedes_run_path=str(old_dir),
        )
        new_manifest = result["manifest"]

    if old_link is None:
        now = utc_now()
        linked_old_manifest = dict(old_manifest)
        linked_old_manifest["superseded_by"] = {**expected_backlink, "linked_at": now}
        linked_old_manifest["updated_at"] = now
        atomic_write_json(old_manifest_path, linked_old_manifest)
    return result


def _safe_artifact(run_dir: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute():
        raise ValueError(f"artifact path must be relative: {relative}")
    resolved = (run_dir / path).resolve()
    try:
        resolved.relative_to(run_dir.resolve())
    except ValueError as error:
        raise ValueError(f"artifact path escapes run directory: {relative}") from error
    return resolved


def _validate_artifact(path: Path):
    if not path.is_file():
        raise ValueError(f"artifact does not exist: {path}")
    if path.suffix.lower() == ".json":
        read_json(path)
    else:
        _validate_text(path.read_text(encoding="utf-8"))


def _validate_completion_contract(
    run_dir: Path, stage: str, company: str | None, artifacts: list[str]
) -> None:
    required_names = {
        "sourcing": {"retrieval.json", "candidates.json"},
        "research": {"evidence.json"},
        "analysis": {"analysis.md"},
        "memo": {"memo.md"},
        "validation": {"run-summary.md"},
    }
    names = {Path(relative).name for relative in artifacts}
    missing = required_names[stage] - names
    if missing:
        raise ValueError(f"completed {stage} stage requires {', '.join(sorted(missing))}")

    errors: list[str] = []
    if stage == "sourcing":
        retrieval_path = run_dir / "sourcing" / "retrieval.json"
        _validate_retrieval(retrieval_path, errors, "sourcing retrieval")
        retrieval = _add_json_error(retrieval_path, errors, "sourcing retrieval") or {}
        candidates = _add_json_error(
            run_dir / "sourcing" / "candidates.json", errors, "candidates"
        )
        if not isinstance(candidates, dict):
            errors.append("candidates.json must be an object")
        else:
            for field in (
                "provider", "query", "retrieval_path", "requested_count",
                "actual_count", "candidates", "excluded",
            ):
                if field not in candidates:
                    errors.append(f"candidates missing {field}")
            retained = candidates.get("candidates")
            excluded = candidates.get("excluded")
            if not isinstance(retained, list) or not isinstance(excluded, list):
                errors.append("candidates and excluded must be arrays")
            else:
                if candidates.get("actual_count") != len(retained):
                    errors.append("actual_count does not match retained candidate count")
                try:
                    expected_count = normalize_input(read_json(run_dir / "input.json"))[
                        "sourcing"
                    ]["target_count"]
                except (KeyError, OSError, json.JSONDecodeError, TypeError, ValueError) as error:
                    errors.append(f"unable to validate sourcing requested_count: {error}")
                else:
                    if candidates.get("requested_count") != expected_count:
                        errors.append(
                            "sourcing requested_count does not match the assignment target_count"
                        )
                if not 10 <= len(retained) <= 20:
                    errors.append(
                        f"completed sourcing requires 10 through 20 retained candidates; found {len(retained)}"
                    )
                _validate_assignment_sourcing(candidates, errors, retrieval)
            if candidates.get("provider") != retrieval.get("provider"):
                errors.append("sourcing provider does not match retrieval artifact")
            if candidates.get("query") != retrieval.get("query"):
                errors.append("sourcing query does not match retrieval artifact")
            if retrieval.get("status") != "ok":
                errors.append("completed sourcing requires a successful retrieval artifact")
    elif stage == "research":
        if not company:
            errors.append("research completion requires company")
        else:
            evidence = _add_json_error(
                run_dir / "companies" / company / "evidence.json", errors, "evidence"
            )
            if not isinstance(evidence, dict):
                errors.append("evidence.json must be an object")
            else:
                candidate = _candidate_by_slug(run_dir, company, errors)
                if candidate is not None:
                    _validate_evidence_identity_and_sources(evidence, candidate, errors)
                coverage = evidence.get("coverage")
                if not isinstance(coverage, dict) or any(
                    coverage.get(category) not in {"present", "missing"}
                    for category in CATEGORIES
                ):
                    errors.append("evidence coverage must contain only present or missing")
                if not isinstance(evidence.get("claims"), list):
                    errors.append("evidence claims must be an array")
                retrievals = evidence.get("retrievals")
                if not isinstance(retrievals, list) or not 1 <= len(retrievals) <= 2:
                    errors.append("evidence requires an initial retrieval and at most one retry")
                    retrievals = []
                expected_missing = [
                    category for category in CATEGORIES
                    if isinstance(coverage, dict) and coverage.get(category) == "missing"
                ]
                if evidence.get("missing_categories") != expected_missing:
                    errors.append("evidence missing_categories is not normalized")
                if evidence.get("unresolved_gaps") != expected_missing:
                    errors.append("evidence unresolved_gaps is not normalized")
                if len(retrievals) == 2:
                    initial_coverage = evidence.get("initial_coverage")
                    initial_missing = evidence.get("initial_missing_categories")
                    if not isinstance(initial_coverage, dict) or any(
                        initial_coverage.get(category) not in {"present", "missing"}
                        for category in CATEGORIES
                    ):
                        errors.append("retry requires binary initial_coverage")
                    else:
                        derived = [
                            category for category in CATEGORIES
                            if initial_coverage.get(category) == "missing"
                        ]
                        if initial_missing != derived or not set(expected_missing).issubset(derived):
                            errors.append("retry missing categories do not match initial coverage")
                for index, retrieval_record in enumerate(retrievals):
                    expected_name = "retrieval-initial.json" if index == 0 else "retrieval-retry.json"
                    expected_path = run_dir / "companies" / company / expected_name
                    if not isinstance(retrieval_record, dict):
                        errors.append(f"invalid retrieval provenance at index {index}")
                        continue
                    if retrieval_record.get("artifact_path") != f"companies/{company}/{expected_name}":
                        errors.append(f"retrieval path must target the current company at index {index}")
                        continue
                    _validate_retrieval(expected_path, errors, f"retrieval at index {index}", max_results=5)
                    artifact_value = _add_json_error(expected_path, errors, f"retrieval at index {index}") or {}
                    for field in ("provider", "query", "retrieved_at", "status", "exit_code"):
                        if retrieval_record.get(field) != artifact_value.get(field):
                            errors.append(f"retrieval provenance does not match artifact at index {index}: {field}")
                if retrievals and not any(
                    isinstance(record, dict) and record.get("status") == "ok"
                    for record in retrievals
                ):
                    errors.append("completed research requires at least one successful retrieval")
                claims = evidence.get("claims", [])
                seen_claims = set()
                for claim in claims if isinstance(claims, list) else []:
                    if not isinstance(claim, dict) or not isinstance(claim.get("id"), str):
                        errors.append("invalid claim record")
                        continue
                    if claim["id"] in seen_claims:
                        errors.append(f"duplicate claim id: {claim['id']}")
                    seen_claims.add(claim["id"])
                    if claim.get("area") not in CATEGORIES:
                        errors.append(f"invalid claim area: {claim.get('area')}")
                    if claim.get("claim_type") not in CLAIM_TYPES:
                        errors.append(f"invalid claim type: {claim.get('claim_type')}")
                    if claim.get("source_quality") not in SOURCE_QUALITIES:
                        errors.append("invalid claim source quality")
                    if claim.get("confidence") not in CONFIDENCES:
                        errors.append("invalid claim confidence")
    elif stage == "analysis" and company:
        evidence = _add_json_error(
            run_dir / "companies" / company / "evidence.json", errors, "evidence"
        ) or {}
        candidate = _candidate_by_slug(run_dir, company, errors)
        claim_ids = (
            _validate_evidence_identity_and_sources(evidence, candidate, errors)
            if candidate is not None else {}
        )
        used_claim_ids: set[str] = set()
        score, call = _parse_analysis(
            run_dir / "companies" / company / "analysis.md", errors, company, claim_ids,
            evidence.get("coverage", {}),
            _rubric_weights(run_dir, errors),
            used_claim_ids,
            candidate.get("website") if candidate is not None else None,
        )
        for claim_id in sorted(set(claim_ids) - used_claim_ids):
            errors.append(f"unused claim for {company}: {claim_id}")
        try:
            thresholds = read_json(run_dir / "input.json")["recommendation_thresholds"]
            if score is not None and call and call.lower() != _expected_call(score, thresholds).lower():
                errors.append("analysis recommendation does not match configured thresholds")
        except (KeyError, OSError, json.JSONDecodeError, TypeError):
            errors.append("unable to validate analysis recommendation thresholds")
    elif stage == "memo" and company:
        evidence = _add_json_error(
            run_dir / "companies" / company / "evidence.json", errors, "evidence"
        ) or {}
        candidate = _candidate_by_slug(run_dir, company, errors)
        claim_ids = (
            _validate_evidence_identity_and_sources(evidence, candidate, errors)
            if candidate is not None else {}
        )
        used_claim_ids: set[str] = set()
        score, call = _parse_analysis(
            run_dir / "companies" / company / "analysis.md", errors, company, claim_ids,
            evidence.get("coverage", {}),
            _rubric_weights(run_dir, errors),
            used_claim_ids,
            candidate.get("website") if candidate is not None else None,
        )
        for claim_id in sorted(set(claim_ids) - used_claim_ids):
            errors.append(f"unused claim for {company}: {claim_id}")
        memo_score, memo_call = _parse_memo(
            run_dir / "companies" / company / "memo.md", errors, company
        )
        if score != memo_score or (call and memo_call and call.lower() != memo_call.lower()):
            errors.append("memo score and recommendation must match analysis")
    elif stage in {"analysis", "memo"}:
        errors.append(f"{stage} completion requires company")
    elif stage == "validation":
        result = validate_run(run_dir)
        errors.extend(result["errors"])
    if errors:
        raise ValueError("; ".join(errors))


def update_stage(
    run_dir: str | Path,
    stage: str,
    status: str,
    *,
    company: str | None = None,
    provider: str | None = None,
    exit_code: int | None = None,
    error: str | None = None,
    artifacts: list[str] | None = None,
) -> dict:
    if stage not in STAGES:
        raise ValueError(f"unknown stage: {stage}")
    if status not in STATUSES:
        raise ValueError(f"unknown status: {status}")
    if company and not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", company):
        raise ValueError(f"invalid company slug: {company}")
    run_dir = Path(run_dir)
    manifest_path = run_dir / "manifest.json"
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict) or manifest.get("version") != 2:
        raise ValueError("manifest.version must be 2 for stage updates")
    _stored_v2_assignment(run_dir, manifest, require_active=True)
    if company:
        if stage in {"sourcing", "validation"}:
            raise ValueError(f"{stage} is a run-level stage")
        company_record = manifest.setdefault("companies", {}).setdefault(company, {})
        record = company_record.setdefault(stage, _stage_record())
    elif stage == "validation":
        record = manifest.setdefault("validation", _stage_record())
    else:
        record = manifest.setdefault("stages", {}).setdefault(stage, _stage_record())

    artifact_list = list(artifacts or [])
    if stage == "research" and status == "running" and int(record.get("attempt_count", 0)) >= 2:
        raise ValueError("research permits one initial attempt and one retry")
    if status == "completed":
        if company:
            predecessor = {"research": "sourcing", "analysis": "research", "memo": "analysis"}.get(stage)
            if predecessor == "sourcing":
                predecessor_status = manifest.get("stages", {}).get("sourcing", {}).get("status")
            elif predecessor:
                predecessor_status = manifest.get("companies", {}).get(company, {}).get(
                    predecessor, {}
                ).get("status")
            else:
                predecessor_status = "completed"
            if predecessor and predecessor_status != "completed":
                raise ValueError(
                    f"company {company} {stage} cannot complete until {predecessor} is completed"
                )
        if not artifact_list:
            raise ValueError("completed stage requires at least one artifact")
        for relative in artifact_list:
            _validate_artifact(_safe_artifact(run_dir, relative))
        _validate_completion_contract(run_dir, stage, company, artifact_list)
        if stage in {"sourcing", "research"} and (provider is None or exit_code is None):
            raise ValueError(f"completed {stage} stage requires provider and exit code")
    previous = record.get("status", "pending")
    if status == "running" or (previous == "pending" and status in {"completed", "partial", "failed"}):
        record["attempt_count"] = int(record.get("attempt_count", 0)) + 1
    record.update(
        {
            "status": status,
            "provider": provider,
            "exit_code": exit_code,
            "error": str(error)[:2000] if error else None,
            "artifacts": artifact_list,
            "completed_at": utc_now() if status in {"completed", "skipped"} else None,
        }
    )
    manifest["updated_at"] = utc_now()
    atomic_write_json(manifest_path, manifest)
    return manifest


def _add_json_error(path: Path, errors: list[str], label: str):
    try:
        return read_json(path)
    except FileNotFoundError:
        errors.append(f"missing {label}: {path}")
    except (OSError, json.JSONDecodeError) as error:
        errors.append(f"invalid {label}: {path} ({error})")
    return None


def _validate_retrieval(
    path: Path, errors: list[str], label: str, *, max_results: int = 20
) -> set[str]:
    value = _add_json_error(path, errors, label)
    urls = set()
    if not isinstance(value, dict):
        return urls
    for field in ("query", "provider", "retrieved_at", "status", "exit_code", "results"):
        if field not in value:
            errors.append(f"{label} missing {field}")
    if value.get("provider") not in PROVIDERS:
        errors.append(f"{label} has invalid provider: {value.get('provider')}")
    if value.get("status") not in {"ok", "failed", "partial"}:
        errors.append(f"{label} has invalid status: {value.get('status')}")
    if not isinstance(value.get("exit_code"), int) or isinstance(value.get("exit_code"), bool):
        errors.append(f"{label} exit_code must be an integer")
    elif value.get("status") == "ok" and value.get("exit_code") != 0:
        errors.append(f"successful retrieval must have exit code zero in {label}")
    elif value.get("status") == "failed" and value.get("exit_code") == 0:
        errors.append(f"failed retrieval must have a nonzero exit code in {label}")
    if len(str(value.get("stderr", ""))) > 2000:
        errors.append(f"{label} stderr exceeds 2000 characters")
    if not isinstance(value.get("results"), list):
        errors.append(f"{label} results must be an array")
        return urls
    if len(value["results"]) > max_results:
        errors.append(f"{label} contains more than {max_results} results")
    for result in value["results"]:
        if not isinstance(result, dict):
            errors.append(f"{label} result must be an object")
            continue
        if result.get("url"):
            url = canonicalize_url(result["url"])
            if url is None:
                errors.append(
                    f"{label} result URL must be absolute HTTP(S) with a nonempty hostname"
                )
                continue
            if url in urls:
                errors.append(f"duplicate retrieval URL in {label}: {url}")
            urls.add(url)
        highlights = result.get("highlights", []) if isinstance(result, dict) else []
        if not isinstance(highlights, list):
            errors.append(f"{label} highlights must be an array")
            continue
        if len(highlights) > 1 or any(len(str(item)) > 400 for item in highlights):
            errors.append(f"{label} contains unbounded highlights")
    return urls


def _validate_manifest(run_dir: Path, manifest: dict, errors: list[str]) -> None:
    if not isinstance(manifest, dict):
        errors.append("manifest must be an object")
        return
    records = []
    stages = manifest.get("stages", {})
    if not isinstance(stages, dict):
        errors.append("manifest stages must be an object")
        stages = {}
    records.extend((f"run {stage}", stage, record) for stage, record in stages.items())
    companies = manifest.get("companies", {})
    if not isinstance(companies, dict):
        errors.append("manifest companies must be an object")
        companies = {}
    for slug, company_stages in companies.items():
        if not isinstance(company_stages, dict):
            errors.append(f"manifest company stages must be an object for {slug}")
            continue
        records.extend(
            (f"company {slug} {stage}", stage, record)
            for stage, record in company_stages.items()
        )
    records.append(("validation", "validation", manifest.get("validation", {})))

    for label, stage, record in records:
        if not isinstance(record, dict):
            errors.append(f"manifest record must be an object for {label}")
            continue
        status = record.get("status")
        if status not in STATUSES:
            errors.append(f"manifest status is invalid for {label}: {status}")
        attempts = record.get("attempt_count")
        if not isinstance(attempts, int) or isinstance(attempts, bool) or attempts < 0:
            errors.append(f"manifest attempt_count is invalid for {label}")
        if stage == "research" and isinstance(attempts, int) and attempts > 2:
            errors.append(f"research attempts exceed initial pass plus one retry for {label}")
        if record.get("provider") not in {None, *PROVIDERS}:
            errors.append(f"manifest provider is invalid for {label}")
        exit_code = record.get("exit_code")
        if exit_code is not None and (
            not isinstance(exit_code, int) or isinstance(exit_code, bool)
        ):
            errors.append(f"manifest exit_code is invalid for {label}")
        if len(str(record.get("error") or "")) > 2000:
            errors.append(f"manifest error exceeds 2000 characters for {label}")
        artifacts = record.get("artifacts")
        if not isinstance(artifacts, list):
            errors.append(f"manifest artifacts must be an array for {label}")
            continue
        if status == "completed" and not artifacts:
            errors.append(f"completed manifest stage has no artifacts for {label}")
        for relative in artifacts:
            try:
                _validate_artifact(_safe_artifact(run_dir, relative))
            except (TypeError, ValueError, OSError, json.JSONDecodeError) as error:
                errors.append(f"manifest artifact is invalid for {label}: {error}")


def _rubric_weights(run_dir: Path, errors: list[str]) -> dict[str, int]:
    rubric = _add_json_error(run_dir / "rubric.json", errors, "rubric")
    if not isinstance(rubric, dict):
        return {label: 20 for label in SCORE_LABELS}
    categories = rubric.get("categories")
    if not isinstance(categories, list):
        errors.append("rubric categories must be an array")
        return {label: 20 for label in SCORE_LABELS}
    weights: dict[str, int] = {}
    for index, category in enumerate(categories):
        if not isinstance(category, dict):
            errors.append(f"rubric category {index} must be an object")
            continue
        name, weight = category.get("name"), category.get("weight")
        if name not in SCORE_LABELS or isinstance(weight, bool) or not isinstance(weight, int):
            errors.append(f"invalid rubric category or weight at index {index}")
            continue
        if name in weights:
            errors.append(f"duplicate rubric category: {name}")
        weights[name] = weight
    if tuple(weights) != SCORE_LABELS:
        errors.append("analysis rubric must use the exact five assignment categories in order")
        return {label: 20 for label in SCORE_LABELS}
    if sum(weights.values()) != 100:
        errors.append("analysis rubric weights must total 100")
    return weights


NARRATIVE_REFERENCE = re.compile(
    r"\s*\[refs:\s*([A-Za-z0-9_.-]+(?:\s*,\s*[A-Za-z0-9_.-]+)*)\]\s*$"
)
FACTUAL_NARRATIVE = re.compile(
    r"(?:[$€£₹]|\b\d+(?:\.\d+)?%?\b|\b(?:arr|mrr|revenue|retention|churn|"
    r"customers?|users?|employees?|founded|launched|raised|growth|grew|declined|"
    r"increased|decreased|contracts?|sales|market share)\b)",
    re.IGNORECASE,
)


def _validate_analysis_narrative(
    text: str,
    errors: list[str],
    name: str,
    claim_ids: dict[str, dict],
    used_claim_ids: set[str] | None,
) -> None:
    section = ""
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        stripped = raw_line.strip()
        heading = re.match(r"^#{1,6}\s+(.+?)\s*$", stripped)
        if heading:
            section = heading.group(1).casefold()
            continue
        if not stripped or stripped.startswith("|"):
            continue
        if stripped.strip("*_").casefold() in {"pass", "watch", "take a meeting"}:
            continue
        bullet = re.match(r"^[-*]\s+(.+)$", stripped)
        narrative = bullet.group(1).strip() if bullet else stripped
        reference_match = NARRATIVE_REFERENCE.search(narrative)
        if reference_match:
            if bullet is None:
                errors.append(
                    f"analysis narrative for {name} at line {line_number} must use a structured bullet"
                )
            statement = narrative[: reference_match.start()].strip()
            if not statement:
                errors.append(f"empty narrative statement for {name} at line {line_number}")
            for claim_id in [
                item.strip() for item in reference_match.group(1).split(",")
            ]:
                if claim_id not in claim_ids:
                    errors.append(
                        f"unknown narrative reference for {name} at line {line_number}: {claim_id}"
                    )
                elif used_claim_ids is not None:
                    used_claim_ids.add(claim_id)
            continue
        factual = FACTUAL_NARRATIVE.search(narrative) is not None
        clearly_open_risk = (
            section == "risks and open questions"
            and (
                narrative.endswith("?")
                or re.match(r"^(?:verify|confirm)\b", narrative, re.IGNORECASE)
                or re.search(
                    r"\b(?:risk|unknown|unclear|unverified|could|may|might|whether|"
                    r"needs? (?:confirmation|verification))\b",
                    narrative,
                    re.IGNORECASE,
                )
            )
        )
        if clearly_open_risk:
            continue
        if bullet is None:
            errors.append(
                f"analysis narrative for {name} at line {line_number} must use a structured bullet"
            )
        else:
            errors.append(
                f"{'factual narrative' if factual else 'narrative bullet'} for {name} "
                f"at line {line_number} requires a trailing [refs: claim-id] list"
            )


def _parse_analysis(
    path: Path,
    errors: list[str],
    name: str,
    claim_ids: dict[str, dict],
    coverage: dict | None = None,
    rubric_weights: dict[str, int] | None = None,
    used_claim_ids: set[str] | None = None,
    company_website: str | None = None,
):
    if not path.exists():
        errors.append(f"missing analysis for {name}")
        return None, None
    text = path.read_text(encoding="utf-8")
    if not re.search(r"^## Risks and open questions\s*$", text, re.MULTILINE):
        errors.append(f"analysis for {name} requires exact heading: ## Risks and open questions")
    weights = rubric_weights or {label: 20 for label in SCORE_LABELS}
    scores = []
    for label, weight in weights.items():
        match = re.search(
            rf"^\|\s*{re.escape(label)}\s*\|\s*(\d+)\s*\|\s*([^|]+)\|",
            text,
            re.MULTILINE | re.IGNORECASE,
        )
        if not match:
            errors.append(f"missing score row {label} for {name}")
            continue
        score = int(match.group(1))
        refs = [part.strip() for part in match.group(2).split(",") if part.strip()]
        if not refs:
            errors.append(f"score row requires an evidence reference for {name}: {label}")
        if not 0 <= score <= weight:
            errors.append(f"score out of range for {name}: {label}={score}; weight={weight}")
        if refs and all(ref.lower().startswith("gap:") for ref in refs) and score != 0:
            errors.append(f"gap-only score row must receive zero for {name}: {label}")
        for ref in refs:
            if ref.lower().startswith("claim:"):
                claim_id = ref.split(":", 1)[1]
                if claim_id not in claim_ids:
                    errors.append(f"unknown claim reference for {name}: {ref}")
                elif used_claim_ids is not None:
                    used_claim_ids.add(claim_id)
            elif ref.lower().startswith("gap:"):
                if ref.split(":", 1)[1].lower() not in CATEGORIES:
                    errors.append(f"unknown gap reference for {name}: {ref}")
            else:
                errors.append(f"invalid evidence reference for {name}: {ref}")
        required_area = SCORE_COVERAGE.get(label)
        referenced_areas = {
            claim_ids.get(ref.split(":", 1)[1], {}).get("area")
            for ref in refs if ref.lower().startswith("claim:")
        }
        usable_claims = [
            claim_ids.get(ref.split(":", 1)[1], {})
            for ref in refs if ref.lower().startswith("claim:")
        ]
        category_claims = [
            claim for claim in usable_claims
            if required_area is None or claim.get("area") == required_area
        ]
        if score > 0 and not any(
            claim and claim.get("claim_type") != "unknown" for claim in usable_claims
        ):
            errors.append(f"positive score lacks usable evidence for {name}: {label}")
        if score > 0 and required_area and required_area not in referenced_areas:
            errors.append(f"score row lacks {required_area} evidence for {name}: {label}")
        if (
            score != 0
            and required_area
            and isinstance(coverage, dict)
            and coverage.get(required_area) != "present"
        ):
            errors.append(
                f"missing coverage must score zero for {name}: {label}={score} "
                f"({required_area} coverage is missing)"
            )
        if (
            score > 10
            and label in COMPANY_CLAIM_CAPPED_CATEGORIES
            and category_claims
            and all(
                _is_company_originated(claim.get("source_url"), company_website)
                for claim in category_claims
            )
        ):
            errors.append(
                f"company-claim-only/company-originated {label} score is capped at 10 "
                f"for {name}: {score}"
            )
        scores.append(score)
    _validate_analysis_narrative(text, errors, name, claim_ids, used_claim_ids)
    final_match = re.search(r"\*\*Final score\*\*\s*\|\s*\*\*(\d+)\s*/\s*100\*\*", text, re.I)
    final_score = int(final_match.group(1)) if final_match else None
    if final_score is None:
        errors.append(f"missing final score for {name}")
    elif len(scores) == len(weights) and final_score != sum(scores):
        errors.append(f"score arithmetic mismatch for {name}: {final_score} != {sum(scores)}")
    recommendation = None
    recommendation_match = re.search(
        r"## Recommendation\s*\n\s*(?:\*\*)?(Pass|Watch|Take a meeting)(?:\*\*)?",
        text,
        re.I,
    )
    if recommendation_match:
        recommendation = recommendation_match.group(1)
    else:
        errors.append(f"missing recommendation for {name}")
    return final_score, recommendation


def _parse_memo(path: Path, errors: list[str], name: str):
    if not path.exists():
        errors.append(f"missing memo for {name}")
        return None, None
    text = path.read_text(encoding="utf-8")
    score = re.search(r"## Score\s*\n\s*\*\*(\d+)\s*/\s*100\*\*", text, re.I)
    call = re.search(r"## Recommendation\s*\n\s*\*\*(Pass|Watch|Take a meeting)\*\*", text, re.I)
    if not score:
        errors.append(f"missing memo score for {name}")
    if not call:
        errors.append(f"missing memo recommendation for {name}")
    return int(score.group(1)) if score else None, call.group(1) if call else None


def _expected_call(score: int, thresholds: dict) -> str:
    if score >= thresholds["meeting_min"]:
        return "Take a meeting"
    if score >= thresholds["watch_min"]:
        return "Watch"
    return "Pass"


def _validate_legacy(run_dir: Path) -> dict:
    errors: list[str] = []
    warnings = ["legacy layout detected; validation is read-only"]
    candidates = _add_json_error(run_dir / "sourcing" / "candidates.json", errors, "legacy candidates") or []
    if not isinstance(candidates, list):
        errors.append("legacy candidates must be an array")
        candidates = []
    for evidence_path in (run_dir / "evidence").glob("*/evidence.md"):
        text = evidence_path.read_text(encoding="utf-8")
        seen = set()
        for match in re.finditer(
            r"\b(team|product|market|traction|competitors|freshness)\s*:\s*([a-z_]+)",
            text,
            re.I,
        ):
            category, value = match.groups()
            seen.add(category.lower())
            if value.lower() not in {"present", "missing"}:
                errors.append(
                    f"invalid legacy coverage in {evidence_path}: {category}={value}; expected present or missing"
                )
        for category in CATEGORIES:
            if category not in seen:
                errors.append(f"missing legacy coverage in {evidence_path}: {category}")
    sourcing_path = run_dir / "sourcing" / "sourcing.md"
    sourcing_text = sourcing_path.read_text(encoding="utf-8") if sourcing_path.exists() else ""
    for candidate in candidates:
        if not isinstance(candidate, dict) or not candidate.get("name") or not candidate.get("website"):
            continue
        name = candidate["name"]
        stale_pattern = rf"{re.escape(name)}(?:(?!\n\n).){{0,500}}official(?:(?!\n\n).){{0,200}}not verified"
        if re.search(stale_pattern, sourcing_text, re.I | re.S):
            errors.append(
                f"stale sourcing claim for {name}: official website is present in candidates but sourcing says it was not verified"
            )
    return {
        "valid": not errors,
        "layout": "legacy",
        "run_dir": str(run_dir),
        "errors": errors,
        "warnings": warnings,
    }


def _validate_new(run_dir: Path) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    input_data = _add_json_error(run_dir / "input.json", errors, "input") or {}
    try:
        input_data = normalize_input(input_data)
    except ValueError as error:
        errors.append(f"invalid input: {error}")
    thesis_path = run_dir / "thesis.md"
    thesis_text = thesis_path.read_text(encoding="utf-8") if thesis_path.exists() else ""
    if not thesis_text.strip():
        errors.append("missing or empty thesis.md")
    rubric_weights = _rubric_weights(run_dir, errors)
    manifest = _add_json_error(run_dir / "manifest.json", errors, "manifest") or {}
    _validate_manifest(run_dir, manifest, errors)
    if isinstance(input_data, dict) and thesis_text.strip():
        if manifest.get("input_fingerprint") != _fingerprint(input_data, thesis_text):
            errors.append("manifest input/thesis fingerprint does not match run artifacts")
    sourcing = _add_json_error(run_dir / "sourcing" / "candidates.json", errors, "candidates") or {}
    if not isinstance(sourcing, dict):
        errors.append("candidates.json must be an object")
        sourcing = {}
    sourcing_urls = _validate_retrieval(
        run_dir / "sourcing" / "retrieval.json", errors, "sourcing retrieval"
    )
    try:
        sourcing_retrieval = read_json(run_dir / "sourcing" / "retrieval.json")
    except (OSError, json.JSONDecodeError):
        sourcing_retrieval = {}
    for field in ("provider", "query", "retrieval_path", "requested_count", "actual_count"):
        if field not in sourcing:
            errors.append(f"candidates missing {field}")
    if sourcing.get("provider") not in PROVIDERS:
        errors.append(f"candidates has invalid provider: {sourcing.get('provider')}")
    if sourcing.get("retrieval_path") != "sourcing/retrieval.json":
        errors.append("candidates retrieval_path must be sourcing/retrieval.json")
    if isinstance(sourcing_retrieval, dict):
        if sourcing.get("provider") != sourcing_retrieval.get("provider"):
            errors.append("sourcing provider does not match retrieval artifact")
        if sourcing.get("query") != sourcing_retrieval.get("query"):
            errors.append("sourcing query does not match retrieval artifact")
        if (
            manifest.get("stages", {}).get("sourcing", {}).get("status") == "completed"
            and sourcing_retrieval.get("status") != "ok"
        ):
            errors.append("completed sourcing requires a successful retrieval artifact")
    candidates, excluded = _validate_assignment_sourcing(
        sourcing, errors, sourcing_retrieval
    )
    if sourcing.get("actual_count") != len(candidates):
        errors.append("actual_count does not match retained candidate count")
    expected_requested = input_data.get("sourcing", {}).get("target_count") if isinstance(input_data, dict) else None
    if sourcing.get("requested_count") != expected_requested:
        errors.append("requested_count does not match input sourcing target")
    sourcing_status = manifest.get("stages", {}).get("sourcing", {}).get("status")
    if not 10 <= len(candidates) <= 20:
        if len(candidates) < 10:
            errors.append(
                f"fewer than 10 retained candidates must leave sourcing partial; found {len(candidates)}"
            )
        else:
            errors.append("retained candidate count exceeds 20")
        if sourcing_status == "completed":
            errors.append("completed sourcing requires 10 through 20 retained candidates")
        elif len(candidates) < 10 and sourcing_status != "partial":
            errors.append("sourcing with fewer than 10 candidates must have partial manifest status")
    research_config = input_data.get("research", {}) if isinstance(input_data, dict) else {}
    if research_config != {"full_coverage": True}:
        errors.append(
            "assignment-v2 research must contain only full_coverage=true and no limit"
        )
    seen_names, seen_sites, seen_slugs, seen_priorities = set(), set(), set(), set()
    selected = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            errors.append("candidate must be an object")
            continue
        name = str(candidate.get("name", "")).strip()
        slug = str(candidate.get("slug", "")).strip()
        website = canonicalize_url(candidate.get("website"))
        normalized_name = re.sub(r"[^a-z0-9]", "", name.lower())
        if not name or not slug or not website:
            errors.append("candidate requires name, slug, and website")
            continue
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
            errors.append(f"invalid candidate slug for {name}: {slug}")
            continue
        if normalized_name in seen_names or website in seen_sites or slug in seen_slugs:
            errors.append(f"duplicate candidate: {name} ({website})")
        seen_names.add(normalized_name)
        seen_sites.add(website)
        seen_slugs.add(slug)
        if candidate.get("candidate_type") not in {"priority", "comparable"}:
            errors.append(f"invalid candidate_type for {name}")
        if candidate.get("source_quality") not in SOURCE_QUALITIES:
            errors.append(f"invalid source_quality for {name}")
        if not isinstance(candidate.get("fit_reasons"), list) or not candidate.get("fit_reasons"):
            errors.append(f"missing fit_reasons for {name}")
        priority = candidate.get("research_priority")
        if not isinstance(priority, int) or isinstance(priority, bool) or priority < 1:
            errors.append(f"invalid research_priority for {name}")
        elif priority in seen_priorities:
            errors.append(f"duplicate research_priority for {name}: {priority}")
        else:
            seen_priorities.add(priority)
        source_urls = candidate.get("source_urls")
        if not isinstance(source_urls, list) or not source_urls:
            errors.append(f"missing source_urls for {name}")
        else:
            sourcing_provenance_urls = {
                _provenance_url(url) for url in sourcing_urls if url
            }
            for source_url in source_urls:
                canonical = canonicalize_url(source_url)
                if canonical is None:
                    errors.append(
                        f"candidate source URL must be absolute HTTP(S) with a hostname for {name}: {source_url}"
                    )
                elif _provenance_url(canonical) not in sourcing_provenance_urls:
                    errors.append(f"candidate source URL not present in sourcing retrieval for {name}: {canonical}")
        if not isinstance(candidate.get("selected_for_research"), bool):
            errors.append(f"selected_for_research must be boolean for {name}")
        if candidate.get("selected_for_research"):
            selected.append(candidate)
        else:
            errors.append(f"full coverage requires retained candidate selection: {name}")
    for exclusion in excluded:
        if (
            not isinstance(exclusion, dict)
            or exclusion.get("candidate_type") != "excluded"
            or not str(exclusion.get("name", "")).strip()
            or not str(exclusion.get("reason", "")).strip()
        ):
            errors.append("invalid exclusion; require name, candidate_type excluded, and reason")
    selected_slugs = {candidate.get("slug") for candidate in selected}
    expected_slugs = {
        candidate.get("slug") for candidate in candidates if isinstance(candidate, dict)
    }
    if selected_slugs != expected_slugs:
        errors.append("full coverage requires every retained candidate to be selected")

    thresholds = input_data.get("recommendation_thresholds", {"watch_min": 65, "meeting_min": 80})
    summary_skipped = [
        str(candidate.get("name")) for candidate in candidates
        if isinstance(candidate, dict) and not candidate.get("selected_for_research")
    ] + [
        str(exclusion.get("name")) for exclusion in excluded
        if isinstance(exclusion, dict) and exclusion.get("name")
    ]
    summary_gaps: list[tuple[str, str]] = []
    summary_retries: list[str] = []
    for candidate in candidates:
        name, slug = candidate["name"], candidate["slug"]
        company_dir = run_dir / "companies" / slug
        evidence = _add_json_error(company_dir / "evidence.json", errors, f"evidence for {name}") or {}
        identity_claim_ids = _validate_evidence_identity_and_sources(
            evidence, candidate, errors
        )
        coverage = evidence.get("coverage", {}) if isinstance(evidence, dict) else {}
        if not isinstance(coverage, dict):
            errors.append(f"coverage for {name} must be an object")
            coverage = {}
        for category in CATEGORIES:
            value = coverage.get(category)
            if value not in {"present", "missing"}:
                errors.append(f"invalid coverage for {name}: {category}={value}")
        expected_missing = [category for category in CATEGORIES if coverage.get(category) == "missing"]
        summary_gaps.extend((name, category) for category in expected_missing)
        if evidence.get("missing_categories") != expected_missing:
            errors.append(f"missing_categories not normalized for {name}")
        if evidence.get("unresolved_gaps") != expected_missing:
            errors.append(f"unresolved_gaps not normalized for {name}")
        retrieval_urls = {canonicalize_url(candidate.get("website"))}
        retrieval_urls.update(canonicalize_url(url) for url in candidate.get("source_urls", []) if url)
        retrievals = evidence.get("retrievals", []) if isinstance(evidence, dict) else []
        if not isinstance(retrievals, list) or not retrievals:
            errors.append(f"missing retrieval provenance for {name}")
            retrievals = []
        if len(retrievals) > 2:
            errors.append(f"more than one targeted retry recorded for {name}")
        initial_missing = evidence.get("initial_missing_categories") if isinstance(evidence, dict) else None
        if len(retrievals) == 2:
            summary_retries.append(name)
            initial_coverage = evidence.get("initial_coverage")
            if not isinstance(initial_coverage, dict) or any(
                initial_coverage.get(category) not in {"present", "missing"}
                for category in CATEGORIES
            ):
                errors.append(f"initial_coverage must contain binary coverage for {name}")
                derived_initial_missing = None
            else:
                derived_initial_missing = [
                    category for category in CATEGORIES
                    if initial_coverage.get(category) == "missing"
                ]
            if (
                not isinstance(initial_missing, list)
                or not initial_missing
                or initial_missing != [category for category in CATEGORIES if category in initial_missing]
            ):
                errors.append(f"initial_missing_categories must be a non-empty normalized list for {name}")
            elif initial_missing != derived_initial_missing:
                errors.append(f"initial_missing_categories does not match initial_coverage for {name}")
            elif not set(expected_missing).issubset(initial_missing):
                errors.append(f"initial_missing_categories omits a final unresolved gap for {name}")
        for index, retrieval in enumerate(retrievals):
            if not isinstance(retrieval, dict) or not retrieval.get("artifact_path"):
                errors.append(f"invalid retrieval provenance for {name} at index {index}")
                continue
            try:
                retrieval_path = _safe_artifact(run_dir, retrieval["artifact_path"])
            except (TypeError, ValueError) as error:
                errors.append(f"invalid retrieval artifact path for {name} at index {index}: {error}")
                continue
            retrieval_urls.update(
                _validate_retrieval(
                    retrieval_path, errors, f"retrieval for {name} at index {index}",
                    max_results=5,
                )
            )
            try:
                retrieval_value = read_json(retrieval_path)
            except (OSError, json.JSONDecodeError):
                retrieval_value = {}
            for field in ("provider", "query", "retrieved_at", "status", "exit_code"):
                if field not in retrieval:
                    errors.append(f"retrieval provenance for {name} missing {field}")
                elif isinstance(retrieval_value, dict) and retrieval.get(field) != retrieval_value.get(field):
                    errors.append(f"retrieval provenance does not match artifact for {name}: {field}")
            expected_name = "retrieval-initial.json" if index == 0 else "retrieval-retry.json"
            expected_relative = f"companies/{slug}/{expected_name}"
            if Path(retrieval["artifact_path"]).as_posix() != expected_relative:
                errors.append(f"retrieval artifact must stay within the current company for {name} at index {index}")
            if retrieval_path.name != expected_name:
                errors.append(f"unexpected retrieval artifact for {name} at index {index}")
            if index == 1:
                try:
                    retry_value = read_json(retrieval_path)
                    retry_focus = retry_value.get("missing_categories")
                    if not isinstance(retry_focus, list) or not retry_focus:
                        errors.append(f"empty retry focus for {name}")
                    elif retry_focus != [category for category in CATEGORIES if category in retry_focus]:
                        errors.append(f"retry focus is not normalized for {name}")
                    elif retry_focus != initial_missing:
                        errors.append(f"retry focus does not match initial_missing_categories for {name}")
                    if retrieval.get("missing_categories") != initial_missing:
                        errors.append(f"retry provenance does not match initial_missing_categories for {name}")
                except (OSError, json.JSONDecodeError, TypeError, ValueError):
                    pass
        if retrievals and not any(
            isinstance(retrieval, dict) and retrieval.get("status") == "ok"
            for retrieval in retrievals
        ):
            errors.append(f"completed research requires at least one successful retrieval for {name}")
        claim_ids = {}
        claims = evidence.get("claims", []) if isinstance(evidence, dict) else []
        if not isinstance(claims, list):
            errors.append(f"claims for {name} must be an array")
            claims = []
        for index, claim in enumerate(claims):
            if not isinstance(claim, dict):
                errors.append(f"claim for {name} at index {index} must be an object")
                continue
            if not str(claim.get("claim", "")).strip():
                errors.append(f"claim text missing for {name} at index {index}")
            claim_id = claim.get("id")
            if not isinstance(claim_id, str) or not claim_id.strip():
                errors.append(f"missing or invalid claim id for {name} at index {index}")
                claim_id = None
            elif claim_id in claim_ids:
                errors.append(f"missing or duplicate claim id for {name} at index {index}")
            if claim_id:
                claim_ids[claim_id] = claim
            if claim.get("area") not in CATEGORIES:
                errors.append(f"invalid claim area for {name}: {claim.get('area')}")
            if claim.get("claim_type") not in CLAIM_TYPES:
                errors.append(f"invalid claim_type for {name}: {claim.get('claim_type')}")
            if claim.get("source_quality") not in SOURCE_QUALITIES:
                errors.append(f"invalid claim source_quality for {name}")
            if claim.get("confidence") not in CONFIDENCES:
                errors.append(f"invalid claim confidence for {name}")
            source_url = canonicalize_url(claim.get("source_url"))
            if claim.get("claim_type") != "unknown" and not source_url:
                errors.append(f"sourced claim missing URL for {name}: {claim_id}")
            if source_url and source_url not in retrieval_urls:
                errors.append(f"claim source URL not present in retrieval for {name}: {source_url}")

        if set(identity_claim_ids) != set(claim_ids):
            errors.append(f"evidence claim identity mismatch for {name}")

        used_claim_ids: set[str] = set()
        score, call = _parse_analysis(
            company_dir / "analysis.md", errors, name, claim_ids, coverage,
            rubric_weights, used_claim_ids, candidate.get("website"),
        )
        for claim_id in sorted(set(claim_ids) - used_claim_ids):
            errors.append(f"unused claim for {name}: {claim_id}")
        memo_score, memo_call = _parse_memo(company_dir / "memo.md", errors, name)
        if score is not None and call:
            expected_call = _expected_call(score, thresholds)
            if call.lower() != expected_call.lower():
                errors.append(f"analysis recommendation mismatch for {name}: {call} != {expected_call}")
        if score != memo_score:
            errors.append(f"memo score mismatch for {name}: {memo_score} != {score}")
        if call and memo_call and call.lower() != memo_call.lower():
            errors.append(f"memo recommendation mismatch for {name}: {memo_call} != {call}")
        summary_path = run_dir / "run-summary.md"
        if summary_path.exists() and score is not None and call:
            summary = summary_path.read_text(encoding="utf-8")
            row = rf"\|\s*{re.escape(name)}\s*\|\s*{score}\s*\|\s*{re.escape(call)}\s*\|"
            if not re.search(row, summary, re.I):
                errors.append(f"run-summary mismatch for {name}")
        company_manifest = manifest.get("companies", {}).get(slug, {}) if isinstance(manifest, dict) else {}
        research_attempts = company_manifest.get("research", {}).get("attempt_count")
        if isinstance(retrievals, list) and research_attempts != len(retrievals):
            errors.append(f"manifest research attempts do not match retrieval count for {name}")
        for stage in ("research", "analysis", "memo"):
            stage_record = company_manifest.get(stage, {})
            if stage_record.get("status") != "completed":
                errors.append(f"manifest stage not completed for {name}: {stage}")
            expected_artifact = {
                "research": f"companies/{slug}/evidence.json",
                "analysis": f"companies/{slug}/analysis.md",
                "memo": f"companies/{slug}/memo.md",
            }[stage]
            if expected_artifact not in stage_record.get("artifacts", []):
                errors.append(
                    f"manifest {stage} artifacts do not cover {name}: {expected_artifact}"
                )
    if manifest.get("stages", {}).get("sourcing", {}).get("status") != "completed":
        errors.append("manifest sourcing stage is not completed")
    summary_path = run_dir / "run-summary.md"
    if not summary_path.exists() or not summary_path.read_text(encoding="utf-8").strip():
        errors.append("missing run-summary.md")
    else:
        summary_text = summary_path.read_text(encoding="utf-8")
        heading_matches = list(re.finditer(r"^##\s+(.+?)\s*$", summary_text, re.M))
        sections = {}
        for index, match in enumerate(heading_matches):
            end = heading_matches[index + 1].start() if index + 1 < len(heading_matches) else len(summary_text)
            sections[match.group(1).strip().lower()] = summary_text[match.end():end]
        for heading in (
            "Decisions", "Skipped candidates", "Unresolved gaps", "Retries", "Failures"
        ):
            if heading.lower() not in sections:
                errors.append(f"run-summary missing {heading} section")
        decisions_text = sections.get("decisions", "")
        skipped_text = sections.get("skipped candidates", "")
        gaps_text = sections.get("unresolved gaps", "")
        retries_text = sections.get("retries", "")
        failures_text = sections.get("failures", "")
        for candidate in selected:
            name = candidate.get("name", "")
            company_dir = run_dir / "companies" / candidate.get("slug", "")
            score, call = _parse_analysis(company_dir / "analysis.md", [], str(name), {}, {})
            if score is not None and call and not re.search(
                rf"\|\s*{re.escape(str(name))}\s*\|\s*{score}\s*\|\s*{re.escape(call)}\s*\|",
                decisions_text,
                re.I,
            ):
                errors.append(f"run-summary decision is outside Decisions section for {name}")
        for skipped_name in summary_skipped:
            if skipped_name.lower() not in skipped_text.lower():
                errors.append(f"run-summary missing skipped candidate: {skipped_name}")
        for gap_name, category in summary_gaps:
            if not re.search(
                rf"{re.escape(gap_name)}[^\n]*\b{re.escape(category)}\b",
                gaps_text,
                re.I,
            ):
                errors.append(f"run-summary missing unresolved gap for {gap_name}: {category}")
        for retry_name in summary_retries:
            if not re.search(rf"{re.escape(retry_name)}[^\n]*retry", retries_text, re.I):
                errors.append(f"run-summary missing retry for {retry_name}")
        failure_labels = []
        for stage, record in manifest.get("stages", {}).items():
            if isinstance(record, dict) and record.get("status") in {"partial", "failed"}:
                failure_labels.append(stage)
        for slug, company_stages in manifest.get("companies", {}).items():
            if not isinstance(company_stages, dict):
                continue
            for stage, record in company_stages.items():
                if isinstance(record, dict) and record.get("status") in {"partial", "failed"}:
                    failure_labels.append(f"{slug} {stage}")
        validation_record = manifest.get("validation", {})
        if isinstance(validation_record, dict) and validation_record.get("status") in {"partial", "failed"}:
            failure_labels.append("validation")
        for failure_label in failure_labels:
            if failure_label.lower() not in failures_text.lower():
                errors.append(f"run-summary missing failure: {failure_label}")
    return {
        "valid": not errors,
        "layout": "current",
        "run_dir": str(run_dir),
        "errors": errors,
        "warnings": warnings,
    }


def validate_run(run_dir: str | Path) -> dict:
    run_dir = Path(run_dir)
    manifest_path = run_dir / "manifest.json"
    marker_path = run_dir / ASSIGNMENT_V2.INITIALIZATION_MARKER
    if manifest_path.exists():
        try:
            manifest = read_json(manifest_path)
        except (OSError, json.JSONDecodeError):
            manifest = None
        try:
            result = _validate_new(run_dir)
            lifecycle_errors = (
                ASSIGNMENT_V2.validate_stored_assignment(run_dir, manifest)
                if isinstance(manifest, dict)
                else []
            )
        except (AttributeError, TypeError, ValueError, OSError, UnicodeError) as error:
            return {
                "valid": False,
                "layout": "current",
                "run_dir": str(run_dir),
                "errors": [f"malformed current artifacts: {error}"],
                "warnings": [],
            }
        result["errors"] = lifecycle_errors + result["errors"]
        result["valid"] = not result["errors"]
        return result

    v2_intended = (run_dir / "rubric.json").exists() or marker_path.exists()
    try:
        stored_input = read_json(run_dir / "input.json")
    except (OSError, json.JSONDecodeError):
        stored_input = None
    if isinstance(stored_input, dict) and stored_input.get("version") == 2:
        v2_intended = True
    if v2_intended:
        try:
            return _validate_new(run_dir)
        except (AttributeError, TypeError, ValueError, OSError, UnicodeError) as error:
            return {
                "valid": False,
                "layout": "current",
                "run_dir": str(run_dir),
                "errors": [f"malformed current artifacts: {error}"],
                "warnings": [],
            }

    candidates_path = run_dir / "sourcing" / "candidates.json"
    try:
        candidates = read_json(candidates_path)
    except (OSError, json.JSONDecodeError):
        candidates = None
    affirmative_legacy = (
        isinstance(candidates, list)
        and (run_dir / "sourcing" / "sourcing.md").is_file()
        and (run_dir / "evidence").is_dir()
    )
    if affirmative_legacy:
        return _validate_legacy(run_dir)
    return _validate_new(run_dir)


def _compact(value: dict) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    preflight_parser = subparsers.add_parser("preflight")
    preflight_parser.add_argument("--cwd", type=Path, default=Path.cwd())
    preflight_parser.add_argument("--output", type=Path)
    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("--run-dir", type=Path, required=True)
    init_parser.add_argument("--input", type=Path, required=True)
    init_parser.add_argument("--thesis", type=Path, required=True)
    init_parser.add_argument("--rubric", type=Path, required=True)
    supersede_parser = subparsers.add_parser("supersede")
    supersede_parser.add_argument("--supersedes-run-dir", type=Path, required=True)
    supersede_parser.add_argument("--run-dir", type=Path, required=True)
    supersede_parser.add_argument("--input", type=Path, required=True)
    supersede_parser.add_argument("--thesis", type=Path, required=True)
    supersede_parser.add_argument("--rubric", type=Path, required=True)
    stage_parser = subparsers.add_parser("stage")
    stage_parser.add_argument("--run-dir", type=Path, required=True)
    stage_parser.add_argument("--stage", choices=sorted(STAGES), required=True)
    stage_parser.add_argument("--status", choices=sorted(STATUSES), required=True)
    stage_parser.add_argument("--company")
    stage_parser.add_argument("--provider", choices=sorted(PROVIDERS))
    stage_parser.add_argument("--exit-code", type=int)
    stage_parser.add_argument("--error")
    stage_parser.add_argument("--artifact", action="append", default=[])
    commit_parser = subparsers.add_parser("commit")
    commit_parser.add_argument("--source", type=Path, required=True)
    commit_parser.add_argument("--destination", type=Path, required=True)
    commit_parser.add_argument("--kind", choices=["json", "text"], required=True)
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--run-dir", type=Path, required=True)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "preflight":
            result = preflight(cwd=args.cwd)
            if args.output:
                atomic_write_json(args.output, result)
            print(_compact(result))
            return 0 if result["runtime"]["usable"] else EXIT_RUNTIME
        if args.command == "init":
            result = initialize_run(args.run_dir, args.input, args.thesis, args.rubric)
            print(_compact({"status": "ok", "run_dir": str(args.run_dir), "resumed": result["resumed"]}))
            return 0
        if args.command == "supersede":
            result = supersede_run(
                args.supersedes_run_dir,
                args.run_dir,
                args.input,
                args.thesis,
                args.rubric,
            )
            print(
                _compact(
                    {
                        "status": "ok",
                        "run_dir": str(args.run_dir),
                        "supersedes_run_id": result["manifest"]["supersedes_run_id"],
                    }
                )
            )
            return 0
        if args.command == "stage":
            update_stage(
                args.run_dir,
                args.stage,
                args.status,
                company=args.company,
                provider=args.provider,
                exit_code=args.exit_code,
                error=args.error,
                artifacts=args.artifact,
            )
            print(_compact({"status": "ok", "stage": args.stage, "company": args.company}))
            return 0
        if args.command == "commit":
            result = atomic_promote(args.source, args.destination, kind=args.kind)
            print(_compact({"status": "ok", "artifact": str(result)}))
            return 0
        if args.command == "validate":
            result = validate_run(args.run_dir)
            print(_compact(result))
            return 0 if result["valid"] else EXIT_VALIDATION
    except ArtifactWriteError as error:
        print(_compact({"status": "failed", "error": str(error)}), file=sys.stderr)
        return EXIT_WRITE
    except (AttributeError, TypeError, ValueError, OSError, json.JSONDecodeError) as error:
        print(_compact({"status": "failed", "error": str(error)}), file=sys.stderr)
        if args.command == "commit":
            return EXIT_WRITE
        if args.command == "validate":
            return EXIT_VALIDATION
        return EXIT_INPUT
    return EXIT_INPUT


if __name__ == "__main__":
    raise SystemExit(main())
