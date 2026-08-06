#!/usr/bin/env bash
#
# Cut a stable Atlas release and prepare the `atlas-pm` AUR package.
#
# What it does:
#   1. Resolves the version (arg, else atlas/__init__.py) and sanity-checks the tree.
#   2. Runs the test suite (the release is what strangers get — don't ship red).
#   3. Tags vX.Y.Z and pushes the tag (GitHub only generates the source tarball once the tag
#      exists, so the push has to happen before we can pin a checksum).
#   4. Downloads the tag tarball, pins its sha256 into release/PKGBUILD, regenerates .SRCINFO.
#   5. Prints the exact commit + AUR-publish commands. It does NOT touch the AUR unless you
#      pass --publish.
#
#   ./linux_dist/arch/release.sh                 # version from atlas/__init__.py
#   ./linux_dist/arch/release.sh 0.13.0          # explicit version
#   ./linux_dist/arch/release.sh --skip-tests    # skip the pytest gate
#   ./linux_dist/arch/release.sh --skip-docs-check   # skip the README/CHANGELOG gate
#   ./linux_dist/arch/release.sh --publish       # also sync + push the atlas-pm AUR repo
#
# Env:
#   ATLAS_AUR_DIR_RELEASE   where to keep the atlas-pm AUR clone (default ~/Projects/atlas-pm)
#
# Requires: git, makepkg, curl, sha256sum (+ your AUR SSH key loaded for --publish).
# This is the stable sibling of publish-aur.sh (which handles the -git package).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REL_DIR="$REPO_ROOT/linux_dist/arch/release"
PKGBUILD="$REL_DIR/PKGBUILD"
GH_REPO="Vatteck/Atlas"
PKG="atlas-pm"
AUR_URL="ssh://aur@aur.archlinux.org/${PKG}.git"
AUR_DIR="${ATLAS_AUR_DIR_RELEASE:-$HOME/Projects/$PKG}"

VERSION=""
SKIP_TESTS=0
SKIP_DOCS=0
PUBLISH=0
for arg in "$@"; do
    case "$arg" in
        --skip-tests)      SKIP_TESTS=1 ;;
        --skip-docs-check) SKIP_DOCS=1 ;;
        --publish)         PUBLISH=1 ;;
        -*)                echo "error: unknown flag '$arg'" >&2; exit 2 ;;
        *)                 VERSION="$arg" ;;
    esac
done

for c in git makepkg curl sha256sum; do
    command -v "$c" >/dev/null || { echo "error: $c not found" >&2; exit 1; }
done
[[ -f "$PKGBUILD" ]] || { echo "error: $PKGBUILD missing" >&2; exit 1; }

# --- 1. Version -----------------------------------------------------------------------------
if [[ -z "$VERSION" ]]; then
    VERSION="$(sed -n "s/^__version__ = ['\"]\([^'\"]*\)['\"].*/\1/p" "$REPO_ROOT/atlas/__init__.py")"
fi
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] \
    || { echo "error: version '$VERSION' is not X.Y.Z" >&2; exit 1; }
TAG="v$VERSION"
echo "==> Releasing $TAG (atlas-pm)"

# Tree must be master, clean, and level with origin — the tag has to mean something.
BRANCH="$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD)"
[[ "$BRANCH" == "master" ]] || { echo "error: on '$BRANCH', not master" >&2; exit 1; }
git -C "$REPO_ROOT" diff --quiet && git -C "$REPO_ROOT" diff --cached --quiet \
    || { echo "error: working tree not clean — commit or stash first" >&2; exit 1; }
git -C "$REPO_ROOT" fetch --quiet origin
[[ "$(git -C "$REPO_ROOT" rev-parse HEAD)" == "$(git -C "$REPO_ROOT" rev-parse origin/master)" ]] \
    || { echo "error: local master != origin/master — push/pull first" >&2; exit 1; }

# --- 1b. Docs freshness ---------------------------------------------------------------------
# Both of these have drifted silently before: the README's What's-new section sat a full version
# behind (0.16.1 shipped headlining 0.16.0), and 0.15.0 shipped with no CHANGELOG entry at all —
# it had to be backfilled onto master later, which the GitHub Release workflow now works around.
# Catch it here, while it's still a one-line fix; once the tag is pushed it isn't.
if [[ "$SKIP_DOCS" -eq 0 ]]; then
    echo "==> Checking README + CHANGELOG mention $VERSION"
    docs_err=0

    README_VER="$(sed -n "s/^## .*What's new in \([0-9]\+\.[0-9]\+\.[0-9]\+\).*/\1/p" \
                  "$REPO_ROOT/README.md" | head -1)"
    if [[ "$README_VER" != "$VERSION" ]]; then
        echo "error: README.md What's-new section says '${README_VER:-<no section found>}', expected $VERSION" >&2
        docs_err=1
    fi

    # Fixed-string match: the version's dots would otherwise be regex wildcards.
    if ! grep -qF "## [$VERSION]" "$REPO_ROOT/CHANGELOG.md"; then
        echo "error: CHANGELOG.md has no '## [$VERSION]' section" >&2
        docs_err=1
    fi

    if [[ "$docs_err" -ne 0 ]]; then
        echo "       Fix the docs and re-run, or pass --skip-docs-check to override." >&2
        exit 1
    fi
    echo "    ok — both current"
