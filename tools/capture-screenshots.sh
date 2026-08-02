#!/usr/bin/env bash
#
# capture-screenshots.sh — re-shoot the README screenshots from the real app.
#
# Dev tool; NOT shipped in the package. Captures the actual WebKitGTK window with grim so
# the images are real pixels from the engine users run, at identical framing for every shot.
#
# You drive the app; the script handles focus, sizing, framing, cropping and naming.
#
#   Usage:  tools/capture-screenshots.sh              # all shots, in order
#           tools/capture-screenshots.sh dashboard    # just one (or several)
#           tools/capture-screenshots.sh --list
#
# Requires: Hyprland, grim, hyprctl, jq.  Start Atlas first (`atlas --logs`); the script
# waits for the window if it isn't up yet.
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="$REPO_ROOT/docs/screenshots"

# README renders these side by side in a 2-col table, so a consistent size matters more
# than a big one. 1280x800 is the app's comfortable layout without looking sparse.
WIDTH="${ATLAS_SHOT_WIDTH:-1280}"
HEIGHT="${ATLAS_SHOT_HEIGHT:-800}"

# name|what to navigate to before capturing
SHOTS=(
  "dashboard|the Dashboard — the attention center, ideally with real updates/health cards showing"
  "apppanel|a package that exists in more than one source, with the source switcher visible"
  "details|a package detail modal, Overview tab (an AUR package shows the caution banner + audit)"
  "diskpage|Disk → Reclaim space, with orphans/cache/runtimes populated"
  "terminal|a live transaction with the terminal dialog open — start an install, then capture mid-run"
)

die() { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }
info() { printf '\033[36m→\033[0m %s\n' "$*"; }
ok()   { printf '\033[32m✓\033[0m %s\n' "$*"; }

if [[ "${1:-}" == "--list" ]]; then
  printf '%-12s %s\n' "NAME" "WHAT TO SHOW"
  for s in "${SHOTS[@]}"; do printf '%-12s %s\n' "${s%%|*}" "${s#*|}"; done
  exit 0
fi

# ---------------------------------------------------------------- preflight
for cmd in grim hyprctl jq; do
  command -v "$cmd" >/dev/null || die "$cmd is not installed."
done
[[ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ]] || die "not running under Hyprland (this script uses hyprctl)."
mkdir -p "$OUT_DIR"

# Match on title first (pywebview sets it to 'Atlas'), fall back to any atlas-ish class.
find_window() {
  hyprctl clients -j | jq -r '
    [ .[] | select((.title == "Atlas") or (.class | ascii_downcase | test("atlas"))) ][0]
    | if . == null then empty else .address end'
}

info "Looking for the Atlas window…"
ADDR="$(find_window || true)"
if [[ -z "$ADDR" ]]; then
  info "Not found. Start it now — e.g.  atlas --logs  — I'll wait up to 60s."
  for _ in $(seq 60); do
    sleep 1
    ADDR="$(find_window || true)"
    [[ -n "$ADDR" ]] && break
  done
fi
[[ -n "$ADDR" ]] || die "no Atlas window appeared."
ok "Found Atlas at $ADDR"

# Remember the terminal so we can hand focus back between shots.
TERM_ADDR="$(hyprctl activewindow -j | jq -r '.address // empty')"

# ---------------------------------------------------------------- window setup
ORIG_ROUNDING="$(hyprctl getoption decoration:rounding -j | jq -r '.int')"
ORIG_FLOATING="$(hyprctl clients -j | jq -r --arg a "$ADDR" '.[] | select(.address==$a) | .floating')"

restore() {
  hyprctl keyword decoration:rounding "$ORIG_ROUNDING" >/dev/null 2>&1 || true
  if [[ "$ORIG_FLOATING" == "false" ]]; then
    hyprctl dispatch settiled "address:$ADDR" >/dev/null 2>&1 || true
  fi
  printf '\n'
  info "Restored rounding=$ORIG_ROUNDING and the window's original tiling state."
}
trap restore EXIT

# Rounded corners would let the desktop behind bleed into the screenshot corners, so square
# them off for the duration. hyprctl keyword is runtime-only — nothing touches your config.
hyprctl keyword decoration:rounding 0 >/dev/null
hyprctl dispatch setfloating "address:$ADDR" >/dev/null
hyprctl dispatch resizewindowpixel "exact $WIDTH $HEIGHT,address:$ADDR" >/dev/null
# centerwindow acts on the *active* window, so focus Atlas before centering it.
hyprctl dispatch focuswindow "address:$ADDR" >/dev/null
hyprctl dispatch centerwindow >/dev/null 2>&1 || true
sleep 0.4
ok "Window floated and sized to ${WIDTH}×${HEIGHT}."

# ---------------------------------------------------------------- capture
capture() {
  local name="$1" tmp geom w h
  # Re-read geometry every time: the window may have been nudged between shots.
  geom="$(hyprctl clients -j | jq -r --arg a "$ADDR" '
    .[] | select(.address==$a) | "\(.at[0]),\(.at[1]) \(.size[0])x\(.size[1])"')"
  [[ -n "$geom" ]] || die "lost the Atlas window (did it close?)."

  # Raise + focus so nothing overlaps it — grim captures the screen, not the surface.
  hyprctl dispatch focuswindow "address:$ADDR" >/dev/null
  hyprctl dispatch bringactivetotop >/dev/null 2>&1 || true
  sleep 0.5

  tmp="$(mktemp --suffix=.png)"
  if ! grim -g "$geom" "$tmp" 2>/dev/null; then
    rm -f "$tmp"; printf '\033[31m  capture failed\033[0m\n'; return 1
  fi
  # Only clobber a good existing screenshot once the new one is known-good.
  mv "$tmp" "$OUT_DIR/$name.png"
  ok "$(printf '%-12s → docs/screenshots/%s.png  (%s, %s)' \
        "$name" "$name" "${geom#* }" "$(du -h "$OUT_DIR/$name.png" | cut -f1)")"

  # Give focus back so you can hit Enter without clicking around.
  [[ -n "$TERM_ADDR" ]] && hyprctl dispatch focuswindow "address:$TERM_ADDR" >/dev/null 2>&1 || true
}

# Build the worklist: all shots, or just the ones named on the command line.
WORK=()
if [[ $# -gt 0 ]]; then
  for want in "$@"; do
    match=""
    for s in "${SHOTS[@]}"; do [[ "${s%%|*}" == "$want" ]] && match="$s"; done
    [[ -n "$match" ]] || die "unknown shot '$want'. Try --list."
    WORK+=("$match")
  done
else
  WORK=("${SHOTS[@]}")
fi

printf '\n'
info "For each shot: set the app up, then press Enter here. (s = skip, q = quit)"
printf '\n'

for s in "${WORK[@]}"; do
  name="${s%%|*}"; what="${s#*|}"
  printf '\033[1m%s\033[0m — %s\n' "$name" "$what"
  printf '  [Enter] capture · [s] skip · [q] quit: '
  read -r reply </dev/tty
  case "$reply" in
    q|Q) info "Stopping here."; break ;;
    s|S) printf '  skipped\n\n'; continue ;;
    *)   capture "$name" || true; printf '\n' ;;
  esac
done

printf '\n'
info "Current screenshots:"
ls -la "$OUT_DIR"/*.png 2>/dev/null | awk '{printf "   %-10s %s\n", $5, $NF}'
printf '\n'
info "Check them into git when you're happy:  git add docs/screenshots && git commit"
