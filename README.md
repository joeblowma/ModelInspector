# ModelInspector

ModelInspector is a Windows-friendly desktop and CLI utility for inspecting
language and diffusion model files without loading tensor payloads.

Based on the original [Safetensors Model Inspector](https://github.com/MNeMoNiCuZ/SafetensorsModelInspector).
See the [project repository](https://github.com/joeblowma/ModelInspector) and
[LICENSE](./LICENSE).

## Requirements

- Python **3.12 or newer** for source and wheel installs.
- The Windows release is a packaged `ModelInspector.exe` and does not require
  a separate Python installation.

## Install on Windows

### Windows release

Download the versioned Windows zip from the project's
[GitHub Releases](https://github.com/joeblowma/ModelInspector/releases) page,
extract it, and run `ModelInspector.exe`.

### Wheel

Install the wheel in a Python 3.12+ environment:

```bat
py -3.12 -m pip install modelinspector-<version>-py3-none-any.whl
modelinspector --help
modelinspector-gui --help
```

`modelinspector` and `modelinspector-gui` are console scripts. Use those names
after installation; they are not `python -m` module names.

### Source checkout

```bat
git clone https://github.com/joeblowma/ModelInspector.git
cd ModelInspector
py -3.12 -m pip install -r requirements.txt
py src/gui.py
py src/inspect_model.py --help
```

`py src/gui.py` starts the GUI. `py src/inspect_model.py` starts the CLI.
Both accept the source-checkout layout without an editable install.

## Supported formats and safety

The normal reader set is:

- `.safetensors`, including `.safetensors.index.json` shard indexes;
- `.gguf`;
- `.onnx`.

Inspection is header/metadata-only: tensor names, shapes, types, and bounded
metadata may be read, but tensor payload bytes are never read. Sharded model
sets and associated metadata are handled through the same bounded path.

PyTorch-style `.ckpt`, `.pt`, and `.pth` files are opt-in only:

```bat
modelinspector path\to\file.ckpt --checkpoint-safety metadata
```

This mode reads only safe ZIP metadata/version entries and never
pickle-deserializes a checkpoint. The default `--checkpoint-safety reject`
policy ignores these files.

## CLI

Inspect files or folders; add `--recursive` for subfolders:

```bat
modelinspector path\to\model.safetensors
modelinspector path\to\folder --recursive --json
py src/inspect_model.py path\to\folder --recursive --threads 4 --json
```

Current CLI help is available with `modelinspector --help` or
`py src/inspect_model.py --help`. The positional target and options are:

```text
targets [targets ...]
-h, --help
-s, --settings PATH
--cachedir PATH
--cache PATH
-r, --recursive
--allow-filename-alias-detection
--checkpoint-safety {reject,metadata}
--json
--dump-keys
--write-modelinfo
--write-modelinfo-json
--resolve-output-path
--threads THREADS
```

`--write-modelinfo` and `--write-modelinfo-json` write beside the inspected
model by default. `--resolve-output-path` selects the resolved target path
instead. `--cache PATH` selects the primary model-cache directory and records
its history; `--cachedir PATH` relocates all application caches for the run.

The GUI accepts an optional file or folder target and the same `-s`/
`--settings`, `--cache`, and `--cachedir` startup options:

```text
py src/gui.py [FILE_OR_FOLDER ...]
py src/gui.py -s PATH
py src/gui.py --cache PATH
py src/gui.py --cachedir PATH
```

## GUI

The main window has three views:

- **Cards** — compact model cards; click a card to open that model in the
  Advanced Viewer.
- **Data** — sortable, copyable table with configurable column visibility,
  order, and widths.
- **Raw** — per-model raw output; full key dumps are explicitly generated and
  cached rather than read from tensor payloads.

The Advanced Viewer provides **Overview**, **Card Details**, **Metadata**,
**Tensors**, and **Embedded Content** pages. Embedded metadata actions are
bounded and read-only: Inspect reuses a stored bounded preview when possible,
Save writes a readable artifact, and exact source JSON extraction is limited
to locatable safetensors/GGUF metadata.

Settings currently provide:

- General analysis, filename-alias, JSON modelinfo, raw-loading, descriptor
  caching, add-mode, default-tab, theme, and remembered-window-size controls;
- Data-column visibility/order/width controls, with the selection column
  locked first and always visible;
- a live Theme editor with Save, Save As, and reset actions;
- model-cache location/history, cache verification, and Clear Cache actions.

The release Settings default is 900x640 and is clamped to the current screen.
Cache loading distinguishes active, all, and historic (missing-source)
summaries without re-inspecting historic files.

Fresh settings, application data, and cache paths use
`Path.home()/.local/share/ModelInspector`; an existing legacy
`.model-inspector` location is retained. Save/move output dialogs use the same
default through `app_paths.ensure_output_dir()` and create it when needed.
Override paths with `SMI_DATA_DIR`, `SMI_CACHE_DIR`, `SMI_MODEL_CACHE_DIR`,
`SMI_SETTINGS_PATH`, or `SMI_OUTPUT_DIR`.

## Build and test

From a checkout:

```bat
py -3.12 -m pip install -r requirements-dev.txt
py -3.12 -m build --wheel
win_compile.bat
```

For the canonical headless test run in PowerShell:

```powershell
$env:PYTHONPATH = "src"
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest tests
```

`win_clean.bat` removes generated build artifacts. Packaging contracts can be
checked with `python -m pytest tests/test_packaging.py -q`.

## Validation status

The final canonical run at `2026-09-21T10:57:10.5414636-06:00` passed
**466 tests, with 4 skipped, in 172.61 seconds** (exit 0):
`$env:PYTHONPATH='src'; $env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests`.
The run log is `R:\Temp\opencode\modelinspector-metadata-full-20260921.log`.
The focused metadata run passed 12 tests. Real-header Qwen smokes passed in
human-readable and JSON modes: the generic Qwen Image2.1 false positive is
fixed by the diffusion guard; the unsupported diffusion case projects a null
domain and empty capabilities, not an image-domain or inference-support claim.
Qwen35 prompt enhancers remain `LLM` with `thinking`/`tools`.

This does not claim all release gates are green: packaged visual QA, the
existing strict pylint blocker, hosted Windows/build validation, tagged-release
validation, and a full Graphify refresh remain open. Mypy is not a configured
clean gate; the first UI pass had 187 errors without a baseline, and the
targeted metadata pass had four import-resolution errors.
