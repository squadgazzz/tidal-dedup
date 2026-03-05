# Tidal Dedup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Python CLI tool that finds and removes duplicate tracks from Tidal playlists or favorites, with configurable detection strategies, resolution strategies, and execution modes.

**Architecture:** A standalone Python package at `../tidal-dedup/` with CLI entry point. Detection strategies are composable functions that group tracks into duplicate sets. A resolution strategy picks which track to keep from each group. Three execution modes control user interaction (auto/review/interactive). All Tidal API calls go through a retry wrapper with escalating backoff.

**Tech Stack:** Python 3.10+, tidalapi 0.8.8, pyyaml, pytest, pytest-mock

---

### Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `src/tidal_dedup/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/unit/__init__.py`
- Create: `tests/conftest.py`
- Create: `pytest.ini`

**Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["setuptools >= 61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "tidal-dedup"
version = "0.1.0"
requires-python = ">= 3.10"

dependencies = [
  "tidalapi==0.8.8",
  "pyyaml~=6.0",
  "requests>=2.20",
  "pytest~=8.0",
  "pytest-mock~=3.8"
]

[tool.setuptools.packages.find]
where = ["src"]

[project.scripts]
tidal-dedup = "tidal_dedup.__main__:main"
```

**Step 2: Create empty `__init__.py` files**

- `src/tidal_dedup/__init__.py` — empty
- `tests/__init__.py` — empty
- `tests/unit/__init__.py` — empty

**Step 3: Create `tests/conftest.py`**

```python
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))
```

**Step 4: Create `pytest.ini`**

```ini
[pytest]
addopts = --maxfail=3 --disable-warnings
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
```

**Step 5: Install in editable mode and verify**

Run: `cd /Users/squadgazzz/RustroverProjects/tidal-dedup && pip install -e .`

**Step 6: Commit**

```bash
git init
git add -A
git commit -m "chore: initial project scaffolding"
```

---

### Task 2: Retry Module

**Files:**
- Create: `src/tidal_dedup/retry.py`
- Create: `tests/unit/test_retry.py`

**Step 1: Write the failing tests**

```python
# tests/unit/test_retry.py
import pytest
from unittest.mock import AsyncMock, MagicMock
import tidalapi.exceptions
import requests.exceptions

from tidal_dedup.retry import retry_on_rate_limit


@pytest.mark.asyncio
async def test_retry_succeeds_on_first_try():
    func = AsyncMock(return_value="ok")
    result = await retry_on_rate_limit(func, "arg1")
    assert result == "ok"
    func.assert_awaited_once_with("arg1")


@pytest.mark.asyncio
async def test_retry_retries_on_too_many_requests(mocker):
    mocker.patch("tidal_dedup.retry.time.sleep")
    func = AsyncMock(side_effect=[tidalapi.exceptions.TooManyRequests("429"), "ok"])
    result = await retry_on_rate_limit(func)
    assert result == "ok"
    assert func.await_count == 2


@pytest.mark.asyncio
async def test_retry_retries_on_request_exception(mocker):
    mocker.patch("tidal_dedup.retry.time.sleep")
    exc = requests.exceptions.ConnectionError("conn err")
    func = AsyncMock(side_effect=[exc, "ok"])
    result = await retry_on_rate_limit(func)
    assert result == "ok"


@pytest.mark.asyncio
async def test_retry_aborts_after_max_retries(mocker):
    mocker.patch("tidal_dedup.retry.time.sleep")
    func = AsyncMock(side_effect=tidalapi.exceptions.TooManyRequests("429"))
    with pytest.raises(SystemExit):
        await retry_on_rate_limit(func, max_retries=2)
    assert func.await_count == 3  # initial + 2 retries


