from typing import Dict, List, Tuple
from tidal_dedup.detection import DuplicateGroup

QUALITY_RANK = {"LOW": 0, "HIGH": 1, "LOSSLESS": 2, "HI_RES_LOSSLESS": 3}

# StreamInfo maps playlist index -> (bit_depth, sample_rate)
StreamInfo = Dict[int, Tuple[int, int]]


def get_stream_quality(track) -> Tuple[int, int]:
    """Fetch bit_depth and sample_rate from the track's stream.

    Returns (bit_depth, sample_rate), or (0, 0) if the stream can't be fetched.
    """
    try:
        stream = track.get_stream()
        return (stream.bit_depth or 0, stream.sample_rate or 0)
    except Exception:
        return (0, 0)


def fetch_stream_info_if_needed(group: DuplicateGroup) -> StreamInfo:
    """Fetch stream metadata for a group if all tracks share the same quality tier."""
    qualities = {track.audio_quality for _, track in group}
    if len(qualities) != 1:
        return {}
    print(f"    Fetching stream metadata for {len(group)} tracks with same quality tier...")
    result = {}
    for idx, track in group:
        result[idx] = get_stream_quality(track)
    return result


def resolve_duplicates(group: DuplicateGroup, strategy: str = "oldest",
                       stream_info: StreamInfo | None = None) -> Tuple[int, List[int]]:
    """Given a duplicate group, decide which to keep and which to remove.

    Returns (keep_index, [remove_indices]) where indices are original playlist positions.
    """
    if strategy == "oldest":
        sorted_group = sorted(group, key=lambda item: item[0])
    elif strategy == "newest":
        sorted_group = sorted(group, key=lambda item: item[0], reverse=True)
    elif strategy == "best-quality":
        si = stream_info or {}
        sorted_group = sorted(
            group,
            key=lambda item: (
                QUALITY_RANK.get(item[1].audio_quality, -1),
                si.get(item[0], (0, 0))[0],  # bit_depth
                si.get(item[0], (0, 0))[1],  # sample_rate
                -item[0],
            ),
            reverse=True,
        )
    else:
        raise ValueError(f"Unknown resolution strategy: {strategy}")

    keep = sorted_group[0]
    remove = sorted_group[1:]
    return keep[0], sorted(idx for idx, _ in remove)
