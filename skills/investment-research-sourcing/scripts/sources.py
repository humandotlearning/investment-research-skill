"""Parse assignment-v2 source snapshots into deterministic candidate records."""

from __future__ import annotations

import copy
import json
import re
import xml.etree.ElementTree as element_tree
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, urlsplit, urlunsplit


ATOM_NAMESPACE = "{http://www.w3.org/2005/Atom}"
ORIGIN_HOSTS = {
    "product_hunt": {"producthunt.com", "www.producthunt.com"},
    "yc": {"ycombinator.com", "www.ycombinator.com"},
}
REQUIRED_CANDIDATE_FIELDS = (
    "name",
    "slug",
    "website",
    "one_line_description",
    "origins",
    "team_signal",
    "freshness_or_traction_signals",
    "thesis_fit_reasons",
    "rank",
)


def _canonicalize_url(value: Any) -> str | None:
    if not value:
        return None
    parsed = urlsplit(str(value).strip())
    if not parsed.scheme or not parsed.hostname:
        return None
    scheme = parsed.scheme.lower()
    host = parsed.hostname.lower()
    try:
        port = parsed.port
    except ValueError:
        return None
    netloc = host
    if port and not ((scheme == "https" and port == 443) or (scheme == "http" and port == 80)):
        netloc = f"{host}:{port}"
    path = parsed.path.rstrip("/")
    return urlunsplit((scheme, netloc, path, "", ""))


def _domain(value: Any) -> str | None:
    canonical = _canonicalize_url(value)
    if canonical is None:
        return None
    host = urlsplit(canonical).hostname
    if not host:
        return None
    return host.removeprefix("www.")