@pytest.mark.asyncio
async def test_retry_escalating_sleep(mocker):
    sleep_mock = mocker.patch("tidal_dedup.retry.time.sleep")
    func = AsyncMock(side_effect=[
        tidalapi.exceptions.TooManyRequests("429"),
        tidalapi.exceptions.TooManyRequests("429"),
        "ok"
    ])
    await retry_on_rate_limit(func)
    assert sleep_mock.call_args_list[0][0][0] == 1
    assert sleep_mock.call_args_list[1][0][0] == 10
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/squadgazzz/RustroverProjects/tidal-dedup && pytest tests/unit/test_retry.py -v`
Expected: FAIL (module not found)

**Step 3: Install pytest-asyncio dependency**

Add `"pytest-asyncio~=0.23"` to dependencies in `pyproject.toml` and run `pip install -e .`

**Step 4: Write the implementation**

```python
# src/tidal_dedup/retry.py
import sys
import time
import traceback

import requests.exceptions
import tidalapi.exceptions

SLEEP_SCHEDULE = {5: 1, 4: 10, 3: 60, 2: 5 * 60, 1: 10 * 60}


async def retry_on_rate_limit(func, *args, max_retries=5, **kwargs):
    """Call an async function with escalating backoff on rate limit / request errors."""
    remaining = max_retries
    while True:
        try:
            return await func(*args, **kwargs)
        except (
            tidalapi.exceptions.TooManyRequests,
            requests.exceptions.RequestException,
        ) as e:
            if remaining <= 0:
                print(f"{e} could not be recovered after {max_retries} retries. Aborting.")
                print(traceback.format_exc())
                sys.exit(1)
            sleep_time = SLEEP_SCHEDULE.get(remaining, 1)
            print(f"{e} — retrying in {sleep_time}s ({remaining} retries left)")
            time.sleep(sleep_time)
            remaining -= 1
```

**Step 5: Run tests to verify they pass**

Run: `cd /Users/squadgazzz/RustroverProjects/tidal-dedup && pytest tests/unit/test_retry.py -v`
Expected: all PASS

**Step 6: Commit**

```bash
git add src/tidal_dedup/retry.py tests/unit/test_retry.py pyproject.toml
git commit -m "feat: add retry module with escalating backoff"
```

---

### Task 3: Detection Module

**Files:**
- Create: `src/tidal_dedup/detection.py`
- Create: `tests/unit/test_detection.py`

The detection module groups a list of tracks into "duplicate groups" — lists of tracks that are duplicates of each other. Each strategy is a function `(List[Track]) -> List[DuplicateGroup]` where `DuplicateGroup` is a list of `(index, track)` tuples with length >= 2.

**Step 1: Write the failing tests**

```python
# tests/unit/test_detection.py
import pytest
from unittest.mock import MagicMock
from tidal_dedup.detection import (
    group_by_id,
    group_by_isrc,
    group_by_name,
    find_duplicates,
)


def _make_track(id, name="Song", artist_name="Artist", isrc="US1234", duration=200, available=True):
    track = MagicMock()
    track.id = id
    track.name = name
    track.isrc = isrc
    track.duration = duration
    track.available = available
    artist = MagicMock()
    artist.name = artist_name
    track.artists = [artist]
    return track


class TestGroupById:
    def test_no_duplicates(self):
        tracks = [_make_track(1), _make_track(2), _make_track(3)]
        groups = group_by_id(tracks)
        assert groups == []

    def test_finds_duplicates(self):
        tracks = [_make_track(1), _make_track(2), _make_track(1)]
        groups = group_by_id(tracks)
        assert len(groups) == 1
        assert len(groups[0]) == 2
        assert groups[0][0][0] == 0  # index 0
        assert groups[0][1][0] == 2  # index 2

    def test_multiple_duplicate_groups(self):
        tracks = [_make_track(1), _make_track(2), _make_track(1), _make_track(2)]
        groups = group_by_id(tracks)
        assert len(groups) == 2


class TestGroupByIsrc:
    def test_no_duplicates(self):
        tracks = [_make_track(1, isrc="AA"), _make_track(2, isrc="BB")]
        groups = group_by_isrc(tracks)
        assert groups == []

    def test_finds_duplicates_different_ids(self):
        tracks = [_make_track(1, isrc="AA"), _make_track(2, isrc="AA")]
        groups = group_by_isrc(tracks)
        assert len(groups) == 1
        assert len(groups[0]) == 2

    def test_skips_tracks_without_isrc(self):
        tracks = [_make_track(1, isrc=None), _make_track(2, isrc=None)]
        groups = group_by_isrc(tracks)
        assert groups == []


