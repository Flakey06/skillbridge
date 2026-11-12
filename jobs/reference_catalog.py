import ast
import csv
import re
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

from django.conf import settings


_STOP_WORDS = {
    "and",
    "at",
    "for",
    "in",
    "of",
    "or",
    "the",
    "to",
    "with",
}
_TITLE_ALIASES = {
    "hr": "human resources",
    "sr": "senior",
    "mgr": "manager",
    "dev": "developer",
    "analyst": "analyst",
}


def _normalise_title(value):
    value = str(value or "").casefold()
    value = re.sub(r"\b(ii|iii|iv|i)\b", " ", value)
    for abbreviation, replacement in _TITLE_ALIASES.items():
        value = re.sub(rf"\b{re.escape(abbreviation)}\b", replacement, value)
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def _title_tokens(value):
    return {
        token
        for token in _normalise_title(value).split()
        if token not in _STOP_WORDS and len(token) > 1
    }


def _title_score(query, reference):
    query_normalised = _normalise_title(query)
    reference_normalised = _normalise_title(reference)
    if not query_normalised or not reference_normalised:
        return 0.0
    if query_normalised == reference_normalised:
        return 1.0
    query_tokens = _title_tokens(query)
    reference_tokens = _title_tokens(reference)
    overlap = len(query_tokens & reference_tokens) / max(len(query_tokens | reference_tokens), 1)
    sequence = SequenceMatcher(None, query_normalised, reference_normalised).ratio()
    return round((overlap * 0.7) + (sequence * 0.3), 4)


def _catalog_path():
    return Path(getattr(settings, "JOB_REFERENCE_CSV", settings.BASE_DIR / "data" / "all_job_post.csv"))


@lru_cache(maxsize=1)
def _load_catalogue(path):
    records = []
    with path.open(newline="", encoding="utf-8-sig") as file:
        for row in csv.DictReader(file):
            title = (row.get("job_title") or "").strip()
            if not title:
                continue
            try:
                skills = ast.literal_eval(row.get("job_skill_set") or "[]")
            except (SyntaxError, ValueError) as error:
                raise ValueError(f"Invalid skill list for reference job {row.get('job_id', title)}") from error
            if not isinstance(skills, list):
                raise ValueError(f"Skill list is not a list for reference job {row.get('job_id', title)}")
            records.append({
                "title": title,
                "category": (row.get("category") or "").strip(),
                "skills": [str(skill).strip() for skill in skills if str(skill).strip()],
            })
    return tuple(records)


def suggest_skills_for_title(title, limit=3):
    title = title.strip()
    if not title:
        return []
    records = _load_catalogue(_catalog_path())
    ranked = sorted(
        (
            (score, record)
            for record in records
            if (score := _title_score(title, record["title"])) >= 0.35
        ),
        key=lambda item: (-item[0], item[1]["title"]),
    )
    suggestions = []
    seen_titles = set()
    for score, record in ranked:
        if record["title"] in seen_titles:
            continue
        seen_titles.add(record["title"])
        confidence = "high" if score >= 0.75 else "medium"
        suggestions.append({
            "title": record["title"],
            "category": record["category"],
            "score": round(score * 100),
            "confidence": confidence,
            "skills": list(dict.fromkeys(record["skills"])),
        })
        if len(suggestions) == limit:
            break
    return suggestions
