# AGENTS.md

## Project overview

A Python toolchain that extracts resources (charts, illustrations, music, avatars) from a Phigros APK and repackages them for the Phira emulator. Flat structure, single entrypoint.

## Entrypoint & run

```bash
python main.py
```

Interactive CLI. Prompts for a version number, checks TapTap for updates, downloads/extracts the APK, generates `.pez` packs, and optionally produces cover images and rendered videos. All output lands under `data/` (gitignored).

## Environment

- Virtual env: `.venv/` (Python 3.14)
- Install deps: `pip install -r requirements.txt`
- System dependency: **libvorbis** is required for OGG audio output. macOS: `brew install libvorbis`

## Critical dependency constraint

**`UnityPy==1.10.18`** — pinned to exactly this version. Newer versions break `UnityTypeTree` usage. Do not upgrade.

## Module convention

Each `.py` module exposes a `run()` function called by `main.py`. When executed standalone (`__name__ == "__main__"`), most read args from `sys.argv` and `config.ini`.

Key modules and their roles:
- `gameInformation.py` — extracts song metadata, difficulty data, tips from APK
- `getResource.py` — extracts charts, illustrations, music, avatars (multi-threaded)
- `phira.py` — packages extracted resources into `.pez` files (ZIPs with `.pez` extension, each containing `info.yml` + chart json + illustration png + music ogg). The `info.yml` follows the Phira `ChartInfo` spec (`#[serde(rename_all = "camelCase")]` YAML with snake_case Rust field names in the source)
- `autoImage.py` — generates cover images using PIL (+ optional OpenGL with `trigridRenderer.py`)
- `taptap.py` — queries TapTap API for latest Phigros version/download URL
- `ttools.py` — launches external Phi-Recorder for video rendering

## Config

`config.ini` is read with `utf8` encoding. Settings control which resource types to extract, update limits, difficulty levels, and whether to auto-download/cover/render.

## Dead/replaced code

`autoCover.py` uses `pygame` (not in `requirements.txt`). It is **not called anywhere** — `main.py` uses `autoImage.py` (pure PIL). Do not modify or rely on `autoCover.py`.

## Static assets

- `resources/` — contains `AllSongBlur.png`, `TriGridBase.png`, and `trigrid.glsl` used by cover generation
- `font.ttf` — required in the repo root by `autoImage.py` for text rendering

## No test or CI infrastructure

There are no tests, no CI workflows, no linters, and no formatters configured in this repo. Do not attempt to run `pytest`, `flake8`, etc.

## .gitignore note

`data/`, `*.json`, `*.apk`, and `test_*.py` are gitignored. The only committed JSON files are inside `resources/` if any.