class TestGroupByName:
    def test_no_duplicates(self):
        tracks = [
            _make_track(1, name="Song A", artist_name="Artist X", duration=200),
            _make_track(2, name="Song B", artist_name="Artist Y", duration=200),
        ]
        groups = group_by_name(tracks)
        assert groups == []

    def test_finds_duplicates_same_name_artist(self):
        tracks = [
            _make_track(1, name="Song A", artist_name="Artist X", duration=200),
            _make_track(2, name="Song A", artist_name="Artist X", duration=201),
        ]
        groups = group_by_name(tracks)
        assert len(groups) == 1

    def test_case_insensitive(self):
        tracks = [
            _make_track(1, name="song a", artist_name="artist x", duration=200),
            _make_track(2, name="Song A", artist_name="Artist X", duration=200),
        ]
        groups = group_by_name(tracks)
        assert len(groups) == 1

    def test_duration_tolerance(self):
        tracks = [
            _make_track(1, name="Song A", artist_name="Artist X", duration=200),
            _make_track(2, name="Song A", artist_name="Artist X", duration=210),
        ]
        groups = group_by_name(tracks)
        assert groups == []  # too far apart

    def test_different_artists_not_duplicates(self):
        tracks = [
            _make_track(1, name="Song A", artist_name="Artist X", duration=200),
            _make_track(2, name="Song A", artist_name="Artist Y", duration=200),
        ]
        groups = group_by_name(tracks)
        assert groups == []


class TestFindDuplicates:
    def test_single_strategy(self):
        tracks = [_make_track(1), _make_track(2), _make_track(1)]
        groups = find_duplicates(tracks, strategies=["id"])
        assert len(groups) == 1

    def test_combined_strategies(self):
        # id=1 appears twice (caught by id strategy)
        # id=2 and id=3 have same ISRC (caught by isrc strategy)
        tracks = [
            _make_track(1, isrc="AA"),
            _make_track(2, isrc="BB"),
            _make_track(1, isrc="AA"),
            _make_track(3, isrc="BB"),
        ]
        groups = find_duplicates(tracks, strategies=["id", "isrc"])
        assert len(groups) == 2

    def test_default_strategy_is_id(self):
        tracks = [_make_track(1), _make_track(1)]
        groups = find_duplicates(tracks, strategies=[])
        assert len(groups) == 1
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/squadgazzz/RustroverProjects/tidal-dedup && pytest tests/unit/test_detection.py -v`
Expected: FAIL (module not found)

**Step 3: Write the implementation**

```python
# src/tidal_dedup/detection.py
from collections import defaultdict
from typing import List, Sequence, Tuple
import unicodedata

import tidalapi

# A DuplicateGroup is a list of (original_index, track) tuples
DuplicateGroup = List[Tuple[int, tidalapi.Track]]


def _normalize(s: str) -> str:
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode("ascii").lower().strip()


def group_by_id(tracks: Sequence[tidalapi.Track]) -> List[DuplicateGroup]:
    """Group tracks that share the same Tidal track ID."""
    buckets: dict[int, DuplicateGroup] = defaultdict(list)
    for idx, track in enumerate(tracks):
        buckets[track.id].append((idx, track))
    return [group for group in buckets.values() if len(group) >= 2]


def group_by_isrc(tracks: Sequence[tidalapi.Track]) -> List[DuplicateGroup]:
    """Group tracks that share the same ISRC code."""
    buckets: dict[str, DuplicateGroup] = defaultdict(list)
    for idx, track in enumerate(tracks):
        if track.isrc:
            buckets[track.isrc].append((idx, track))
    return [group for group in buckets.values() if len(group) >= 2]


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
        # We cluster by checking if any pair is within tolerance.
        # For simplicity, check all against the first track's duration.
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
        strategies = ["id"]

    # Collect all groups, dedup by frozenset of indices
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
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/squadgazzz/RustroverProjects/tidal-dedup && pytest tests/unit/test_detection.py -v`
Expected: all PASS

**Step 5: Commit**

```bash
git add src/tidal_dedup/detection.py tests/unit/test_detection.py
git commit -m "feat: add duplicate detection strategies (id, isrc, name)"
```

---

### Task 4: Dedup Module (Resolution Logic)

**Files:**
- Create: `src/tidal_dedup/dedup.py`
- Create: `tests/unit/test_dedup.py`

**Step 1: Write the failing tests**

```python
# tests/unit/test_dedup.py
import pytest
from unittest.mock import MagicMock, patch
from tidal_dedup.dedup import resolve_duplicates
from tidal_dedup.detection import DuplicateGroup


