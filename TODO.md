# TODO: Active Product Roadmap

This file contains only outstanding or partially completed work. Completed,
rejected, and superseded items belong in `DONE.md`.

The legacy Raw Dump view remains useful and should be retained alongside the
read-only Explorer. The Explorer is an expansion of model inspection, not a
replacement for access to the raw generated dump.


## 0. Less Unknowns

- Identify more models based on architecture to reduce unknowns
- give Advanced view access to things it needs like layer/block counts
  and populate the tensor tab
- Green tag on card views should show LLM for language models, VLM for language
  models with vision capabilities, MMLM for multimodal language models
- run a quick simple text parse of language model chat template if available
  - add badges/tags for:
    - think tags for thinking models
    - tool tags for tool use models
- when dealing with .safetensors check beside the literal file (not symlink)
  for `config.json` and `chat_template.jinja` to fill in some blanks if available,
  may also need to look for `tokenizer_config.json` and `processor_config.json`
  for insight
  - 3 symlinks to directories with multiple models and various ancillary files
  can be found in `./test` to assist `fast_drive_image_models`, `fast_drive_llm_only`
  and `slow_drive_mostly_llm`

## 1. Library Linking and Path Resolution

- Add symbolic-link creation alongside existing move-file actions.
- Support editable destination templates such as
  `.\models\<type>\<model name>\<file>`.
- Provide presets for ComfyUI, LM Studio, Fooocus, and A1111 layouts.
- Canonicalize source and destination paths so symlinks, junctions, hardlinks,
  and original paths do not create duplicate model records.
- Show resolved source and planned destination paths before bulk operations.
- Detect existing destinations and offer Skip, Overwrite, or Open Location.

## 4. Explorer and Raw Dump Refinement

- Keep both Explorer and Raw Dump views available in the current shared tab;
  external context-menu View Raw actions must select the target model and load
  the full output when auto-load is enabled.
- In Raw model labels, hide the file extension unless Show Full Path is enabled.
- Keep the Raw selection-checkbox column permanently visible and pinned on the
  left; remove it from user-configurable column visibility/order.
- Implement safe host-side extraction for genuinely extractable embedded
  tensors such as VAE, encoder/decoder, and LoRA content. The current Explorer
  intentionally exposes header-derived candidates and requests only.
- Support extraction of useful text fields such as Jinja templates and training
  configuration without implying that tensor payloads were loaded.
- Add template type detection, validation, and supported-kwargs reporting.
- Add a selected-model action to force a metadata re-scan while preserving
  cached-first UI behavior.

### Explorer filter behavior

- Keep filter controls stable while parsing: retain selected values and avoid
  flashing, clearing, or rebuilding them on each progress update; apply new
  options atomically when parsing provides them.
- Constrain filter popups to the available window or screen bounds and make
  long option lists scrollable instead of allowing an oversized popup.

## 5. Advanced Model Viewer Redesign and Completion

- Revisit the Advanced Viewer layout and interaction model against the supplied
  reference screenshot; treat the current dialog as a functional foundation,
  not the final design.
- Continue aligning with the reference's file-inspector information architecture:
  add a persistent model path/header and denser use of the available window.
  Overview, Card Details, Metadata, Tensors, and Embedded Content already have
  separate peer work areas.
- Keep the at-a-glance facts and memory estimator as a compact header, sidebar,
  or secondary tab supporting the inspector rather than dominating the window.
- Show metadata as typed Key / Type / Value rows and tensors as an equivalently
  dense sortable table. Replace the reference editor's mutating actions with
  read-only actions such as Copy, Inspect, and safe Export/Extract where the
  underlying format actually supports them.
- Retain a topmost/modal relationship with the main window while improving the
  density and hierarchy of model facts.
- Add sorted/original block and layer views, visually grouped by shard.
- Present memory projections as useful comparisons across common context sizes,
  weight quantizations, and KV-cache precisions rather than only a single
  selected estimate.
- Expand the at-a-glance section, when values are available or safely
  inferable, with:
  - architecture, layers, parameter size, and file size;
  - total/active experts;
  - trained/max context, top-p, top-k, and temperature;
  - RoPE type, original context, scale, and multiplier;
  - MTP/speculative-decoding details;
  - embedded-template presence, type, validation, and supported kwargs;
  - associated `mmproj` and draft model facts.
- Refine capability badges so Tool Use, Thinking, and Vision distinguish
  metadata-backed facts from weaker heuristics.
- Generate the full human-readable runtime configuration format, including
  primary model, sidecars, comments, context, sampling, RoPE, and speculative
  decoding arguments. Keep copy icons consistent between Explorer/Raw and the
  Advanced Viewer; path-specific actions must copy exact full paths, while
  `File:` labels remain only in Copy Info output.

## 6. CLI, Packaging, and CI/CD

- Accept files/folders passed to the packaged executable and queue them after
  the GUI is ready, as if dropped onto the window.
- Add `modelinspector.exe -cli <commands>` pass-through and mirror the behavior
  when launched from Python.
- Finish wheel packaging.
- Add GitHub Actions for supported wheel builds, Windows executable packaging,
  optional publishing, and GitHub releases.

## 7. Developer Tooling and Architecture Graph

- Repair `.graphifyignore` ordering so `src/back/*.py` and `src/front/*.py`
  remain unignored after the broad `src/*` rule; the current incremental graph
  sees root `src/*.py` and tests but omits both application subpackages.
- Run a full Graphify rebuild after fixing the ignore rules, verify current
  frontend/backend nodes and edges are present, and use incremental
  `graphify update .` after later structural changes.
