# TODO

Outstanding items of the actionable integration plan for repository organization, additional model formats, richer dumps, and UI expansion.

## 4. Library Linking & Path Resolution

- Add an option to create symbolic links alongside the existing move-file actions.
- Support destination templates for common model library layouts, such as `.\models\<type>\<model name>\<file>`.
- Add presets for ComfyUI, LMStudio, Foooocus, and A1111 directory conventions, with editable templates.
- Resolve canonical target paths before creating links so the same model is not duplicated under symlink, junction, hardlink, or original-path aliases.
- Show the resolved source path and planned link path before applying bulk link operations.
- Detect existing destination files/links and offer skip, overwrite, or open-location behavior.

## 8. Research Safetensors Library Integration

- If suitable, add `safetensors` to `requirements.txt` and isolate usage behind the reader abstraction.

## 10. Replace Raw Tab with Explorer Tab

- Expand the current raw tab into an `Explorer` tab inspired by the GGUF editor UI, but read-only.
- Show parsed metadata as searchable key/value rows.
- Show parsed tensors in a sortable/filterable table with name, shape, dtype, component bucket, and parameter count.
- Show info regarding embedded "checkpoint" tensors (vae/encoder/decoder/lora/etc), and ability to extract them
- Support extracting individual useful fields such as jinja templates, training data, etc
- Support `.safetensors` and `.gguf` and others through the shared reader abstraction.

## 11. Add Checkpoint, `.onnx`, and `.pt`/`.pth` Support

- Prefer lightweight inspection paths that avoid importing Torch unless necessary.
- Add extension dispatch for `.ckpt`, `.onnx`, `.pt`, and `.pth` only after the safety model is explicit.

## 12. Refactor Overloaded Structures

- Use graphify god-node results to split overloaded modules and classes.
- Consider extracting reader modules, architecture detection modules, modelinfo dumping, and GUI widgets into separate files.
- Prioritize reducing `MainWindow`, `inspect_file()`, `generate_modelinfo_dump()`, and architecture detection helper sprawl.
- Add tests or smoke fixtures before large refactors so behavior stays stable.
- After code changes, run `graphify update .` and review the updated god-node/community report.