QUALITY_ORDER = {"LOW": 0, "HIGH": 1, "LOSSLESS": 2, "HI_RES_LOSSLESS": 3}


def _make_track(id, quality="HIGH", duration=200, name="Song", artist_name="Artist"):
    track = MagicMock()
    track.id = id
    track.name = name
    track.audio_quality = quality
    track.duration = duration
    artist = MagicMock()
    artist.name = artist_name
    track.artists = [artist]
    return track


class TestResolveKeepOldest:
    def test_keeps_first_occurrence(self):
        t1, t2, t3 = _make_track(1), _make_track(1), _make_track(1)
        group: DuplicateGroup = [(0, t1), (5, t2), (10, t3)]
        keep_idx, remove_indices = resolve_duplicates(group, strategy="oldest")
        assert keep_idx == 0
        assert remove_indices == [5, 10]


class TestResolveKeepNewest:
    def test_keeps_last_occurrence(self):
        t1, t2, t3 = _make_track(1), _make_track(1), _make_track(1)
        group: DuplicateGroup = [(0, t1), (5, t2), (10, t3)]
        keep_idx, remove_indices = resolve_duplicates(group, strategy="newest")
        assert keep_idx == 10
        assert remove_indices == [0, 5]


class TestResolveKeepBestQuality:
    def test_keeps_highest_quality(self):
        t1 = _make_track(1, quality="HIGH")
        t2 = _make_track(2, quality="LOSSLESS")
        t3 = _make_track(3, quality="LOW")
        group: DuplicateGroup = [(0, t1), (5, t2), (10, t3)]
        keep_idx, remove_indices = resolve_duplicates(group, strategy="best-quality")
        assert keep_idx == 5
        assert remove_indices == [0, 10]

    def test_ties_broken_by_position(self):
        t1 = _make_track(1, quality="LOSSLESS")
        t2 = _make_track(2, quality="LOSSLESS")
        group: DuplicateGroup = [(0, t1), (5, t2)]
        keep_idx, remove_indices = resolve_duplicates(group, strategy="best-quality")
        assert keep_idx == 0  # first one wins on tie
        assert remove_indices == [5]
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/squadgazzz/RustroverProjects/tidal-dedup && pytest tests/unit/test_dedup.py -v`
Expected: FAIL (module not found)

**Step 3: Write the implementation**

```python
# src/tidal_dedup/dedup.py
from typing import List, Tuple
from tidal_dedup.detection import DuplicateGroup

QUALITY_RANK = {"LOW": 0, "HIGH": 1, "LOSSLESS": 2, "HI_RES_LOSSLESS": 3}


def resolve_duplicates(group: DuplicateGroup, strategy: str = "oldest") -> Tuple[int, List[int]]:
    """Given a duplicate group, decide which to keep and which to remove.

    Returns (keep_index, [remove_indices]) where indices are original playlist positions.
    """
    if strategy == "oldest":
        sorted_group = sorted(group, key=lambda item: item[0])
        keep = sorted_group[0]
        remove = sorted_group[1:]
    elif strategy == "newest":
        sorted_group = sorted(group, key=lambda item: item[0], reverse=True)
        keep = sorted_group[0]
        remove = sorted_group[1:]
    elif strategy == "best-quality":
        sorted_group = sorted(
            group,
            key=lambda item: (QUALITY_RANK.get(item[1].audio_quality, -1), -item[0]),
            reverse=True,
        )
        keep = sorted_group[0]
        remove = sorted_group[1:]
    else:
        raise ValueError(f"Unknown resolution strategy: {strategy}")

    return keep[0], [idx for idx, _ in remove]
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/squadgazzz/RustroverProjects/tidal-dedup && pytest tests/unit/test_dedup.py -v`
Expected: all PASS

**Step 5: Commit**

```bash
git add src/tidal_dedup/dedup.py tests/unit/test_dedup.py
git commit -m "feat: add duplicate resolution strategies (oldest, newest, best-quality)"
```

---

### Task 5: Auth Module

**Files:**
- Create: `src/tidal_dedup/auth.py`

Adapted from `spotify_to_tidal/auth.py`, Tidal-only.

**Step 1: Write the implementation**

```python
# src/tidal_dedup/auth.py
import sys
import webbrowser

