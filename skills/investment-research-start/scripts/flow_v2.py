"""Flow-v2 input, rubric, and fingerprint contracts."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


VERSION = 2
INITIALIZATION_MARKER = ".flow-v2-init.json"
RUBRIC_CATEGORIES = (
    "Team",
    "Product differentiation",
    "Market",
    "Traction",
    "Thesis alignment",
)
ANCHOR_SCORES = ("0", "10", "20")
PRIMARY_SOURCES = ("product_hunt", "yc")
SIGNAL_SOURCES = ("hacker_news",)
STOPWORDS = {
    "about", "after", "also", "and", "are", "back", "been", "being",
    "between", "but", "can", "could", "does", "each", "for", "from",
    "have", "into", "investment", "its", "more", "most", "not", "only", "other",
    "our", "over", "should", "than", "that", "the", "their", "then",
    "there", "these", "they", "this", "those", "through", "under",
    "thesis", "using", "very", "was", "were", "what", "when", "where", "which",
    "while", "will", "with", "would", "your",
}


def normalize_input(value: dict) -> dict:
    """Validate and materialize the flow-v2 input contract."""
    if not isinstance(value, dict):
        raise ValueError("input must be a JSON object")
    if value.get("version", VERSION) != VERSION:
        raise ValueError("input.version must be 2")
    seed = value.get("seed")
    if not isinstance(seed, dict) or seed.get("type") not in {"topic", "urls", "feed"}:
        raise ValueError("seed.type must be topic, urls, or feed")
    seed_value = seed.get("value")
    if seed["type"] == "urls":
        if not isinstance(seed_value, list) or not seed_value or not all(
            isinstance(item, str) and item.strip() for item in seed_value
        ):
            raise ValueError("seed.value must be a non-empty URL list")
        normalized_seed = {"type": "urls", "value": [item.strip() for item in seed_value]}
    else:
        if not isinstance(seed_value, str) or not seed_value.strip():
            raise ValueError("seed.value must be non-empty")
        normalized_seed = {"type": seed["type"], "value": seed_value.strip()}

    sourcing = value.get("sourcing", {})
    research = value.get("research", {})
    thresholds = value.get("recommendation_thresholds", {})
    if not isinstance(sourcing, dict):
        raise ValueError("sourcing must be an object")
    if not isinstance(research, dict):
        raise ValueError("research must be an object")
    if not isinstance(thresholds, dict):
        raise ValueError("recommendation_thresholds must be an object")
    target_count = sourcing.get("target_count", 10)
    if isinstance(target_count, bool) or not isinstance(target_count, int) or not 10 <= target_count <= 20:
        raise ValueError("sourcing.target_count must be an integer from 10 through 20")
    primary_sources = sourcing.get("primary_sources", list(PRIMARY_SOURCES))
    signal_sources = sourcing.get("signal_sources", list(SIGNAL_SOURCES))
    if not isinstance(primary_sources, list) or len(primary_sources) != 2 or set(primary_sources) != set(PRIMARY_SOURCES):
        raise ValueError("sourcing.primary_sources must contain product_hunt and yc")
    if not isinstance(signal_sources, list) or signal_sources != list(SIGNAL_SOURCES):
        raise ValueError("sourcing.signal_sources must contain only hacker_news")
    full_coverage = research.get("full_coverage", True)
    if full_coverage is not True:
        raise ValueError("research.full_coverage must be exactly true")
    if "limit" in research:
        raise ValueError("research.limit is not allowed for flow-v2 full coverage")
    normalized_research = {"full_coverage": True}
    watch_min = thresholds.get("watch_min", 65)
    meeting_min = thresholds.get("meeting_min", 80)
    if not all(isinstance(item, int) and not isinstance(item, bool) for item in (watch_min, meeting_min)):
        raise ValueError("recommendation thresholds must be integers")
    if not 0 <= watch_min < meeting_min <= 100:
        raise ValueError("thresholds must satisfy 0 <= watch_min < meeting_min <= 100")
    assumptions = value.get("assumptions", [])
    if not isinstance(assumptions, list) or not all(isinstance(item, str) for item in assumptions):
        raise ValueError("assumptions must be an array of strings")
    return {
        "version": VERSION,
        "seed": normalized_seed,
        "sourcing": {
            "target_count": target_count,
            "primary_sources": list(PRIMARY_SOURCES),
            "signal_sources": list(SIGNAL_SOURCES),
        },
        "research": normalized_research,
        "recommendation_thresholds": {"watch_min": watch_min, "meeting_min": meeting_min},
        "assumptions": assumptions,
    }


def thesis_fingerprint(thesis: str) -> str:
    return hashlib.sha256(thesis.encode("utf-8")).hexdigest()


def input_fingerprint(input_data: dict, thesis: str) -> str:
    serialized = json.dumps(input_data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(f"{serialized}\n{thesis}".encode("utf-8")).hexdigest()


def _meaningful_tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.casefold())
        if len(token) >= 4 and token not in STOPWORDS
    }


def validate_rubric(value: dict, thesis: str) -> dict:
    """Validate the exact five-row, thesis-bound rubric schema."""
    if not isinstance(value, dict):
        raise ValueError("rubric.json must contain a JSON object")
    if value.get("version") != VERSION:
        raise ValueError("rubric.version must be 2")
    if value.get("total_weight") != 100:
        raise ValueError("rubric total_weight must be 100")
    if value.get("thesis_fingerprint") != thesis_fingerprint(thesis):
        raise ValueError("rubric thesis_fingerprint must match thesis.md")
    categories = value.get("categories")
    if not isinstance(categories, list) or len(categories) != len(RUBRIC_CATEGORIES):
        raise ValueError("rubric must contain exactly five categories")
    names = tuple(category.get("name") if isinstance(category, dict) else None for category in categories)
    if names != RUBRIC_CATEGORIES:
        raise ValueError(
            "rubric categories must be Team, Product differentiation, Market, "
            "Traction, and Thesis alignment in that order"
        )
    for category in categories:
        name = category["name"]
        if category.get("weight") != 20:
            raise ValueError(f"rubric category weight must be 20: {name}")
        anchors = category.get("anchors")
        if (
            not isinstance(anchors, dict)
            or len(anchors) != len(ANCHOR_SCORES)
            or set(anchors) != set(ANCHOR_SCORES)
        ):
            raise ValueError(f"rubric category requires exact 0/10/20 anchors: {name}")
        if not all(isinstance(anchors[score], str) and anchors[score].strip() for score in ANCHOR_SCORES):
            raise ValueError(f"rubric anchors must be non-empty thesis-specific text: {name}")
        normalized_texts = {
            " ".join(anchors[score].casefold().split()) for score in ANCHOR_SCORES
        }
        if len(normalized_texts) != len(ANCHOR_SCORES):
            raise ValueError(f"rubric anchor level texts must be distinct: {name}")
        thesis_tokens = _meaningful_tokens(thesis)
        if not thesis_tokens:
            raise ValueError("thesis must contain a meaningful token for rubric anchors")
        for score in ANCHOR_SCORES:
            if not (_meaningful_tokens(anchors[score]) & thesis_tokens):
                raise ValueError(
                    f"rubric anchor {score} must contain a meaningful thesis token: {name}"
                )
    if sum(category["weight"] for category in categories) != 100:
        raise ValueError("rubric category weights must total 100")
    return value


def rubric_fingerprint(rubric: dict) -> str:
    serialized = json.dumps(rubric, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def flow_fingerprint(input_data: dict, thesis: str, rubric: dict) -> str:
    payload = {"input": input_data, "thesis": thesis, "rubric": rubric}
    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _resolved_link_target(
    run_dir: Path, path_value: object, label: str, errors: list[str]
) -> Path | None:
    if not isinstance(path_value, str) or not path_value.strip():
        errors.append(f"{label} linked target path is invalid")
        return None
    path = Path(path_value)
    if not path.is_absolute():
        errors.append(f"{label} linked target path must be absolute")
        return None
    try:
        target = path.resolve(strict=True)
        current = run_dir.resolve(strict=True)
    except OSError as error:
        errors.append(f"{label} linked target path does not exist: {error}")
        return None
    if not target.is_dir() or target == current:
        errors.append(f"{label} linked target path must identify a different run directory")
        return None
    if str(target) != path_value:
        errors.append(f"{label} linked target path must be resolved exactly")
        return None
    return target


def _read_linked_manifest(target: Path, label: str, errors: list[str]) -> dict | None:
    try:
        value = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("manifest must be an object")
    except (OSError, json.JSONDecodeError, ValueError) as error:
        errors.append(f"{label} linked target manifest is invalid: {error}")
        return None
    target_errors = validate_stored_flow(target, value, validate_links=False)
    errors.extend(f"{label} linked target {error}" for error in target_errors)
    return value


def _same_resolved_path(path_value: object, expected: Path) -> bool:
    if not isinstance(path_value, str) or not Path(path_value).is_absolute():
        return False
    try:
        return Path(path_value).resolve(strict=True) == expected.resolve(strict=True)
    except OSError:
        return False


def validate_stored_flow(
    run_dir: str | Path, manifest: dict, *, validate_links: bool = True
) -> list[str]:
    """Return lifecycle errors for a stored v2 flow without writing files."""
    run_dir = Path(run_dir)
    errors: list[str] = []
    try:
        input_data = normalize_input(json.loads((run_dir / "input.json").read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, ValueError) as error:
        errors.append(f"invalid flow-v2 input.json: {error}")
        input_data = None
    try:
        thesis = (run_dir / "thesis.md").read_text(encoding="utf-8")
        if not thesis.strip():
            raise ValueError("thesis.md must not be empty")
    except (OSError, ValueError) as error:
        errors.append(f"invalid flow-v2 thesis.md: {error}")
        thesis = None
    try:
        rubric = json.loads((run_dir / "rubric.json").read_text(encoding="utf-8"))
        if thesis is not None:
            validate_rubric(rubric, thesis)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        errors.append(f"invalid flow-v2 rubric.json: {error}")
        rubric = None
    if not isinstance(manifest, dict):
        return ["manifest must be a JSON object"]
    if manifest.get("version") != VERSION:
        errors.append("manifest.version must be 2")
    run_id = manifest.get("run_id")
    if not isinstance(run_id, str) or not run_id.strip() or run_id != run_dir.name:
        errors.append("manifest run_id must match the run directory name")
    if input_data is not None and thesis is not None and rubric is not None:
        if manifest.get("input_fingerprint") != input_fingerprint(input_data, thesis):
            errors.append("manifest input fingerprint does not match input.json and thesis.md")
        if manifest.get("flow_fingerprint") != flow_fingerprint(input_data, thesis, rubric):
            errors.append("manifest flow fingerprint does not match input, thesis, and rubric")
        if manifest.get("rubric_fingerprint") != rubric_fingerprint(rubric):
            errors.append("manifest rubric fingerprint does not match rubric.json")
    supersedes_run_id = manifest.get("supersedes_run_id")
    supersedes_run_path = manifest.get("supersedes_run_path")
    if (supersedes_run_id is None) != (supersedes_run_path is None) or (
        supersedes_run_id is not None
        and (
            not isinstance(supersedes_run_id, str)
            or not supersedes_run_id.strip()
            or not isinstance(supersedes_run_path, str)
            or not supersedes_run_path.strip()
        )
    ):
        errors.append("manifest supersedes linkage must provide both run id and path")
    superseded_by = manifest.get("superseded_by")
    if superseded_by is not None:
        if not isinstance(superseded_by, dict) or any(
            not isinstance(superseded_by.get(field), str)
            or not superseded_by.get(field, "").strip()
            for field in ("run_id", "path", "flow_fingerprint", "linked_at")
        ):
            errors.append("manifest superseded_by linkage is invalid")
        elif not re.fullmatch(r"[0-9a-f]{64}", superseded_by["flow_fingerprint"]):
            errors.append("manifest superseded_by linkage has an invalid flow fingerprint")

    if not validate_links:
        return errors

    current_path = run_dir.resolve()
    current_fingerprint = manifest.get("flow_fingerprint")
    if isinstance(supersedes_run_id, str) and isinstance(supersedes_run_path, str):
        target = _resolved_link_target(run_dir, supersedes_run_path, "supersedes", errors)
        if target is not None:
            target_manifest = _read_linked_manifest(target, "supersedes", errors)
            if target_manifest is not None:
                if target_manifest.get("run_id") != supersedes_run_id:
                    errors.append("supersedes target run_id does not match the forward link")
                reciprocal = target_manifest.get("superseded_by")
                if not isinstance(reciprocal, dict):
                    errors.append("supersedes target is missing reciprocal superseded_by linkage")
                else:
                    if reciprocal.get("run_id") != run_id:
                        errors.append("supersedes target reciprocal run_id does not match")
                    if reciprocal.get("flow_fingerprint") != current_fingerprint:
                        errors.append(
                            "supersedes target reciprocal flow fingerprint does not match"
                        )
                    if not _same_resolved_path(reciprocal.get("path"), current_path):
                        errors.append("supersedes target reciprocal path does not match")

    if isinstance(superseded_by, dict) and all(
        isinstance(superseded_by.get(field), str)
        for field in ("run_id", "path", "flow_fingerprint")
    ):
        target = _resolved_link_target(run_dir, superseded_by["path"], "superseded_by", errors)
        if target is not None:
            target_manifest = _read_linked_manifest(target, "superseded_by", errors)
            if target_manifest is not None:
                if target_manifest.get("run_id") != superseded_by["run_id"]:
                    errors.append("superseded_by target run_id does not match the backward link")
                if target_manifest.get("flow_fingerprint") != superseded_by.get(
                    "flow_fingerprint"
                ):
                    errors.append(
                        "superseded_by target flow fingerprint does not match the backward link"
                    )
                if target_manifest.get("supersedes_run_id") != run_id:
                    errors.append("superseded_by target is missing reciprocal supersedes run_id")
                if not _same_resolved_path(
                    target_manifest.get("supersedes_run_path"), current_path
                ):
                    errors.append("superseded_by target reciprocal supersedes path does not match")
    return errors
