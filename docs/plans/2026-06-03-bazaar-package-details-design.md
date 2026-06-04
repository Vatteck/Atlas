# Rich Package Details View (Bazaar-style) Design

## Overview
Redesign the package details modal in Atlas to provide a richer, more visually appealing layout, drawing inspiration from Bazaar's detailed metadata tiles. The goal is to surface key metadata (size, age rating, safety, license) as large, prominent tiles rather than inline text.

## Backend Data Pipeline
1. **Age Rating**: Parse `content_rating` (OARS) from Flathub AppStream metadata and map it to standardized age brackets (e.g., "All Ages", "12+", "18+").
2. **Form Factor**: Read AppStream XML for form-factor hints (`<requires><display_length...` or `<branding>`) to expose a `desktop_only` flag.
3. **Size Data**: Ensure `download_size` and `installed_size` are accurately exposed in the common package payload for Flatpak, Arch, and AUR.
4. **Graceful Degradation**: Arch and AUR packages will lack certain Flathub-specific metrics (Age Rating, Downloads/Month). The backend must cleanly omit these fields rather than providing null/invalid markers.

## Frontend Layout & Styling
1. **The Badge Grid**: Replace the current inline `#detail-badges` container with a new `.rich-badges-grid` (CSS Grid or Flexbox) at the top of the modal body, underneath the header.
2. **Tile Design**: Each metadata point will be rendered as a standalone vertical tile containing:
   - A modern vector icon (SVG).
   - Primary text value (e.g., "213 MB", "Proprietary", "12+").
   - Secondary label text (e.g., "Download", "License", "Age Rating").
3. **Dynamic Rendering**: `main.js` will dynamically generate these tiles based on the package metadata. The layout will gracefully adjust its columns based on how many tiles are present (e.g., Flatpaks may have 6, AUR may have 4).
4. **CSS Overhaul**: Add styling for `.rich-badge-tile`, `.rich-badge-icon`, `.rich-badge-value`, and `.rich-badge-label` to match the Bazaar aesthetic.
