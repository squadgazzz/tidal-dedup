import re
from collections import defaultdict
from typing import List, Sequence, Tuple
import unicodedata

import tidalapi

# A DuplicateGroup is a list of (original_index, track) tuples
DuplicateGroup = List[Tuple[int, tidalapi.Track]]


def _normalize(s: str) -> str:
    return unicodedata.normalize("NFC", s).casefold().strip()


def _full_name(track: tidalapi.Track) -> str:
    """Return title with version included, matching tidalapi's full_name."""
    return track.full_name or track.name


def group_by_id(tracks: Sequence[tidalapi.Track]) -> List[DuplicateGroup]:
    """Group tracks that share the same Tidal track ID."""
    buckets: dict[int, DuplicateGroup] = defaultdict(list)
    for idx, track in enumerate(tracks):
        buckets[track.id].append((idx, track))
    return [group for group in buckets.values() if len(group) >= 2]


def _same_artist(a: tidalapi.Track, b: tidalapi.Track) -> bool:
    """Check if two tracks share at least one artist."""
    artists_a = {_normalize(artist.name) for artist in a.artists} if a.artists else set()
    artists_b = {_normalize(artist.name) for artist in b.artists} if b.artists else set()
    return bool(artists_a & artists_b)


def group_by_isrc(tracks: Sequence[tidalapi.Track]) -> List[DuplicateGroup]:
    """Group tracks that share the same ISRC code.

    As a sanity check, tracks with the same ISRC must also share at least one
    artist — Tidal sometimes assigns the same ISRC to unrelated tracks.
    """
    buckets: dict[str, DuplicateGroup] = defaultdict(list)
    for idx, track in enumerate(tracks):
        if track.isrc:
            buckets[track.isrc].append((idx, track))

    result = []
    for group in buckets.values():
        if len(group) < 2:
            continue
        # Sub-group by artist overlap to avoid false matches from bad ISRC data
        verified: DuplicateGroup = [group[0]]
        for idx, track in group[1:]:
            if _same_artist(group[0][1], track):
                verified.append((idx, track))
        if len(verified) >= 2:
            result.append(verified)
    return result


def group_by_name(tracks: Sequence[tidalapi.Track]) -> List[DuplicateGroup]:
    """Group tracks that share the same full name (title + version) and artist."""
    def _track_key(track: tidalapi.Track) -> str:
        artist = _normalize(track.artists[0].name) if track.artists else ""
        return f"{_normalize(_full_name(track))}|{artist}"

    buckets: dict[str, DuplicateGroup] = defaultdict(list)
    for idx, track in enumerate(tracks):
        buckets[_track_key(track)].append((idx, track))

    return [group for group in buckets.values() if len(group) >= 2]


_REMASTER_PATTERNS = [
    re.compile(r"[\(\[]\s*remaster(?:ed)?\s*(?:\d{4})?\s*[\)\]]", re.IGNORECASE),
    re.compile(r"[\(\[]\s*\d{4}\s+remaster(?:ed)?\s*[\)\]]", re.IGNORECASE),
    re.compile(r"[\(\[].*remaster(?:ed)?.*[\)\]]", re.IGNORECASE),
    re.compile(r"\s-\s+remaster(?:ed)?\s*(?:\d{4})?$", re.IGNORECASE),
    re.compile(r"\s-\s+\d{4}\s+remaster(?:ed)?$", re.IGNORECASE),
]

_REMASTER_VERSION_RE = re.compile(r"remaster(?:ed)?", re.IGNORECASE)


def strip_remaster_tags(title: str) -> str:
    """Remove remaster-related tags from a track title."""
    result = title
    for pattern in _REMASTER_PATTERNS:
        result = pattern.sub("", result)
    return result.strip()


def _is_remaster_version(version: str | None) -> bool:
    """Check if a version string indicates a remaster."""
    if not version:
        return False
    return bool(_REMASTER_VERSION_RE.search(version))


def is_remastered(track: tidalapi.Track) -> bool:
    """Check if a track is a remastered version."""
    if _is_remaster_version(track.version):
        return True
    return any(p.search(track.name) for p in _REMASTER_PATTERNS)


def group_by_remaster(tracks: Sequence[tidalapi.Track]) -> List[DuplicateGroup]:
    """Group tracks that are remastered versions of the same song.

    Strips remaster tags from titles before comparing. If the version field
    is a remaster tag, it's excluded from the grouping key. Non-remaster
    versions (e.g., "Instrumental") are kept in the key.
    """
    def _track_key(track: tidalapi.Track) -> str:
        title = _normalize(strip_remaster_tags(track.name))
        version = _normalize(track.version) if track.version and not _is_remaster_version(track.version) else ""
        artist = _normalize(track.artists[0].name) if track.artists else ""
        return f"{title}|{version}|{artist}"

    buckets: dict[str, DuplicateGroup] = defaultdict(list)
    for idx, track in enumerate(tracks):
        buckets[_track_key(track)].append((idx, track))

    result = []
    for group in buckets.values():
        if len(group) < 2:
            continue
        # Only include groups where at least one track has a remaster tag
        if not any(is_remastered(track) for _, track in group):
            continue
        # Verify artist overlap
        verified: DuplicateGroup = [group[0]]
        for idx, track in group[1:]:
            if _same_artist(group[0][1], track):
                verified.append((idx, track))
        if len(verified) >= 2:
            result.append(verified)
    return result


STRATEGY_MAP = {
    "id": group_by_id,
    "isrc": group_by_isrc,
    "name": group_by_name,
    "remaster": group_by_remaster,
}


def find_duplicates(tracks: Sequence[tidalapi.Track], strategies: List[str]) -> List[DuplicateGroup]:
    """Find all duplicate groups using the union of the given strategies."""
    if not strategies:
        strategies = ["name"]

    seen_groups: set[frozenset[int]] = set()
    result: List[DuplicateGroup] = []

    for strategy_name in strategies:
        func = STRATEGY_MAP.get(strategy_name, STRATEGY_MAP["id"])
        for group in func(tracks):
            key = frozenset(idx for idx, _ in group)
            if key not in seen_groups:
                seen_groups.add(key)
                result.append(group)

    return result
