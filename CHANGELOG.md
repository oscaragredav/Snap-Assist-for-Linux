# Changelog

All notable changes to SnapAssist are documented here. This project follows
[Semantic Versioning](https://semver.org/).

## [2.0.0-dev] - Unreleased

### Added

- Isolated stable/test channels with transactional switching and manifests.
- GNOME Shell 46 integration for X11, Wayland and XWayland through a versioned
  D-Bus protocol.
- Native layout and suggestion presentation, semantic platform contracts and
  a graphical editor for custom layouts and shortcuts.

### Changed

- The development tree identifies itself as `2.0.0.dev0`; installing it over
  the stable channel requires an explicit, gated promotion.
- Completed groups are raised immediately; dragging a grouped window now
  detaches it at the user's drop position, and suggestions only show fitting
  windows from the active workspace.
- GNOME preferences use symbolic layout names, automatic IDs and visual
  percentage controls; duplicated layouts start from the selected geometry.
- Replaced the geometry editor with selectable visual forms, click-to-select
  zones, proportional splits and undo; creation no longer exposes internal
  IDs, JSON or coordinates.
- Layout and shortcut changes reload automatically, and preferences are
  accessible directly from the native layout selector.

### Fixed

- Prevented minimum-size handling from expanding terminal windows over
  adjacent zones.
- Made long layout lists scrollable and fixed the graphical create, duplicate
  and shortcut-save actions.
- Added outside-click cancellation, reliable terminal unminimize/move/focus,
  and GNOME accelerator support for function and navigation keys.
- Kept keyboard selection visible by scrolling the native layout list.
- Removed the ambiguous proportion slider; visual forms and zone splits now
  use predictable equal divisions.
- Detect outside clicks from the GNOME stage using the selector's transformed
  coordinates, independent of modal event targeting.
- Standardized built-in labels as fractions and added a second focus request
  from the coordinator after every successful snap operation.
- Rendered `EnvironmentFile` without incompatible quotes in user services.
- Fixed new-layout creation incorrectly treating a null source as an existing
  custom layout.
- Rendered `WorkingDirectory` without incompatible quotes in user services.

## [1.1.0] - 2026-08-12

### Added

- Reproducible Python packaging and the `snapassist` command.
- XDG desktop-entry application-name resolution.
- Single-thread ownership checks for mutable runtime state.
- CI coverage for Python 3.11 through 3.13.

### Changed

- The installer renders the user unit with the actual XDG installation paths.
- Every callback crossing from Tkinter into the coordinator requires a flow ID.
- Diagnostic scripts are kept as documented development tools, outside the package.

### Removed

- Historical direct-snap callback and obsolete phase references in production code.
