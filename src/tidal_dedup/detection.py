from collections import defaultdict
from typing import List, Sequence, Tuple
import unicodedata

import tidalapi

# A DuplicateGroup is a list of (original_index, track) tuples
DuplicateGroup = List[Tuple[int, tidalapi.Track]]


def _normalize(s: str) -> str:
    return unicodedata.normalize("NFC", s).casefold().strip()


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


def group_by_name(tracks: Sequence[tidalapi.Track], duration_tolerance: int = 2) -> List[DuplicateGroup]:
    """Group tracks that share the same normalized name + artist within duration tolerance."""
    def _track_key(track: tidalapi.Track) -> str:
        artist = _normalize(track.artists[0].name) if track.artists else ""
        return f"{_normalize(track.name)}|{artist}"

    buckets: dict[str, DuplicateGroup] = defaultdict(list)
    for idx, track in enumerate(tracks):
        buckets[_track_key(track)].append((idx, track))

    result = []
    for group in buckets.values():
        if len(group) < 2:
            continue
        # Within a name-match group, further filter by duration tolerance.
        duration_clusters: dict[int, DuplicateGroup] = defaultdict(list)
        for idx, track in group:
            placed = False
            for anchor_dur in duration_clusters:
                if abs(track.duration - anchor_dur) <= duration_tolerance:
                    duration_clusters[anchor_dur].append((idx, track))
                    placed = True
                    break
            if not placed:
                duration_clusters[track.duration].append((idx, track))
        for cluster in duration_clusters.values():
            if len(cluster) >= 2:
                result.append(cluster)
    return result


STRATEGY_MAP = {
    "id": group_by_id,
    "isrc": group_by_isrc,
    "name": group_by_name,
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
