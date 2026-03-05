# src/tidal_dedup/tidal_api.py
import asyncio
import math
from typing import List

import tidalapi

from tidal_dedup.retry import retry_on_rate_limit


def remove_indices_from_playlist(playlist, indices: List[int]):
    """Remove tracks at the given indices from a Tidal playlist.

    Sorts indices descending internally to avoid shifting issues.
    """
    if not indices:
        return
    sorted_indices = sorted(indices, reverse=True)
    headers = {"If-None-Match": getattr(playlist, '_etag', None)}
    if not headers["If-None-Match"]:
        headers = None
    index_string = ",".join(map(str, sorted_indices))
    print(f"Removing {len(sorted_indices)} track(s) from playlist...")
    playlist.request.request(
        "DELETE",
        (playlist._base_url + "/items/%s") % (playlist.id, index_string),
        headers=headers,
    )
    if hasattr(playlist, '_reparse'):
        playlist._reparse()
    print("Done.")


def remove_favorites(session: tidalapi.Session, track_ids: List[int]):
    """Remove tracks from Tidal favorites."""
    for track_id in track_ids:
        session.user.favorites.remove_track(track_id)


MAX_CONCURRENT_REQUESTS = 5


async def _get_all_chunks(url, session, parser, params=None) -> list:
    """Fetch all items from a paginated Tidal endpoint with limited concurrency."""
    if params is None:
        params = {}
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

    def _make_request(offset: int = 0):
        req_params = {**params, "offset": offset}
        return session.request.map_request(url, params=req_params)

    first_chunk = await asyncio.to_thread(_make_request)
    limit = first_chunk["limit"]
    total = first_chunk["totalNumberOfItems"]
    items = session.request.map_json(first_chunk, parse=parser)

    if len(items) < total:
        offsets = [limit * n for n in range(1, math.ceil(total / limit))]

        async def _fetch_chunk(offset):
            async with semaphore:
                return await retry_on_rate_limit(
                    asyncio.to_thread,
                    lambda o=offset: session.request.map_json(
                        _make_request(o), parse=parser
                    ),
                )

        extra = await asyncio.gather(*[_fetch_chunk(o) for o in offsets])
        for chunk in extra:
            items.extend(chunk)
    return items


async def get_all_playlist_tracks(playlist: tidalapi.Playlist) -> List[tidalapi.Track]:
    """Fetch all tracks from a Tidal playlist."""
    params = {"limit": 20}
    print(f"Loading tracks from Tidal playlist '{playlist.name}'")
    return await _get_all_chunks(
        f"{playlist._base_url % playlist.id}/tracks",
        session=playlist.session,
        parser=playlist.session.parse_track,
        params=params,
    )


async def get_all_favorites(session: tidalapi.Session) -> List[tidalapi.Track]:
    """Fetch all favorite tracks."""
    favorites = session.user.favorites
    params = {"limit": 100, "order": "DATE", "orderDirection": "ASC"}
    print("Loading favorite tracks from Tidal")
    return await _get_all_chunks(
        f"{favorites.base_url}/tracks",
        session=favorites.session,
        parser=favorites.session.parse_track,
        params=params,
    )


async def get_all_playlists(session: tidalapi.Session) -> List[tidalapi.Playlist]:
    """Fetch all user playlists."""
    user = session.user
    params = {"limit": 10}
    print("Loading playlists from Tidal")
    return await _get_all_chunks(
        f"users/{user.id}/playlists",
        session=user.session,
        parser=user.playlist.parse_factory,
        params=params,
    )
