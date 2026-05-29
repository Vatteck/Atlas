# Atlas

**Atlas** (formerly known as bauh) is the ultimate All-In-One graphical interface for managing your Linux software packages and applications. Atlas is being modernized with a sleek web UI and an optimized, lazy-loaded backend engine.

It currently supports the following formats: AppImage, Arch Linux packages (including AUR), Debian, Flatpak, Snap, and Native Web applications.

## Key features
- **Modern Web Interface:** A completely refactored frontend offering a dynamic, elegant experience.
- **Unified Management Panel:** Search, install, uninstall, upgrade, downgrade, and launch your applications across multiple formats from one place.
- **Optimized Engine:** Lazy loading of package backends for faster startup and reduced memory footprint.
- **System Backup:** Integrates with [Timeshift](https://github.com/teejee2008/timeshift) to provide a simple and safe backup process before applying changes to your system.

## Supported types

- **AppImage:** Integrated AppImage support directly from AppImageHub.
- **Arch packages/AUR:** Handles conflicts, missing/optional dependencies, and multi-threaded downloads.
- **Debian packages:** Supports dpkg/apt packages.
- **Flatpak:** Seamless Flatpak app management and full component updates.
- **Snap:** Snap application and channel management.
- **Web Applications:** Install native Web applications effortlessly with Electron and Nativefier.

## Directory structure, caching, and logs
- `~/.config/atlaspm` (or `/etc/atlaspm` for **root**): stores configuration files
- `~/.cache/atlaspm` (or `/var/cache/atlaspm` for **root**): stores data about your installed applications, databases, and indexes.
- `/tmp/atlaspm@$USER`: stores logging and temporary files

## Roadmap
- Rewrite the GUI to a modern, elegant web-based front-end.
- Modernize the background engine for optimal speed and concurrency.
- Re-introduce tray mode (the legacy Qt tray was removed in the rebrand; a non-Qt
  implementation is planned).
- Add advanced container sandboxing ("Vault").
- Expand support for additional formats.

## Contributing
We welcome contributions to Atlas! Please refer to the `CONTRIBUTING.md` file for more details.
