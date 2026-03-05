import pytest
from unittest.mock import MagicMock
from tidal_dedup.dedup import resolve_duplicates
from tidal_dedup.detection import DuplicateGroup


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

    def test_ties_broken_by_stream_metadata(self):
        t1 = _make_track(1, quality="LOSSLESS")
        t2 = _make_track(2, quality="LOSSLESS")
        group: DuplicateGroup = [(0, t1), (5, t2)]
        stream_info = {0: (16, 44100), 5: (24, 96000)}
        keep_idx, remove_indices = resolve_duplicates(group, strategy="best-quality", stream_info=stream_info)
        assert keep_idx == 5  # t2 has higher bit_depth/sample_rate
        assert remove_indices == [0]

    def test_ties_broken_by_position_when_stream_equal(self):
        t1 = _make_track(1, quality="LOSSLESS")
        t2 = _make_track(2, quality="LOSSLESS")
        group: DuplicateGroup = [(0, t1), (5, t2)]
        stream_info = {0: (16, 44100), 5: (16, 44100)}
        keep_idx, remove_indices = resolve_duplicates(group, strategy="best-quality", stream_info=stream_info)
        assert keep_idx == 0  # first one wins on tie
        assert remove_indices == [5]