def _normalized_name(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _slug(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")


def _origin_sort_key(origin: dict) -> tuple[str, str, str, str]:
    return (
        str(origin.get("source", "")),
        str(origin.get("canonical_url", "")),
        str(origin.get("source_id", "")),
        str(origin.get("publication_or_batch_date", "")),
    )


def _signal_sort_key(signal: dict) -> str:
    return json.dumps(signal, sort_keys=True, separators=(",", ":"), default=str)


def _is_signal(signal: Any) -> bool:
    return (
        isinstance(signal, dict)
        and signal.get("kind") in {"freshness", "traction"}
        and bool(signal.get("source_url"))
    )


def _is_official_hn_item_url(value: Any) -> bool:
    parsed = urlsplit(str(value or "").strip())
    query = parse_qs(parsed.query, keep_blank_values=True)
    return (
        parsed.scheme.lower() == "https"
        and parsed.hostname == "news.ycombinator.com"
        and parsed.path == "/item"
        and set(query) == {"id"}
        and len(query["id"]) == 1
        and query["id"][0].isdigit()
    )


def _is_trusted_signal(signal: Any, origins: list[dict]) -> bool:
    if not _is_signal(signal):
        return False
    source_url = signal["source_url"]
    if _is_official_hn_item_url(source_url):
        return True
    canonical_source_url = _canonicalize_url(source_url)
    return canonical_source_url is not None and any(
        canonical_source_url == _canonicalize_url(origin.get("canonical_url"))
        for origin in origins
        if origin_is_allowed(origin)
    )


def origin_is_allowed(origin: Any) -> bool:
    """Return whether an origin has an approved source name and exact host."""
    if not isinstance(origin, dict):
        return False
    source = origin.get("source")
    if source not in ORIGIN_HOSTS:
        return False
    canonical_url = _canonicalize_url(origin.get("canonical_url"))
    if canonical_url is None:
        return False
    parsed = urlsplit(canonical_url)
    return parsed.scheme == "https" and parsed.hostname in ORIGIN_HOSTS[source]


def _origin_is_complete(origin: Any) -> bool:
    return origin_is_allowed(origin) and all(
        origin.get(field) for field in ("source_id", "publication_or_batch_date")
    )


def parse_product_hunt_atom(atom_text: str) -> list[dict]:
    """Parse Product Hunt Atom entries into source records without network access."""
    root = element_tree.fromstring(atom_text)
    records = []
    for entry in root.findall(f"{ATOM_NAMESPACE}entry"):
        links = {
            link.get("rel"): link.get("href")
            for link in entry.findall(f"{ATOM_NAMESPACE}link")
            if link.get("rel") and link.get("href")
        }
        origin_url = _canonicalize_url(links.get("alternate"))
        website = _canonicalize_url(links.get("related"))
        title = (entry.findtext(f"{ATOM_NAMESPACE}title") or "").strip()
        name = re.split(r"\s+[\-–—]\s+", title, maxsplit=1)[0].strip()
        slug = _slug((urlsplit(origin_url).path if origin_url else "").split("/")[-1])
        source_id = (entry.findtext(f"{ATOM_NAMESPACE}id") or "").strip()
        published = (entry.findtext(f"{ATOM_NAMESPACE}updated") or "").strip()
        summary = (entry.findtext(f"{ATOM_NAMESPACE}summary") or "").strip()
        if not (name and slug and website and origin_url and source_id and published):
            continue
        origin = {
            "source": "product_hunt",
            "canonical_url": origin_url,
            "source_id": source_id,
            "publication_or_batch_date": published,
        }
        if not origin_is_allowed(origin):
            continue
        records.append(
            {
                "name": name,
                "slug": slug,
                "website": website,
                "one_line_description": summary,
                "origins": [origin],
                "team_signal": None,
                "freshness_or_traction_signals": [
                    {"kind": "freshness", "source_url": origin_url, "date": published}
                ],
                "thesis_fit_reasons": [],
            }
        )
    return records


def normalize_yc_snapshot(snapshot: Any) -> list[dict]:
    """Normalize public YC company-directory/profile snapshots into source records."""
    if isinstance(snapshot, dict) and "companies" in snapshot:
        companies = snapshot["companies"]
    elif isinstance(snapshot, dict):
        companies = [snapshot]
    else:
        companies = snapshot
    if not isinstance(companies, list):
        return []
    records = []
    for company in companies:
        if not isinstance(company, dict):
            continue
        name = str(company.get("name") or "").strip()
        slug = str(company.get("slug") or _slug(name)).strip()
        website = _canonicalize_url(company.get("website"))
        description = str(company.get("one_liner") or company.get("description") or "").strip()
        origin_url = _canonicalize_url(company.get("url"))
        source_id = company.get("id")
        batch = company.get("batch") or company.get("launched_at")
        if not (name and slug and website and description and origin_url and source_id is not None and batch):
            continue
        origin = {
            "source": "yc",
            "canonical_url": origin_url,
            "source_id": str(source_id),
            "publication_or_batch_date": str(batch),
        }
        if not origin_is_allowed(origin):
            continue
        records.append(
            {
                "name": name,
                "slug": slug,
                "website": website,
                "one_line_description": description,
                "origins": [origin],
                "team_signal": None,
                "freshness_or_traction_signals": [
                    {"kind": "freshness", "source_url": origin_url, "date": str(batch)}
                ],
                "thesis_fit_reasons": [],
            }
        )
    return records


def _record_reason(record: Any) -> str | None:
    if not isinstance(record, dict):
        return "invalid record"
    origins = record.get("origins")
    if not isinstance(origins, list) or not origins or not all(_origin_is_complete(origin) for origin in origins):
        return "unsupported origin"
    if not all(record.get(field) for field in ("name", "slug", "one_line_description")):
        return "missing required candidate field"
    signals = record.get("freshness_or_traction_signals")
    if not isinstance(signals, list) or not any(
        _is_trusted_signal(signal, origins) for signal in signals
    ):
        return "missing freshness or traction signal from a trusted source"
    if not isinstance(record.get("thesis_fit_reasons"), list):
        return "missing thesis fit reasons"
    return None


def _record_key(record: dict) -> tuple[str, str, str]:
    return (
        _domain(record.get("website")) or "",
        _normalized_name(record.get("name")),
        _signal_sort_key(record),
    )


def _record_matches_group(record: dict, group: list[dict]) -> bool:
    record_domain = _domain(record.get("website"))
    group_domains = {_domain(member.get("website")) for member in group}
    group_domains.discard(None)
    if record_domain and group_domains:
        return record_domain in group_domains
    normalized_name = _normalized_name(record.get("name"))
    return bool(normalized_name) and any(
        normalized_name == _normalized_name(member.get("name")) for member in group
    )


def _unique_sorted(values: list[dict], key) -> list[dict]:
    unique = {}
    for value in values:
        unique[key(value)] = value
    return [unique[item] for item in sorted(unique)]


def _preferred_record(records: list[dict], field: str) -> Any:
    def preference(record: dict) -> tuple[int, int, str]:
        has_yc_origin = any(origin.get("source") == "yc" for origin in record["origins"])
        value = str(record.get(field) or "")
        return (0 if has_yc_origin else 1, -len(value), value.casefold())

    return min(records, key=preference).get(field)


def _preferred_website(records: list[dict]) -> str:
    def preference(record: dict) -> tuple[int, int, str]:
        website = str(record["website"])
        path = urlsplit(website).path.rstrip("/")
        return (0 if not path else 1, len(path), website)

    usable_records = [record for record in records if _canonicalize_url(record.get("website"))]
    if not usable_records:
        return None
    return min(usable_records, key=preference)["website"]


def _merge_records(records: list[dict]) -> dict:
    origins = _unique_sorted(
        [origin for record in records for origin in record["origins"]], _origin_sort_key
    )
    signals = _unique_sorted(
        [
            signal
            for record in records
            for signal in record["freshness_or_traction_signals"]
            if _is_trusted_signal(signal, record["origins"])
        ],
        _signal_sort_key,
    )
    reasons = sorted(
        {str(reason).strip() for record in records for reason in record["thesis_fit_reasons"] if str(reason).strip()},
        key=str.casefold,
    )
    team_signals = [record.get("team_signal") for record in records if record.get("team_signal") is not None]
    return {
        "name": _preferred_record(records, "name"),
        "slug": _preferred_record(records, "slug"),
        "website": _preferred_website(records),
        "one_line_description": _preferred_record(records, "one_line_description"),
        "origins": origins,
        "team_signal": min(team_signals, key=lambda value: _signal_sort_key({"value": value})) if team_signals else None,
        "freshness_or_traction_signals": signals,
        "thesis_fit_reasons": reasons,
        "rank": 0,
    }


def normalize_candidates(records: list[dict]) -> tuple[list[dict], list[dict]]:
    """Validate, deduplicate, and rank Product Hunt/YC source records deterministically."""
    accepted = []
    excluded = []
    for record in records:
        reason = _record_reason(record)
        if reason:
            excluded.append({
                "name": record.get("name") if isinstance(record, dict) else None,
                "reason": reason,
                "origins": copy.deepcopy(record.get("origins", [])) if isinstance(record, dict) else [],
            })
        else:
            accepted.append(copy.deepcopy(record))
    groups: list[list[dict]] = []
    for record in sorted(accepted, key=_record_key):
        matching_group = next((group for group in groups if _record_matches_group(record, group)), None)
        if matching_group is None:
            groups.append([record])
        else:
            matching_group.append(record)
    candidates = []
    for group in groups:
        candidate = _merge_records(group)
        if candidate["website"]:
            candidates.append(candidate)
        else:
            excluded.append({
                "name": candidate.get("name"),
                "reason": "missing required candidate field",
                "origins": candidate["origins"],
            })
    candidates.sort(key=lambda candidate: (_normalized_name(candidate["name"]), candidate["slug"], candidate["website"]))
    for rank, candidate in enumerate(candidates, start=1):
        candidate["rank"] = rank
    return candidates, excluded


def _show_hn_name(title: Any) -> str:
    match = re.match(r"\s*show\s+hn\s*:\s*(.*)", str(title or ""), re.IGNORECASE)
    if not match:
        return ""
    return re.split(r"\s+[\-–—]\s+", match.group(1), maxsplit=1)[0].strip()


def _hn_url(item: dict) -> str:
    return f"https://news.ycombinator.com/item?id={item['id']}"


def _hn_signals(item: dict) -> list[dict]:
    published = item.get("time")
    date = None
    if isinstance(published, (int, float)):
        date = datetime.fromtimestamp(published, timezone.utc).isoformat().replace("+00:00", "Z")
    source_url = _hn_url(item)
    return [
        {"kind": "freshness", "source_url": source_url, "date": date},
        {
            "kind": "traction",
            "source_url": source_url,
            "score": item.get("score", 0),
            "comments": item.get("descendants", 0),
        },
    ]


def enrich_with_hacker_news(candidates: list[dict], items: list[dict]) -> list[dict]:
    """Add Show HN signals without turning Hacker News into an origin source."""
    stories = [
        item for item in items
        if isinstance(item, dict)
        and item.get("type") == "story"
        and item.get("id") is not None
        and _show_hn_name(item.get("title"))
    ]
    enriched = copy.deepcopy(candidates)
    for candidate in enriched:
        domain = _domain(candidate.get("website"))
        domain_matches = [item for item in stories if domain and _domain(item.get("url")) == domain]
        matches = domain_matches or [
            item for item in stories
            if _normalized_name(_show_hn_name(item.get("title"))) == _normalized_name(candidate.get("name"))
        ]
        signals = list(candidate.get("freshness_or_traction_signals", []))
        for item in sorted(matches, key=lambda item: int(item["id"])):
            signals.extend(_hn_signals(item))
        candidate["freshness_or_traction_signals"] = _unique_sorted(signals, _signal_sort_key)
    return enriched
