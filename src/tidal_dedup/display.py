# src/tidal_dedup/display.py
from typing import Dict, List, Tuple

import tidalapi

from tidal_dedup.detection import DuplicateGroup
from tidal_dedup.dedup import StreamInfo


def format_track(track: tidalapi.Track, stream_info: Tuple[int, int] | None = None) -> str:
    """Format a track for display."""
    artists = ", ".join(a.name for a in track.artists) if track.artists else "Unknown"
    quality = track.audio_quality or "?"
    mins, secs = divmod(track.duration, 60)
    base = f"{track.name} — {artists} [{quality}] ({mins}:{secs:02d})"
    if stream_info:
        bit_depth, sample_rate = stream_info
        if bit_depth or sample_rate:
            base += f" {bit_depth}bit/{sample_rate}Hz"
    return base


def print_duplicate_group(group: DuplicateGroup, keep_idx: int, remove_indices: List[int],
                          stream_info: StreamInfo | None = None):
    """Print a duplicate group showing which track is kept and which are removed."""
    si = stream_info or {}
    print(f"\n  Duplicate group ({len(group)} tracks):")
    for idx, track in group:
        marker = "  KEEP  " if idx == keep_idx else "  REMOVE"
        print(f"    [{marker}] #{idx}: {format_track(track, si.get(idx))}")


def print_summary(groups: List[Tuple[DuplicateGroup, int, List[int], StreamInfo]]):
    """Print a full summary of all planned changes."""
    total_remove = sum(len(remove) for _, _, remove, _ in groups)
    print(f"\n{'='*60}")
    print(f"Deduplication Summary: {len(groups)} duplicate group(s), {total_remove} track(s) to remove")
    print(f"{'='*60}")
    for group, keep_idx, remove_indices, stream_info in groups:
        print_duplicate_group(group, keep_idx, remove_indices, stream_info)
    print(f"\n{'='*60}")
    print(f"Total: {total_remove} track(s) will be removed")
    print(f"{'='*60}")


def confirm_proceed() -> bool:
    """Ask the user to confirm the planned changes."""
    response = input("\nProceed with removal? [y/N]: ").strip().lower()
    return response in ("y", "yes")


def prompt_interactive(group: DuplicateGroup, keep_idx: int, remove_indices: List[int],
                       stream_info: StreamInfo | None = None) -> str:
    """Prompt for a single duplicate group in interactive mode.

    Returns: 'keep' to apply removal, 'skip' to skip, 'quit' to abort.
    """
    print_duplicate_group(group, keep_idx, remove_indices, stream_info)
    while True:
        response = input("  Action — [k]eep plan / [s]kip / [q]uit: ").strip().lower()
        if response in ("k", "keep"):
            return "keep"
        elif response in ("s", "skip"):
            return "skip"
        elif response in ("q", "quit"):
            return "quit"
        print("  Invalid input. Enter k, s, or q.")
