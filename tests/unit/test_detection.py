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

    def test_rejects_same_isrc_different_artist(self):
        tracks = [
            _make_track(1, isrc="AA", artist_name="Artist X"),
            _make_track(2, isrc="AA", artist_name="Artist Y"),
        ]
        groups = group_by_isrc(tracks)
        assert groups == []

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

    def test_default_strategy_is_name(self):
        tracks = [
            _make_track(1, name="Song A", artist_name="Artist X", duration=200),
            _make_track(2, name="Song A", artist_name="Artist X", duration=200),
        ]
        groups = find_duplicates(tracks, strategies=[])
        assert len(groups) == 1
