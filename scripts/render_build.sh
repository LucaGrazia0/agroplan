#!/usr/bin/env bash
set -euo pipefail
python -m pip install -r backend/requirements-lock.txt
flutter_version=3.47.6
flutter_cache="${RENDER_FLUTTER_CACHE:-/opt/render/project/.cache/agroplan-flutter-$flutter_version}"
if [ ! -x "$flutter_cache/bin/flutter" ]; then
  mkdir -p "$(dirname "$flutter_cache")"
  git clone --depth 1 --branch "$flutter_version" https://github.com/flutter/flutter.git "$flutter_cache"
fi
export FLUTTER_BIN="$flutter_cache/bin/flutter"
"$FLUTTER_BIN" config --no-analytics
python scripts/build_web.py