fi

# --- 2. Tests -------------------------------------------------------------------------------
if [[ "$SKIP_TESTS" -eq 0 ]]; then
    echo "==> Running test suite"
    # Prefer the project venv if present so deps resolve the same as a dev run.
    [[ -f "$REPO_ROOT/venv/bin/activate" ]] && source "$REPO_ROOT/venv/bin/activate"
    ( cd "$REPO_ROOT" && python -m pytest -q )
else
    echo "==> Skipping tests (--skip-tests)"
fi

# --- 3. Tag + push --------------------------------------------------------------------------
if git -C "$REPO_ROOT" rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
    echo "==> Tag $TAG already exists locally — reusing"
else
    git -C "$REPO_ROOT" tag -a "$TAG" -m "Atlas $TAG"
    echo "==> Created tag $TAG"
fi
git -C "$REPO_ROOT" push origin "$TAG"
echo "==> Pushed tag $TAG"

# --- 4. Pin the checksum --------------------------------------------------------------------
TARBALL_URL="https://github.com/$GH_REPO/archive/refs/tags/$TAG.tar.gz"
echo "==> Pinning sha256 from $TARBALL_URL"
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
curl -fsSL "$TARBALL_URL" -o "$TMP"
# Read the whole listing into a var and take line 1 — piping to `head` would SIGPIPE `tar`,
# which `set -o pipefail` turns into a script-killing failure.
TOP="$(tar tzf "$TMP")"; TOP="${TOP%%$'\n'*}"
[[ "$TOP" == "Atlas-$VERSION/" ]] \
    || echo "warning: tarball top dir is '$TOP', expected 'Atlas-$VERSION/' — check the cd in build()/package()" >&2
SHA="$(sha256sum "$TMP" | cut -d' ' -f1)"
echo "==> sha256 = $SHA"

# pkgrel resets to 1 only on a genuine version change; a same-version re-release (packaging-only
# fix) keeps whatever pkgrel you bumped by hand.
OLD_VER="$(sed -n 's/^pkgver=//p' "$PKGBUILD")"
sed -i -e "s/^pkgver=.*/pkgver=$VERSION/" -e "s/^sha256sums=.*/sha256sums=('$SHA')/" "$PKGBUILD"
if [[ "$OLD_VER" != "$VERSION" ]]; then
    sed -i "s/^pkgrel=.*/pkgrel=1/" "$PKGBUILD"
fi

# Regenerate .SRCINFO from the now-pinned PKGBUILD (keeps the two from drifting).
( cd "$REL_DIR" && makepkg --printsrcinfo > .SRCINFO )
echo "==> Updated PKGBUILD + .SRCINFO:"
git -C "$REPO_ROOT" --no-pager diff -- "$PKGBUILD" "$REL_DIR/.SRCINFO" || true

# --- 5. Next steps / optional publish -------------------------------------------------------
cat <<EOF

────────────────────────────────────────────────────────────────────────
Release $TAG prepared. To finish:

  # a) commit the pinned recipe in this repo
  git -C "$REPO_ROOT" add linux_dist/arch/release/PKGBUILD linux_dist/arch/release/.SRCINFO
  git -C "$REPO_ROOT" commit -m "release: atlas-pm $VERSION"
  git -C "$REPO_ROOT" push

  # b) publish to the AUR (or just re-run this with --publish)
  git clone $AUR_URL "$AUR_DIR"          # first time only
  cd "$AUR_DIR" && git fetch origin && git reset --hard origin/master
  cp "$PKGBUILD" "$REL_DIR/.SRCINFO" "$AUR_DIR/"
  git -C "$AUR_DIR" commit -am "atlas-pm $VERSION" && git -C "$AUR_DIR" push
────────────────────────────────────────────────────────────────────────
EOF

if [[ "$PUBLISH" -eq 1 ]]; then
    echo "==> --publish: syncing + pushing the $PKG AUR repo"
    if [[ -d "$AUR_DIR/.git" ]]; then
        git -C "$AUR_DIR" fetch --quiet origin
        git -C "$AUR_DIR" reset --quiet --hard origin/master
    else
        git clone "$AUR_URL" "$AUR_DIR"
    fi
    cp "$PKGBUILD" "$AUR_DIR/PKGBUILD"
    cp "$REL_DIR/.SRCINFO" "$AUR_DIR/.SRCINFO"
    if git -C "$AUR_DIR" diff --quiet -- PKGBUILD .SRCINFO; then
        echo "==> AUR already up to date — nothing to push."
    else
        git -C "$AUR_DIR" add PKGBUILD .SRCINFO
        git -C "$AUR_DIR" commit -m "atlas-pm $VERSION"
        git -C "$AUR_DIR" push origin master
        echo "==> Pushed atlas-pm $VERSION to the AUR."
    fi
fi
