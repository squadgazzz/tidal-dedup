# This repo is archived in favor of https://github.com/squadgazzz/luna-plugins#playlisttools. Please use TidaLuna with this plugin for better experience.

# tidal-dedup

A CLI tool to find and remove duplicate tracks from your Tidal playlists and favorites.

## Features

- **Four detection strategies** (combinable):
  - `--by-name` (default) — matches by full track name (title + version) and artist
  - `--by-id` — exact same Tidal track ID added multiple times
  - `--by-isrc` — same ISRC code with artist verification to avoid Tidal metadata errors
  - `--by-remaster` — finds remastered versions of the same track (e.g., "Angel" vs "Angel (Remastered 2015)"). Handles patterns like `(Remastered)`, `(Remastered YYYY)`, `(YYYY Remaster)`, `[Remastered]`, `- Remastered`, and `(Deluxe Remastered)`.
- **Three resolution strategies** for choosing which duplicate to keep:
  - `--keep best-quality` (default) — keeps the highest quality version (compares audio tier, then bit depth/sample rate, then prefers remastered versions)
  - `--keep oldest` — keeps the first occurrence
  - `--keep newest` — keeps the last occurrence
- **Three execution modes:**
  - `--mode review` (default) — shows a summary of all changes and asks for confirmation
  - `--mode interactive` — prompts for each duplicate group individually
  - `--mode auto` — applies all changes without asking
- Rate-limit aware with automatic retry and escalating backoff

## Installation

Requires Python 3.10+.

```bash
git clone https://github.com/your-username/tidal-dedup.git
cd tidal-dedup
pip install -e .
```

## Usage

On first run, a browser window will open for Tidal OAuth login. The session is saved to `.session.yml` for future runs.

```bash
# Deduplicate favorites (default: by name, keep best quality, review mode)
tidal-dedup

# Deduplicate a specific playlist (by ID or URL)
tidal-dedup 12345678-abcd-1234-abcd-1234567890ab
tidal-dedup "https://tidal.com/browse/playlist/12345678-abcd-1234-abcd-1234567890ab"

# Deduplicate all user playlists
tidal-dedup --all

# Combine detection strategies
tidal-dedup --by-id --by-isrc --by-name

# Find and remove remastered duplicates
tidal-dedup --by-remaster

# Keep oldest duplicate, apply automatically
tidal-dedup --keep oldest --mode auto

# Interactive mode — decide per duplicate group
tidal-dedup --mode interactive
```

### Example output

```
Opening Tidal session...
Connected to Tidal.
Processing favorites...
Loading favorite tracks from Tidal
Fetched 2560 track(s).

============================================================
Deduplication Summary: 2 duplicate group(s), 2 track(s) to remove
============================================================

  Duplicate group (2 tracks):
    [  KEEP  ] #95: Without — The Soft Moon [Deeper (2015)] [LOSSLESS] (3:24) 16bit/44100Hz
    [  REMOVE] #96: Without — The Soft Moon [Deeper (2015)] [LOSSLESS] (3:24) 16bit/44100Hz

  Duplicate group (2 tracks):
    [  KEEP  ] #195: Masc — Chat Pile [God's Country (2022)] [LOSSLESS] (4:09) 16bit/44100Hz
    [  REMOVE] #241: Masc — Chat Pile [God's Country (2022)] [LOSSLESS] (4:09) 16bit/44100Hz

============================================================
Total: 2 track(s) will be removed
============================================================

Proceed with removal? [y/N]:
```

## Running tests

```bash
pytest
```

## License

MIT
