import pytest
from unittest.mock import MagicMock
from tidal_dedup.detection import (
    group_by_id,
    group_by_isrc,
    group_by_name,
    group_by_remaster,
    find_duplicates,
    strip_remaster_tags,
    is_remastered,
)


def _make_track(id, name="Song", artist_name="Artist", isrc="US1234", duration=200, available=True, version=None):
    track = MagicMock()
    track.id = id
    track.name = name
    track.version = version
    track.full_name = f"{name} ({version})" if version else name
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
            _make_track(1, name="Song A", artist_name="Artist X"),
            _make_track(2, name="Song B", artist_name="Artist Y"),
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
            _make_track(1, name="song a", artist_name="artist x"),
            _make_track(2, name="Song A", artist_name="Artist X"),
        ]
        groups = group_by_name(tracks)
        assert len(groups) == 1

    def test_different_duration_still_matches(self):
        tracks = [
            _make_track(1, name="Song A", artist_name="Artist X", duration=200),
            _make_track(2, name="Song A", artist_name="Artist X", duration=210),
        ]
        groups = group_by_name(tracks)
        assert len(groups) == 1  # no duration tolerance — same full_name matches

    def test_different_artists_not_duplicates(self):
        tracks = [
            _make_track(1, name="Song A", artist_name="Artist X"),
            _make_track(2, name="Song A", artist_name="Artist Y"),
        ]
        groups = group_by_name(tracks)
        assert groups == []

    def test_different_versions_not_duplicates(self):
        tracks = [
            _make_track(1, name="Without", artist_name="Artist X"),
            _make_track(2, name="Without", artist_name="Artist X", version="Instrumental"),
        ]
        groups = group_by_name(tracks)
        assert groups == []


class TestStripRemasterTags:
    def test_parenthesized_remastered(self):
        assert strip_remaster_tags("Angel (Remastered 2015)") == "Angel"

    def test_bracketed_remaster(self):
        assert strip_remaster_tags("Angel [Remastered]") == "Angel"

    def test_dash_remastered(self):
        assert strip_remaster_tags("Angel - Remastered 2015") == "Angel"

    def test_year_first(self):
        assert strip_remaster_tags("Angel (2015 Remaster)") == "Angel"

    def test_deluxe_remastered(self):
        assert strip_remaster_tags("Angel (Deluxe Remastered)") == "Angel"

    def test_no_remaster_tag(self):
        assert strip_remaster_tags("Angel") == "Angel"

    def test_instrumental_not_stripped(self):
        assert strip_remaster_tags("Angel (Instrumental)") == "Angel (Instrumental)"


class TestIsRemastered:
    def test_remastered_in_version(self):
        track = _make_track(1, name="Angel", version="Remastered 2015")
        assert is_remastered(track)

    def test_remastered_in_title(self):
        track = _make_track(1, name="Angel (Remastered 2015)")
        assert is_remastered(track)

    def test_not_remastered(self):
        track = _make_track(1, name="Angel")
        assert not is_remastered(track)

    def test_instrumental_not_remastered(self):
        track = _make_track(1, name="Angel", version="Instrumental")
        assert not is_remastered(track)


class TestGroupByRemaster:
    def test_groups_remastered_with_original(self):
        tracks = [
            _make_track(1, name="Angel", artist_name="Massive Attack"),
            _make_track(2, name="Angel", artist_name="Massive Attack", version="Remastered 2015"),
        ]
        groups = group_by_remaster(tracks)
        assert len(groups) == 1
        assert len(groups[0]) == 2

    def test_no_remaster_tag_no_group(self):
        tracks = [
            _make_track(1, name="Angel", artist_name="Massive Attack"),
            _make_track(2, name="Angel", artist_name="Massive Attack"),
        ]
        groups = group_by_remaster(tracks)
        assert groups == []  # neither has remaster tag

    def test_different_songs_not_grouped(self):
        tracks = [
            _make_track(1, name="Angel", artist_name="Massive Attack", version="Remastered 2015"),
            _make_track(2, name="Teardrop", artist_name="Massive Attack", version="Remastered 2015"),
        ]
        groups = group_by_remaster(tracks)
        assert groups == []

    def test_instrumental_not_grouped_with_original(self):
        tracks = [
            _make_track(1, name="Angel", artist_name="Massive Attack"),
            _make_track(2, name="Angel", artist_name="Massive Attack", version="Instrumental"),
        ]
        groups = group_by_remaster(tracks)
        assert groups == []

    def test_different_artists_not_grouped(self):
        tracks = [
            _make_track(1, name="Angel", artist_name="Massive Attack"),
            _make_track(2, name="Angel", artist_name="Other Artist", version="Remastered 2015"),
        ]
        groups = group_by_remaster(tracks)
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
