#!/usr/bin/env bash
# Sincroniza los providers del índice federado y regenera el catálogo del frontend.
# Se ejecuta desde el timer systemd recursos-sync.timer.
set -euo pipefail

APP_DIR="/opt/recursos-api"
CATALOG_DIR="/tmp/recursos-catalog"
WWW_DATA="/var/www/recursos/data"
LEGACY_GAMES="$APP_DIR/data/games-legacy.json"

cd "$APP_DIR"
PY="$APP_DIR/.venv/bin/python"

for provider in jclic h5p eduhoot; do
  echo "[sync] $provider"
  "$PY" -m app.cli sync "$provider"
done

echo "[export-catalog]"
"$PY" -m app.cli export-catalog --games "$LEGACY_GAMES" --out-dir "$CATALOG_DIR"

cp "$CATALOG_DIR/games.json" "$WWW_DATA/games.json"
cp "$CATALOG_DIR/games-home.json" "$WWW_DATA/games-home.json"

echo "[done] $(date -Is)"
