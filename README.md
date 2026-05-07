# Safetensors Model Inspector

Inspect `.safetensors` and `.gguf` models from a desktop GUI and CLI.

<img width="2537" height="1283" alt="image" src="https://github.com/user-attachments/assets/27ce9f06-4c5f-4b32-aee9-bda85ff576b0" />

## What It Does

- Detects architecture families and variants (Flux, SDXL/SD3, Wan, Hunyuan, Qwen, HiDream, LTX, Z-Image, Chroma, and more)
- Detects adapter type (`LoRA`, `LyCORIS`, `LoHa`, `LoKr`, `DoRA`, `GLoRA`)
- Extracts training metadata when present (steps, epochs, images, resolution, software, and related fields)
- Supports file or folder workflows (including recursive folder scanning)
- Supports `.modelinfo` key dumps for debugging and sharing
- Supports read-only `.gguf` metadata/tensor inspection

## Repository Layout

- `gui.py`: GUI only
- `inspect_model.py`: model parsing, detection logic, data extraction, CLI
- `requirements.txt`: dependencies
- `venv_create.bat`: virtual environment bootstrap helper
- `venv_activate.bat`: activate helper

## Setup

1. Create the virtual environment:

```bat
venv_create.bat
```

2. Activate:

```bat
venv_activate.bat
```

3. Run GUI:

```bat
py gui.py
```

4. Run CLI help:

```bat
py inspect_model.py --help
```

## CLI Usage

### Inspect one or more files

```bat
py inspect_model.py path\to\model1.safetensors path\to\model2.safetensors
py inspect_model.py path\to\model.gguf
```

### Inspect folders

```bat
py inspect_model.py path\to\folder
py inspect_model.py path\to\folder --recursive
```

### JSON output

```bat
py inspect_model.py path\to\folder --recursive --json
py inspect_model.py path\to\folder --recursive --threads 4 --json
```

### Write `.modelinfo` files

```bat
py inspect_model.py path\to\folder --recursive --write-modelinfo
```

### Write JSON `.modelinfo` files

```bat
py inspect_model.py path\to\folder --recursive --write-modelinfo-json
```

### Dump key/debug report text to console

```bat
py inspect_model.py path\to\folder --recursive --dump-keys
```

### Optional alias fallback (filename tokens)

```bat
py inspect_model.py path\to\folder --recursive --allow-filename-alias-detection
```

## GUI Walkthrough

### Top Area (Input + Controls)

- Drag and drop files or folders into the drop zone
- Use `Browse...` or `Browse Folder...`
- `Analyze` processes queued inputs
- `Settings` controls visibility and behavior
- `Minimize` / `Restore` collapses or expands the top area for more workspace
 
<img width="2547" height="373" alt="image" src="https://github.com/user-attachments/assets/419e5d42-e3f2-469e-8850-633720ac7782" />

### Tab: Cards

- Detailed model cards with a `Simple View` toggle for lightweight cards
- Supports card selection, multi-select, and context menu actions
- Card order follows the current Data table sort order

<img width="1708" height="1076" alt="image" src="https://github.com/user-attachments/assets/a146a5a7-3a9f-422f-8eee-64efb36af715" />

- Supports specific LoRA formats like LoHa, LoKr, GLoRa
- Some fail sometimes (lycoris)

<img width="2526" height="953" alt="image" src="https://github.com/user-attachments/assets/1ef32b95-868a-4407-8569-8207d68eac3a" />



### Tab: Data

- Sortable/resizable table
- Multi-select cells and copy via `Ctrl+C`
- Right-click actions (`View Raw`, `Copy Selected Entries`)
- Column visibility can be configured in settings
- Sorting the table also reorders the Cards tab and Raw model dropdown

<img width="2385" height="257" alt="image" src="https://github.com/user-attachments/assets/1dcd1a23-ca36-433e-8e77-9252cfcc0208" />



### Tab: Raw

- Per-model raw `.modelinfo` text view
- `View Raw` context action jumps here for the selected model summary
- `Load Full Dump` explicitly generates and caches the full tensor key dump for the current model
- `Ctrl+C` copies the selected text, or the full raw content when no selection exists

<img width="2442" height="726" alt="image" src="https://github.com/user-attachments/assets/4c2f9d4d-1476-4348-b872-06c282a80007" />


## Notes

- Folder drag/drop and folder browse both support recursive discovery of `.safetensors` and `.gguf`.
- `.ckpt`, `.pt`, and `.pth` are treated as unsafe/unsupported for now because PyTorch checkpoint loading may require pickle deserialization. The app warns and ignores them until an explicit safe-loading mode exists.
- Parsed model summaries are cached by resolved path, file size, and modified time to speed up repeat inspections.
- If `Cache full tensor data during analysis` is enabled, compact tensor descriptors are stored under `cache/data/` beside the summary cache and can be used for Raw/modelinfo output even when the model file is unavailable.
- Successful folder scans are cached immediately. The `Load default libraries on startup` setting restores cached scan results on launch and keeps cached summaries even when files are missing or temporarily unreachable.
- App settings and cache default to `.model-inspector` beside the app for portable use. Override with `SMI_DATA_DIR`, `SMI_CACHE_DIR`, or `SMI_SETTINGS_PATH`.
- Filtering in the UI affects visibility and copy behavior (hidden rows are excluded from table copy).
- `.modelinfo` output is generated by shared backend logic in `inspect_model.py`.
- The GUI dump button writes selected models; from the Raw tab, with nothing selected, it writes only the current Raw model.
- The `.safetensors` reader intentionally uses the custom header parser as the primary path because it is dependency-free and preserves tensor data offsets. The official `safetensors.safe_open(..., framework="numpy")` API can provide metadata, keys, shapes, and dtypes without Torch, but it does not expose per-tensor data offsets.
- Filename alias detection is opt-in in Settings and can map filename tokens to fallback labels.
- `Pony7` is treated as distinct from `PDXL`. The alias tokens `pony7`, `ponyv7`, and `pony v7` map to `Pony7`.

## Settings (Current)

### General

- `Filename Alias Detection`: optional filename-token fallback for special labels
- `Auto-minimize top section on Analyze`
- `Auto-analyze when files are added`
- `Load default libraries on startup`: restores files from cached folder scans
- `Analysis threads`: bounded worker count for independent file inspection, default `2`
- `Cache full tensor data during analysis`: stores compact tensor descriptors for offline Raw/modelinfo use
- `Also dump JSON .modelinfo`: writes `.modelinfo.json` files with the dump action
- `File add behavior`:
  - `Replace current input list`
  - `Append to current input list`
- `Default tab`: `Cards`, `Data`, or `Raw`

### Cards

- `Simple Cards`: choose which data fields are shown
- `Detailed Cards`: choose which data fields are shown

### Data Columns

- `Data Columns`: choose visible columns in the Data tab
