# TIC-80 Collection Manager 🕹️

**TIC-80 Collection Manager (t80m)** is a comprehensive command-line tool to **build, maintain, curate, and export** a high-quality local collection of **TIC-80 cartridges**, media assets, and metadata.

It synchronizes data from **tic80.com** and **itch.io**, maintains a local CSV database for manual curation, and produces **EmulationStation-compatible** `gamelist.xml` files for retro handhelds and frontends.

If you just want a ready-made snapshot, you can download a pre-packed collection:

➡️ **[TIC80-collection-2026-01-03.tar.xz](https://pub-a92c0b929eca476cba03da88268d07db.r2.dev/TIC80-collection-2026-01-03.tar.xz)**

But if you want **continuous updates, reproducibility, and full control**, this tool is for you.

---

## Why this exists

TIC-80 games are a *perfect* fit for retro handhelds — small, creative, and plentiful — but building a clean, usable library is harder than it should be.

Problems this project solves:

* **Hash-based scraping breaks easily**: TIC-80 carts are frequently updated, which invalidates ScreenScraper-style ROM hashing.
* **Duplicate and multi-version carts**: The same game often exists in multiple places and revisions.
* **No opinionated baseline**: Instead of heavy filtering, this project provides a *low-bar curated baseline* so users can apply their own filters later.

The goal is not to decide what is “good”, but to provide a **complete, structured, and inspectable dataset** that others can curate further.

---

## Features

* **Multi-source ingestion**
  Fetches and merges data from:

  * the official **tic80.com** API
  * **itch.io** games tagged *made-with-tic-80*

* **Local CSV database**
  A human-editable `games_info.csv` where you can:

  * override names, authors, descriptions
  * flag games for inclusion/exclusion
  * manage distribution safety

* **ROM & media management**

  * Downloads updated carts
  * Backs up outdated ROMs
  * Manages screenshots, title screens, and cover art

* **Flexible folder layouts**

  * Single ROM directory
  * Or multiple category folders (Games, WIP, Tools, Itch, …)

* **Deterministic filenames**

  * Custom naming rules
  * Case normalization
  * Optional category suffixes

* **EmulationStation-ready output**
  Generates `gamelist.xml` compatible with EmulationStation, RetroPie, ES-DE, etc.

* **Export profiles**
  Export:

  * curated collections
  * almost-all collections
  * distribution-safe subsets for sharing

---

## License

### Media (images, screenshots, covers)

**CC BY-NC-SA 4.0** — Attribution-NonCommercial-ShareAlike

This matches ScreenScraper’s license. Even self-captured images are released under the same license to keep redistribution simple and consistent.

### Text metadata

Game descriptions and player counts sourced from ScreenScraper follow the same license.

---

## Installation

### Prerequisites

* Python 3.11+
* **uv** — [https://docs.astral.sh/uv/](https://docs.astral.sh/uv/)

### Install

```bash
uv tool install .
```

To update after a git pull or local changes:

```bash
uv tool upgrade t80m --reinstall
```

---

## First run

Run the tool once to generate the configuration file:

```bash
t80m
```

The tool will print the config location. Defaults are safe, but fully customizable.

### Fast initialization (recommended)

To avoid hammering servers and save time, initialize from the latest snapshot:

```bash
t80m init
```

This will:

* clone the database and media repositories
* download a verified InitPack
* extract ROMs and media using your current naming rules

---

## Configuration & paths

`t80m` uses **platformdirs**, so paths are OS-correct:

* **Linux**: `~/.local/share/t80m/`
* **Windows**: `%LOCALAPPDATA%\\t80m`
* **macOS**: `~/Library/Application Support/t80m/`

### Key paths

|                      Path | Description                 |
| ------------------------: | --------------------------- |
|                   `roms/` | TIC-80 cartridges           |
| `database/games_info.csv` | Main metadata database      |
|                  `media/` | Screenshots, covers, titles |
|            `gamelist.xml` | EmulationStation gamelist   |
|          `backuped-roms/` | Old ROM versions            |

> **LibreOffice note**
> When opening the CSV, choose **Unicode (UTF-8)**, otherwise non‑Latin text and emojis will break.

---

## Usage

```bash
t80m <command> [source] [options]
```

### Global options

| Flag                              | Values                                | Default     | Description                        |
| --------------------------------- | ------------------------------------- | ----------- | ---------------------------------- |
| `--rom-folder-organization`       | `single`, `multiple`                  | auto        | One folder or per-category folders |
| `--filename-category-parenthesis` | `true`, `false`                       | `true`      | Adds `(WIP)`, `(Tool)` etc.        |
| `--use-custom-filenames`          | `true`, `false`                       | `true`      | Uses `name_overwrite`              |
| `--use-custom-gamenames`          | `true`, `false`                       | `true`      | Uses `name_overwrite` in metadata  |
| `--filename-case`                 | `unchanged`, `uppercase`, `lowercase` | `uppercase` | Filename normalization             |

---

## Commands

### `updatecsv`

Synchronize metadata **without downloading ROMs**.

```bash
t80m updatecsv tic80com
t80m updatecsv itch
```

* Adds new carts
* Updates hashes and URLs
* Marks entries for re-download

> **Itch.io note**
> A Cloudflare CAPTCHA must be solved once. The tool opens your editor and guides you through copying a cURL request.


---

### `get-roms`

Download missing or updated ROMs and media.

```bash
t80m get-roms tic80com
t80m get-roms itch
```

Download modes:

* **default**: curated collection
* `--download-almost-all`: broader collection
* `--download-all`: everything

---

### `sync-filenames`

Rename ROMs and media after editing the CSV.

```bash
t80m sync-filenames
```

---

### `get-coverarts`

Fetch missing TIC-80 cover art.

```bash
t80m get-coverarts
```

---

### `update-gamelistxml`

Generate an EmulationStation-compatible gamelist.

```bash
t80m update-gamelistxml --image-path=./images
```

---

### `export-collection`

Export a normalized, shareable collection.

```bash
t80m export-collection --dest-path=./export-dir
```

Options:

* default: curated
* `--export-almost-all`
* `--export-all`
* `--export-curated-distribution-safe`

Output:

* ROMs (single folder)
* media subfolders
* `gamelist.xml` with relative paths

---

## Note for TIC-80 developers

If you publish **paid games on itch.io**, consider releasing a **free demo** (like *Last in Space* or *Bone Knight*).

This tool scrapes the playable HTML version. Games flagged with `distribution_license=F` are excluded when using:

```bash
--export-curated-distribution-safe
```

Nothing prevents manual scraping, but this flag exists to support responsible redistribution.

---

## Philosophy

* Transparent over magical
* CSV > opaque databases
* Reproducible builds
* User-controlled curation

If this aligns with how you think about collections, welcome aboard.
