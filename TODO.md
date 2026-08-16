# TODO: Repository Roadmap & Integration Plan

## 1. File Readers, Model Formats & Sharding

### Research Safetensors Integration: Add `safetensors` to `requirements.txt` and isolate file reading behind the shared reader abstraction.

- Add Checkpoint, `.onnx`, and `.pt`/`.pth` Support:
  - Implement extension dispatch for `.ckpt`, `.onnx`, `.pt`, and `.pth` only after explicit security sandboxing/safety checks.
  - Prefer lightweight inspection paths that avoid importing PyTorch unless strictly required.

### Support Sharded Model Files:

- Add support for sharded `.gguf` and `.safetensors` sets (e.g., `*00001-of-00004*`).
- Index original layer/block order and track shard indices (`shard_id = 0` for non-sharded files).

### Sidecar File Discovery & Association:

- Automatically detect sidecar files (`mmproj`, `dflash`/`eagle`, `draft`) located in the same directory as the primary model.
- Store sidecar metadata separately and tag the primary model with `mmproj`, `draft`, or `spec-type`.
- Maintain lightweight sidecar records to perform fast change-detection scans upon user request.

## 2. Library Linking & Path Resolution

### Symbolic Link Creation: Add an option to create symlinks alongside existing move-file operations.

- Destination Templates:
  - Support configurable directory templates (e.g., `.\models\<type>\<model name>\<file>`).
  - Provide built-in presets for ComfyUI, LMStudio, Fooocus, and A1111 directory conventions.

### Canonical Path Resolution: Resolve target paths before link creation to prevent duplicating aliases (symlinks, junctions, hardlinks).

- Pre-Flight Operations & Safety:
  - Show resolved source paths and planned link destinations prior to bulk execution.
  - Detect existing target files/links and offer `Skip`, `Overwrite`, or `Open Location` options.

## 3. Cache Management & Integrity

### Manual Cache Load Actions:

- `Load Cache`: Active only when the current model cache is populated.
- `Load Cache All`: Active if historic/unlocatable model caches exist.
- `Load Cache Archived`: Active if historic model caches exist.

### Cache Validation & Background Sync:

- Verify physical file existence on cache load; move missing entries to the historic/archive cache.
- Detect changes in file size or timestamp to queue non-blocking background metadata updates.

### Settings Clear & Verify Controls:

- Display item counts (`Total` / `Active` / `Historic`) alongside the `Clear Cache` button.
- Add a `Verify Cached File Paths` tool to scan and archive stale or unlocatable cached models.

## 4. Settings & External Theme Engine

### JSONC Migration:

- Convert `settings.ini` to a human-readable `settings.jsonc` file with explanatory comments.
- Generate a user settings template on launch with default values and safety guidelines.
- Remove obsolete `load default libraries on startup` setting.

### Externalized Themes:

- Move hard-coded themes into external `./assets/` JSON files as defaults.
- Include free/unlicensed community variants (e.g., Catppuccin, Cursor, GitHub, Gruvbox).
- Export themes to the user configuration folder; validate external themes on load with an automatic fallback to default + alert popup on error.

## 5. UI & Explorer Tab Refinement

### Data Tab Customization:

- Add a settings pane for Data Tab column visibility and order (scrolling list with checkboxes and reorder drag-handles).
- Persist column width adjustments across application restarts.

### Tooltips: Add contextual tooltips across UI buttons, controls, and configuration options.

- Explorer Tab (Replacing Raw Tab):
  - Redesign the Raw Tab into a read-only GGUF/Safetensors Explorer Tab.
  - Display metadata in searchable key/value rows.
  - Render tensors in a sortable/filterable table showing Name, Shape, Dtype, Bucket, and Parameter count.
  - Enable inspection and extraction of embedded checkpoint tensors (VAE, encoder, decoder, LoRA) and text fields (Jinja templates, training configs).

### Metadata Re-scan: Add a lower right menu option to force a re-scan of selected models.

## 6. Advanced Model Viewer & Memory Estimator

### Interactive Popup Window:

- Dedicated pop-out window (pinned on top, locking main window interactions).
- Toggle between sorted and unsorted block/layer views (grouped visually by shard).

### Capability & Model Tagging:

- Categorize models by domain (Diffusion, LLM, Multimodal, LoRA).
- Apply granular capability badges (Tool Use, Thinking, Vision).

### At-a-Glance Summary & Memory Projection:

- Calculate estimated VRAM/RAM requirements mapped across context sizes and quantization levels.
- Display core parameters: Architecture, Layer Count, Experts (Total/Active), Trained/Max Context, Top-P/Top-K, Temperature, RoPE Scaling, and MTP details.
- Validate embedded Jinja templates and supported keyword arguments.
- Include a `Copy Configuration` button to output plain-text human-readable model parameters:

```text
[SOME_FILE_NAME_BF16]
; 256 experts, 8 used, 40 layers - qwen35moe - 16.5GB
model=C:\path\to\SOME_FOLDER_NAME\SOME_FILE_NAME-BF16.gguf
; 27 layers, 447.5M, clip, 863.4MB
mmproj=C:\path\to\SOME_FOLDER_NAME\SOME_FILE_NAME-mmproj-F16.gguf
; 5 layers, 833.2M, dflash-draft, 514.9MB
spec-draft-model=C:\path\to\SOME_FOLDER_NAME\SOME_FILE_NAME-dflash.Q4_K_M.gguf
ctx-size=262144
temperature=0.3
rope-scaling=yarn
rope-scale=64
yarn-orig-ctx=4096
spec-type=draft-mtp
```

## 7. CLI, Packaging & CI/CD

### Drag-and-Drop & CLI Pass-through:

- Handle files/folders dropped directly onto the compiled `.exe` icon by queuing them on startup.
- Implement a CLI pass-through flag: `modelinspector.exe -cli <command>`.
- Mirror all GUI to CLI capabilities when executing directly via Python scripts.

### Build System & GitHub Workflows:

- Complete python wheel build configuration (`pyproject.toml` / `setup.py`).
- Create GitHub Actions workflows to compile cross-platform Python wheels, build Windows `.exe` packages, and publish releases automatically.
