# REJECT: Rejected and Superseded Proposals

These are current product decisions, not permanent prohibitions. A proposal may
be reopened with new evidence and a reviewable scope.

## Destructive library operations

- **Rejected for future linking workflows:** collision choices that overwrite,
  delete, or move source/target files as an implicit side effect. Linking must
  remain preview-first and non-destructive.
- **Deferred, not rejected:** valid symbolic-link support and path-template
  workflows. The existing legacy Move action is separate and this decision does
  not claim that the application has no destructive actions.

## Superseded presentation proposals

- **Superseded, reviewable:** screenshot-driven alternate dense Advanced Viewer
  redesigns. The accepted Advanced Viewer layout is the current settled view;
  an alternate layout needs a new, evidence-backed proposal.
- **Superseded, reviewable:** typed metadata Key / Type / Value rows as a
  presentation redesign. The current searchable metadata and descriptor views
  remain accepted; typed rows are optional, not implemented work.
- **Rejected for the current direction:** replacing or removing the legacy Raw
  Dump view. Explorer and Raw intentionally coexist.

## Dependency parity

- **Rejected for parity alone:** adding the official `safetensors` dependency
  solely to duplicate the existing lightweight metadata-only header reader.