import tidalapi
import yaml


def open_tidal_session() -> tidalapi.Session:
    """Open a Tidal session, reusing a saved token if available."""
    try:
        with open(".session.yml", "r") as f:
            previous_session = yaml.safe_load(f)
    except OSError:
        previous_session = None

    session = tidalapi.Session()

    if previous_session:
        try:
            if session.load_oauth_session(
                token_type=previous_session["token_type"],
                access_token=previous_session["access_token"],
                refresh_token=previous_session["refresh_token"],
            ):
                return session
        except Exception as e:
            print(f"Error loading previous Tidal session: {e}")

    login, future = session.login_oauth()
    print("Login with the web browser: " + login.verification_uri_complete)
    url = login.verification_uri_complete
    if not url.startswith("https://"):
        url = "https://" + url
    webbrowser.open(url)
    future.result()

    with open(".session.yml", "w") as f:
        yaml.dump(
            {
                "session_id": session.session_id,
                "token_type": session.token_type,
                "access_token": session.access_token,
                "refresh_token": session.refresh_token,
            },
            f,
        )
    return session
```

**Step 2: Commit**

```bash
git add src/tidal_dedup/auth.py
git commit -m "feat: add Tidal OAuth auth module"
```

---

### Task 6: Tidal API Helpers

**Files:**
- Create: `src/tidal_dedup/tidal_api.py`

Adapted from `spotify_to_tidal/tidalapi_patch.py`. Provides functions to fetch tracks and remove items.

**Step 1: Write the implementation**

```python
# src/tidal_dedup/tidal_api.py
import asyncio
import math
from typing import List

import tidalapi
from tidal_dedup.retry import retry_on_rate_limit


def remove_indices_from_playlist(playlist: tidalapi.UserPlaylist, indices: List[int]):
    """Remove tracks at the given indices from a Tidal playlist.

    Indices must be sorted descending to avoid shifting issues, but this
    function handles sorting internally.
    """
    if not indices:
        return
    # Sort descending and process in chunks to avoid index shifting
    sorted_indices = sorted(indices, reverse=True)
    headers = {"If-None-Match": playlist._etag}
    # Tidal API accepts comma-separated indices for batch delete
    index_string = ",".join(map(str, sorted_indices))
    playlist.request.request(
        "DELETE",
        (playlist._base_url + "/items/%s") % (playlist.id, index_string),
        headers=headers,
    )
    playlist._reparse()


def remove_favorites(session: tidalapi.Session, track_ids: List[int]):
    """Remove tracks from Tidal favorites."""
    for track_id in track_ids:
        session.user.favorites.remove_track(track_id)


async def get_all_playlist_tracks(playlist: tidalapi.Playlist) -> List[tidalapi.Track]:
    """Fetch all tracks from a Tidal playlist."""
    def _fetch(offset: int = 0):
        params = {"limit": 20, "offset": offset}
        return playlist.session.request.map_request(
            f"{playlist._base_url % playlist.id}/tracks", params=params
        )

    first_chunk = _fetch()
    limit = first_chunk["limit"]
    total = first_chunk["totalNumberOfItems"]
    tracks = playlist.session.request.map_json(
        first_chunk, parse=playlist.session.parse_track
    )

    if len(tracks) < total:
        offsets = [limit * n for n in range(1, math.ceil(total / limit))]
        extra = await asyncio.gather(
            *[
                asyncio.to_thread(
                    lambda o: playlist.session.request.map_json(
                        _fetch(o), parse=playlist.session.parse_track
                    ),
                    offset,
                )
                for offset in offsets
            ]
        )
        for chunk in extra:
            tracks.extend(chunk)
    return tracks


