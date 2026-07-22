"""
lab_query.py
============
Natural-language query engine over parsed LabRecord data (see
lab_parser.py). Answers questions like:

    "Benzene Product 7 July M"
    "DSN 5 July"                (no shift -> all shifts returned)
    "PX-1 Reformate night"
    "pta"                       (returns ALL PTA samples across all hours)
    "601"                       (matches C-601 Btm AND C-601 Reflux)
    "601 btm"                   (narrows to C-601 Btm exactly)
    "dec7 oh"                   (matches DeC7 O/H via synonym)

by resolving the sample name, date, and (optional) shift from the query
text, then returning every reported parameter for the matching row(s) as a
clean table: parameter | unit | value.

Shift codes: M = Morning, E = Evening, N = Night.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass

from lab_parser import LabRecord

MONTH_NAMES = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
MONTH_NAMES.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})

SHIFT_WORDS = {
    "m": "M", "morning": "M",
    "e": "E", "evening": "E",
    "n": "N", "night": "N",
}

# Longest-match-first date patterns.
_DATE_PATTERNS = [
    # "7 July 2026", "07 July", "7th July"
    re.compile(
        r"\b(?P<day>\d{1,2})(?:st|nd|rd|th)?\s+(?P<month>[A-Za-z]+)\.?\s*(?P<year>\d{4})?\b"
    ),
    # "July 7", "July 7th"
    re.compile(
        r"\b(?P<month>[A-Za-z]+)\.?\s+(?P<day>\d{1,2})(?:st|nd|rd|th)?\s*(?P<year>\d{4})?\b"
    ),
    # "07.07.2026", "07-07-2026", "07/07/2026"
    re.compile(r"\b(?P<day>\d{1,2})[./-](?P<month_num>\d{1,2})[./-](?P<year>\d{4})\b"),
]


@dataclass
class ParsedQuery:
    sample_hint: str | None
    day: int | None
    month: int | None
    year: int | None
    shift: str | None
    raw_query: str


def _extract_date(query: str) -> tuple[int | None, int | None, int | None, str]:
    """Return (day, month, year, remaining_query_with_date_removed)."""
    for pattern in _DATE_PATTERNS:
        match = pattern.search(query)
        if not match:
            continue
        groups = match.groupdict()
        day = int(groups["day"]) if groups.get("day") else None
        year = int(groups["year"]) if groups.get("year") else None
        if "month_num" in groups and groups["month_num"]:
            month = int(groups["month_num"])
        else:
            month_str = (groups.get("month") or "").lower()
            month = MONTH_NAMES.get(month_str)
        if day and month:
            remaining = query[: match.start()] + " " + query[match.end() :]
            return day, month, year, remaining
    return None, None, None, query


def _extract_shift(query: str) -> tuple[str | None, str]:
    """Return (shift_code_or_None, remaining_query_with_shift_removed).

    Only strips a shift word when it stands alone as a whitespace-separated
    word (or at the very start/end of the query) - NOT merely at a regex
    "word boundary", which would also match punctuation like the 'E' in
    "E-7" or the 'M' in "PTA(M-1423)Comp" (both real sample names in this
    data set). Real shift mentions in practice are always space-separated
    from the rest of the query (e.g. "...July M", "...July night"), so this
    is a safe, tighter requirement that avoids corrupting sample-name hints
    that merely happen to contain a shift letter as part of a longer token.
    """
    tokens = re.findall(r"[A-Za-z]+", query)
    for tok in tokens:
        low = tok.lower()
        if low in SHIFT_WORDS and len(tok) <= len("morning"):
            pattern = re.compile(rf"(?:(?<=\s)|^){re.escape(tok)}(?=\s|$)")
            if pattern.search(query):
                remaining = pattern.sub(" ", query, count=1)
                return SHIFT_WORDS[low], remaining
    return None, query


def parse_query(query: str) -> ParsedQuery:
    day, month, year, remaining = _extract_date(query)
    shift, remaining = _extract_shift(remaining)
    sample_hint = re.sub(r"\s+", " ", remaining).strip(" ,.-") or None
    return ParsedQuery(sample_hint, day, month, year, shift, query)


# Synonym groups for common refinery-jargon abbreviations, so a query using
# any variant of a word matches sample names using any other variant.
# Add new groups here as new abbreviation patterns are discovered - do not
# scatter ad-hoc string replacements elsewhere in this module.
_SAMPLE_SYNONYMS = {
    "btm": "bottom", "bot": "bottom", "bott": "bottom", "bottom": "bottom",
    "oh": "oh", "ovhd": "oh", "ovhead": "oh", "overhead": "oh",
    "reflx": "reflux", "reflux": "reflux",
    "recv": "receiver", "receive": "receiver", "receiver": "receiver",
}

# Matches "O/H", "o / h", "O /H" etc. so it can be canonicalized to the
# single token "oh" - the same token that a user typing "oh" produces -
# BEFORE generic punctuation stripping would otherwise split it into two
# separate single-letter tokens ("o", "h") that could spuriously match
# all sorts of unrelated samples.
_OH_SLASH_PATTERN = re.compile(r"\bo\s*/\s*h\b", re.IGNORECASE)


def _normalize_to_tokens(text: str) -> set[str]:
    """Normalize a sample name or a user's free-text hint into a
    comparable set of tokens, so that punctuation (-, /, ., (), :),
    casing, and known abbreviations never prevent a match.

    Examples:
        "C-601 Btm"        -> {"c", "601", "bottom"}
        "601"              -> {"601"}
        "601 bottom"       -> {"601", "bottom"}
        "DeC7 O/H"         -> {"dec7", "oh"}
        "oh"               -> {"oh"}
        "PTA  07:30 Hrs"   -> {"pta", "07", "30", "hrs"}
    """
    text = _OH_SLASH_PATTERN.sub("oh", text.lower())
    text = re.sub(r"[^a-z0-9]+", " ", text)
    # Split letter/digit boundaries so a concatenated form like "c601"
    # tokenizes identically to the separated "C-601" (-> "c", "601"),
    # rather than becoming one unmatched compound token.
    text = re.sub(r"(?<=[a-z])(?=[0-9])", " ", text)
    text = re.sub(r"(?<=[0-9])(?=[a-z])", " ", text)
    tokens = (_SAMPLE_SYNONYMS.get(tok, tok) for tok in text.split())
    return {tok for tok in tokens if tok}


def _best_sample_match(sample_hint: str | None, known_samples: list[str]) -> list[str]:
    """Return the known sample name(s) matching the free-text hint.

    Uses tokenized, punctuation- and abbreviation-insensitive matching so
    informal queries work naturally:
      - Separators (-, /, ., (), :) never block a match: "601" matches
        "C-601 Btm".
      - A single word from a multi-word sample name is enough: "pta"
        matches every "PTA <time> Hrs" sample (all of them are returned,
        by design).
      - Known abbreviation variants are treated as identical: "btm" /
        "bott" / "bottom" all match each other; "oh" matches "O/H".

    Three tiers, most precise first:
      1. Exact token-set equality.
      2. Hint tokens fully contained within a sample's tokens (all
         qualifying samples returned, not narrowed to one).
      3. Best-effort partial token overlap for typos / partial hints.
    """
    if not sample_hint:
        return []
    hint_tokens = _normalize_to_tokens(sample_hint)
    if not hint_tokens:
        return []

    sample_tokens = {s: _normalize_to_tokens(s) for s in known_samples}

    # Tier 1: exact token-set equality.
    exact = [s for s, toks in sample_tokens.items() if toks == hint_tokens]
    if exact:
        return sorted(exact)

    # Tier 2: hint tokens are a subset of the sample's tokens.
    contains = [s for s, toks in sample_tokens.items() if hint_tokens <= toks]
    if contains:
        return sorted(contains)

    # Tier 3: partial overlap fallback.
    scored = [
        (len(hint_tokens & toks), s)
        for s, toks in sample_tokens.items()
        if hint_tokens & toks
    ]
    if scored:
        scored.sort(reverse=True)
        top_score = scored[0][0]
        return sorted(s for score, s in scored if score == top_score)

    return []


def _date_matches(record_date: str, day: int | None, month: int | None, year: int | None) -> bool:
    if day is None or month is None:
        return True  # no date filter -> match all dates
    try:
        d_part, m_part, y_part = record_date.split(".")
        rd, rm, ry = int(d_part), int(m_part), int(y_part)
    except (ValueError, AttributeError):
        return False
    if rd != day or rm != month:
        return False
    if year is not None and ry != year:
        return False
    return True


def query_records(
    query: str, records: list[LabRecord]
) -> tuple[list[LabRecord], ParsedQuery, list[str]]:
    """Resolve a natural-language query against parsed lab records.

    Returns (matching_records, parsed_query, warnings).
    """
    parsed = parse_query(query)
    warnings: list[str] = []

    known_samples = sorted({r.sample for r in records})
    matched_samples = _best_sample_match(parsed.sample_hint, known_samples)

    if parsed.sample_hint and not matched_samples:
        warnings.append(
            f"No sample name matching '{parsed.sample_hint}' was found in the "
            f"loaded lab reports."
        )
        return [], parsed, warnings

    if len(matched_samples) > 1:
        preview = matched_samples[:8]
        suffix = f", and {len(matched_samples) - 8} more" if len(matched_samples) > 8 else ""
        warnings.append(
            f"'{parsed.sample_hint}' matched {len(matched_samples)} samples: "
            f"{', '.join(preview)}{suffix}. Showing results for all of them."
        )

    results = [
        r
        for r in records
        if (not matched_samples or r.sample in matched_samples)
        and _date_matches(r.date, parsed.day, parsed.month, parsed.year)
        and (parsed.shift is None or r.shift.upper() == parsed.shift)
    ]

    if not results:
        warnings.append(
            "No matching lab records were found for the given sample/date/shift "
            "combination. Please check the sample name, date, or shift and try again."
        )

    return results, parsed, warnings


SHIFT_FULL_NAME = {"M": "Morning", "E": "Evening", "N": "Night"}


def format_records_as_tables(results: list[LabRecord]) -> str:
    """Render matching LabRecords as markdown tables."""
    if not results:
        return "No data found."

    blocks = []
    for r in results:
        shift_name = SHIFT_FULL_NAME.get(r.shift.upper(), r.shift)
        header = (
            f"**{r.sample}** — {r.date} — {shift_name} shift "
            f"({r.material}, source: {r.source_file})"
        )
        if not r.values:
            blocks.append(f"{header}\n\n_No parameters were reported for this row._")
            continue
        lines = [header, "", "| Parameter | Unit | Value |", "|---|---|---|"]
        for param, (unit, value) in r.values.items():
            lines.append(f"| {param} | {unit} | {value} |")
        blocks.append("\n".join(lines))

    return "\n\n---\n\n".join(blocks)
