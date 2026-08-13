# Changelog

All notable changes to SnapAssist are documented here. This project follows
[Semantic Versioning](https://semver.org/).

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