async def get_all_favorites(session: tidalapi.Session) -> List[tidalapi.Track]:
    """Fetch all favorite tracks."""
    favorites = session.user.favorites
    params = {"limit": 100, "order": "DATE", "orderDirection": "ASC"}

    def _fetch(offset: int = 0):
        p = {**params, "offset": offset}
        return favorites.session.request.map_request(
            f"{favorites.base_url}/tracks", params=p
        )

    first_chunk = _fetch()
    limit = first_chunk["limit"]
    total = first_chunk["totalNumberOfItems"]
    tracks = favorites.session.request.map_json(
        first_chunk, parse=favorites.session.parse_track
    )

    if len(tracks) < total:
        offsets = [limit * n for n in range(1, math.ceil(total / limit))]
        extra = await asyncio.gather(
            *[
                asyncio.to_thread(
                    lambda o: favorites.session.request.map_json(
                        _fetch(o), parse=favorites.session.parse_track
                    ),
                    offset,
                )
                for offset in offsets
            ]
        )
        for chunk in extra:
            tracks.extend(chunk)
    return tracks


async def get_all_playlists(session: tidalapi.Session) -> List[tidalapi.Playlist]:
    """Fetch all user playlists."""
    user = session.user

    def _fetch(offset: int = 0):
        params = {"limit": 10, "offset": offset}
        return user.session.request.map_request(
            f"users/{user.id}/playlists", params=params
        )

    first_chunk = _fetch()
    limit = first_chunk["limit"]
    total = first_chunk["totalNumberOfItems"]
    playlists = user.session.request.map_json(
        first_chunk, parse=user.playlist.parse_factory
    )

    if len(playlists) < total:
        offsets = [limit * n for n in range(1, math.ceil(total / limit))]
        extra = await asyncio.gather(
            *[
                asyncio.to_thread(
                    lambda o: user.session.request.map_json(
                        _fetch(o), parse=user.playlist.parse_factory
                    ),
                    offset,
                )
                for offset in offsets
            ]
        )
        for chunk in extra:
            playlists.extend(chunk)
    return playlists
```

**Step 2: Commit**

```bash
git add src/tidal_dedup/tidal_api.py
git commit -m "feat: add Tidal API helpers (fetch tracks, remove items)"
```

---

### Task 7: Display Module

**Files:**
- Create: `src/tidal_dedup/display.py`

Handles terminal output for all three execution modes.

**Step 1: Write the implementation**

```python
# src/tidal_dedup/display.py
from typing import List, Tuple

import tidalapi

from tidal_dedup.detection import DuplicateGroup


def format_track(track: tidalapi.Track) -> str:
    """Format a track for display."""
    artists = ", ".join(a.name for a in track.artists) if track.artists else "Unknown"
    quality = track.audio_quality or "?"
    mins, secs = divmod(track.duration, 60)
    return f"{track.name} — {artists} [{quality}] ({mins}:{secs:02d})"


def print_duplicate_group(group: DuplicateGroup, keep_idx: int, remove_indices: List[int]):
    """Print a duplicate group showing which track is kept and which are removed."""
    print(f"\n  Duplicate group ({len(group)} tracks):")
    for idx, track in group:
        marker = "  KEEP  " if idx == keep_idx else "  REMOVE"
        print(f"    [{marker}] #{idx}: {format_track(track)}")


def print_summary(groups: List[Tuple[DuplicateGroup, int, List[int]]]):
    """Print a full summary of all planned changes."""
    total_remove = sum(len(remove) for _, _, remove in groups)
    print(f"\n{'='*60}")
    print(f"Deduplication Summary: {len(groups)} duplicate group(s), {total_remove} track(s) to remove")
    print(f"{'='*60}")
    for group, keep_idx, remove_indices in groups:
        print_duplicate_group(group, keep_idx, remove_indices)
    print(f"\n{'='*60}")
    print(f"Total: {total_remove} track(s) will be removed")
    print(f"{'='*60}")


def confirm_proceed() -> bool:
    """Ask the user to confirm the planned changes."""
    response = input("\nProceed with removal? [y/N]: ").strip().lower()
    return response in ("y", "yes")


