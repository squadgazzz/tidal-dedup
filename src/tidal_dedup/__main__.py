import argparse
import asyncio
import re
import sys

from tidal_dedup.auth import open_tidal_session
from tidal_dedup.dedup import fetch_stream_info_if_needed, resolve_duplicates
from tidal_dedup.detection import find_duplicates
from tidal_dedup.display import (
    confirm_proceed,
    print_duplicate_group,
    print_summary,
    prompt_interactive,
)
from tidal_dedup.tidal_api import (
    get_all_favorites,
    get_all_playlist_tracks,
    get_all_playlists,
    remove_favorites,
    remove_indices_from_playlist,
)


def parse_playlist_id(value: str) -> str:
    """Extract playlist UUID from a URL or raw ID."""
    match = re.search(r"playlist/([a-f0-9-]+)", value, re.IGNORECASE)
    if match:
        return match.group(1)
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tidal-dedup",
        description="Remove duplicate tracks from Tidal playlists or favorites.",
    )
    parser.add_argument(
        "playlist",
        nargs="?",
        default=None,
        help="Playlist ID or URL to deduplicate. If omitted, deduplicates favorites.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        dest="all_playlists",
        help="Deduplicate all user playlists.",
    )

    # Detection strategies
    strategy_group = parser.add_argument_group("detection strategies (combine any; default: --by-name)")
    strategy_group.add_argument("--by-id", action="store_true", help="Match by exact Tidal track ID")
    strategy_group.add_argument("--by-isrc", action="store_true", help="Match by ISRC code")
    strategy_group.add_argument("--by-name", action="store_true", help="Match by name + artist + duration (default)")

    # Resolution
    parser.add_argument(
        "--keep",
        choices=["oldest", "newest", "best-quality"],
        default="best-quality",
        help="Which duplicate to keep (default: best-quality).",
    )

    # Execution mode
    parser.add_argument(
        "--mode",
        choices=["auto", "review", "interactive"],
        default="review",
        help="Execution mode (default: review).",
    )
    return parser


def get_strategies(args) -> list[str]:
    strategies = []
    if args.by_id:
        strategies.append("id")
    if args.by_isrc:
        strategies.append("isrc")
    if args.by_name:
        strategies.append("name")
    return strategies  # empty list defaults to ["id"] in find_duplicates


def process_tracks(tracks, args, remove_fn):
    """Core dedup logic: detect, resolve, display, remove."""
    print(f"Fetched {len(tracks)} track(s).")
    strategies = get_strategies(args)
    groups = find_duplicates(tracks, strategies)

    if not groups:
        print("No duplicates found.")
        return

    # Fetch stream info for groups where quality tier is the same, then resolve
    resolved = []
    for group in groups:
        stream_info = fetch_stream_info_if_needed(group)
        keep_idx, remove_indices = resolve_duplicates(group, strategy=args.keep, stream_info=stream_info)
        resolved.append((group, keep_idx, remove_indices, stream_info))

    if args.mode == "auto":
        print_summary(resolved)
        all_remove = []
        for _, _, remove_indices, _ in resolved:
            all_remove.extend(remove_indices)
        remove_fn(all_remove)
        print(f"Removed {len(all_remove)} duplicate track(s).")

    elif args.mode == "review":
        print_summary(resolved)
        if not confirm_proceed():
            print("Aborted.")
            return
        all_remove = []
        for _, _, remove_indices, _ in resolved:
            all_remove.extend(remove_indices)
        remove_fn(all_remove)
        print(f"Removed {len(all_remove)} duplicate track(s).")

    elif args.mode == "interactive":
        total_removed = 0
        for group, keep_idx, remove_indices, stream_info in resolved:
            action = prompt_interactive(group, keep_idx, remove_indices, stream_info)
            if action == "keep":
                remove_fn(remove_indices)
                total_removed += len(remove_indices)
            elif action == "quit":
                print(f"Stopped. Removed {total_removed} track(s) so far.")
                return
            # "skip" just continues
        print(f"Done. Removed {total_removed} duplicate track(s).")


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.playlist and args.all_playlists:
        parser.error("Cannot specify both a playlist and --all")

    print("Opening Tidal session...")
    session = open_tidal_session()
    if not session.check_login():
        sys.exit("Could not connect to Tidal")
    print("Connected to Tidal.")

    if args.all_playlists:
        playlists = asyncio.run(get_all_playlists(session))
        print(f"Found {len(playlists)} playlist(s)")
        for playlist in playlists:
            print(f"\nProcessing playlist: '{playlist.name}'")
            tracks = asyncio.run(get_all_playlist_tracks(playlist))
            process_tracks(
                tracks,
                args,
                remove_fn=lambda indices, p=playlist: remove_indices_from_playlist(p, indices),
            )

    elif args.playlist:
        playlist_id = parse_playlist_id(args.playlist)
        playlist = session.playlist(playlist_id)
        print(f"Processing playlist: '{playlist.name}'")
        tracks = asyncio.run(get_all_playlist_tracks(playlist))
        process_tracks(
            tracks,
            args,
            remove_fn=lambda indices: remove_indices_from_playlist(playlist, indices),
        )

    else:
        print("Processing favorites...")
        tracks = asyncio.run(get_all_favorites(session))
        # For favorites, removal is by track ID, not index
        track_by_index = {i: t for i, t in enumerate(tracks)}
        process_tracks(
            tracks,
            args,
            remove_fn=lambda indices: remove_favorites(
                session, [track_by_index[i].id for i in indices]
            ),
        )


if __name__ == "__main__":
    main()
