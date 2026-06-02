#!/usr/bin/env bash
#
# Publish linux_dist/arch/PKGBUILD to the AUR (atlas-pm-git) in one step.
#
# The AUR package lives in its own git repo (ssh://aur@aur.archlinux.org/atlas-pm-git.git)
# containing only PKGBUILD + .SRCINFO at the root — it can't point at this repo's
# linux_dist/arch/ subfolder. So the workflow is: edit the PKGBUILD here (the source of
# truth), then run this to sync + push the AUR copy. .SRCINFO is regenerated from the
# PKGBUILD so the two can never drift.
#
#   ./linux_dist/arch/publish-aur.sh ["commit message"]
#   ./linux_dist/arch/publish-aur.sh --dry-run        # show what would change, don't push
#
# Env:
#   ATLAS_AUR_DIR   where to keep the AUR clone (default: ~/Projects/atlas-aur)
#
# Requires: git, makepkg, and your AUR SSH key loaded (the push uses it).

set -euo pipefail

PKG="atlas-pm-git"
AUR_URL="ssh://aur@aur.archlinux.org/${PKG}.git"
ARCH_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUR_DIR="${ATLAS_AUR_DIR:-$HOME/Projects/atlas-aur}"

DRY_RUN=0
MSG=""
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1 ;;
        *) MSG="$arg" ;;
    esac
done

command -v git     >/dev/null || { echo "error: git not found" >&2; exit 1; }
command -v makepkg >/dev/null || { echo "error: makepkg not found (install pacman/base-devel)" >&2; exit 1; }
[[ -f "$ARCH_DIR/PKGBUILD" ]] || { echo "error: $ARCH_DIR/PKGBUILD missing" >&2; exit 1; }

# 1. Get a clean AUR checkout (clone on first run; otherwise reset to the remote so a stale
#    or half-edited clone can't poison the push).
if [[ -d "$AUR_DIR/.git" ]]; then
    echo "==> Updating AUR clone at $AUR_DIR"
    git -C "$AUR_DIR" fetch --quiet origin
    git -C "$AUR_DIR" reset --quiet --hard origin/master
else
    echo "==> Cloning AUR repo into $AUR_DIR"
    git clone "$AUR_URL" "$AUR_DIR"
fi

# 2. Copy the PKGBUILD and regenerate .SRCINFO from it (in the AUR dir, so it's authoritative),
#    then mirror .SRCINFO back into this repo so the tracked copy stays identical.
cp "$ARCH_DIR/PKGBUILD" "$AUR_DIR/PKGBUILD"
( cd "$AUR_DIR" && makepkg --printsrcinfo > .SRCINFO )
cp "$AUR_DIR/.SRCINFO" "$ARCH_DIR/.SRCINFO"

# 3. Nothing changed? Then the AUR already matches — stop.
if git -C "$AUR_DIR" diff --quiet -- PKGBUILD .SRCINFO; then
    echo "==> AUR is already up to date — nothing to push."
    exit 0
fi

echo "==> Changes to publish:"
git -C "$AUR_DIR" --no-pager diff -- PKGBUILD .SRCINFO

[[ -z "$MSG" ]] && MSG="sync from atlas $(git -C "$ARCH_DIR" rev-parse --short HEAD 2>/dev/null || echo HEAD)"

if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "==> --dry-run: not committing or pushing. Would commit with: \"$MSG\""
    exit 0
fi

# 4. Commit + push to the AUR.
git -C "$AUR_DIR" add PKGBUILD .SRCINFO
git -C "$AUR_DIR" commit -m "$MSG"
git -C "$AUR_DIR" push origin master
echo "==> Pushed to AUR: $MSG"
echo "    (Remember to commit the refreshed $ARCH_DIR/.SRCINFO in the Atlas repo if it changed.)"