def prompt_interactive(group: DuplicateGroup, keep_idx: int, remove_indices: List[int]) -> str:
    """Prompt for a single duplicate group in interactive mode.

    Returns: 'keep' to apply removal, 'skip' to skip, 'quit' to abort.
    """
    print_duplicate_group(group, keep_idx, remove_indices)
    while True:
        response = input("  Action — [k]eep plan / [s]kip / [q]uit: ").strip().lower()
        if response in ("k", "keep"):
            return "keep"
        elif response in ("s", "skip"):
            return "skip"
        elif response in ("q", "quit"):
            return "quit"
        print("  Invalid input. Enter k, s, or q.")
```

**Step 2: Commit**

```bash
git add src/tidal_dedup/display.py
git commit -m "feat: add display module for summary, interactive, and auto modes"
```

---

### Task 8: CLI Entry Point (__main__.py)

**Files:**
- Create: `src/tidal_dedup/__main__.py`

Wires everything together: argument parsing, session login, fetching tracks, detection, resolution, display, and removal.

**Step 1: Write the implementation**

```python
# src/tidal_dedup/__main__.py
import argparse
import asyncio
import re
import sys

from tidal_dedup.auth import open_tidal_session
from tidal_dedup.dedup import resolve_duplicates
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
    # Handle URLs like https://tidal.com/browse/playlist/UUID or https://listen.tidal.com/playlist/UUID
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
    strategy_group = parser.add_argument_group("detection strategies (combine any; default: --by-id)")
    strategy_group.add_argument("--by-id", action="store_true", help="Match by exact Tidal track ID")
    strategy_group.add_argument("--by-isrc", action="store_true", help="Match by ISRC code")
    strategy_group.add_argument("--by-name", action="store_true", help="Match by name + artist + duration")

    # Resolution
    parser.add_argument(
        "--keep",
        choices=["oldest", "newest", "best-quality"],
        default="oldest",
        help="Which duplicate to keep (default: oldest).",
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
    strategies = get_strategies(args)
    groups = find_duplicates(tracks, strategies)

    if not groups:
        print("No duplicates found.")
        return

    # Resolve each group
    resolved = []
    for group in groups:
        keep_idx, remove_indices = resolve_duplicates(group, strategy=args.keep)
        resolved.append((group, keep_idx, remove_indices))

    if args.mode == "auto":
        print_summary(resolved)
        all_remove = []
        for _, _, remove_indices in resolved:
            all_remove.extend(remove_indices)
        remove_fn(all_remove)
        print(f"Removed {len(all_remove)} duplicate track(s).")

    elif args.mode == "review":
        print_summary(resolved)
        if not confirm_proceed():
            print("Aborted.")
            return
        all_remove = []
        for _, _, remove_indices in resolved:
            all_remove.extend(remove_indices)
        remove_fn(all_remove)
        print(f"Removed {len(all_remove)} duplicate track(s).")

    elif args.mode == "interactive":
        total_removed = 0
        for group, keep_idx, remove_indices in resolved:
            action = prompt_interactive(group, keep_idx, remove_indices)
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
```

**Step 2: Verify it runs**

Run: `cd /Users/squadgazzz/RustroverProjects/tidal-dedup && python -m tidal_dedup --help`
Expected: help text with all arguments

**Step 3: Commit**

```bash
git add src/tidal_dedup/__main__.py
git commit -m "feat: add CLI entry point wiring all modules together"
```

---

### Task 9: End-to-End Smoke Test

**Step 1: Run the full test suite**

Run: `cd /Users/squadgazzz/RustroverProjects/tidal-dedup && pytest -v`
Expected: all tests pass

**Step 2: Verify CLI entry point works**

Run: `cd /Users/squadgazzz/RustroverProjects/tidal-dedup && tidal-dedup --help`
Expected: prints help with all options

**Step 3: Final commit if any fixes needed**

```bash
git add -A
git commit -m "chore: final cleanup and verification"
```

---

Plan saved to `docs/plans/2026-03-05-tidal-dedup-design.md`. Two execution options:

**1. Subagent-Driven (this session)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** — Open new session with executing-plans, batch execution with checkpoints

Which approach?