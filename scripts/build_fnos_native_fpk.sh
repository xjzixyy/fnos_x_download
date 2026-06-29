#!/bin/sh
set -eu

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DIST_DIR="$ROOT_DIR/dist/fnos-native"
APP_NAME="xdownload"

if ! command -v fnpack >/dev/null 2>&1; then
  echo "fnpack not found. Please run this script on a fnOS machine with fnpack installed." >&2
  exit 1
fi

mkdir -p "$DIST_DIR"

cd "$DIST_DIR"
fnpack create "$APP_NAME"

rm -rf "$APP_NAME/app"
cp -R "$ROOT_DIR/packaging/fnos-native/app" "$APP_NAME/app"
cp "$ROOT_DIR/packaging/fnos-native/cmd/main" "$APP_NAME/cmd/main"
cp "$ROOT_DIR/packaging/fnos-native/manifest" "$APP_NAME/manifest"
cp "$ROOT_DIR/packaging/fnos-native/ICON.PNG" "$APP_NAME/ICON.PNG"
cp "$ROOT_DIR/packaging/fnos-native/ICON.PNG" "$APP_NAME/ICON_256.PNG"
cp "$ROOT_DIR/packaging/fnos-native/config/privilege" "$APP_NAME/config/privilege"
cp "$ROOT_DIR/packaging/fnos-native/config/resource" "$APP_NAME/config/resource"

cp "$ROOT_DIR/main.py" "$APP_NAME/app/main.py"
cp -R "$ROOT_DIR/xdownload" "$APP_NAME/app/xdownload"
cp "$ROOT_DIR/README.md" "$APP_NAME/app/README.md"

find "$APP_NAME/app/bin" -type f -name "*.sh" -exec chmod 755 {} \;
chmod 755 "$APP_NAME/app/ui/index.cgi"
chmod 755 "$APP_NAME/cmd/main"

cd "$APP_NAME"
fnpack build

if [ -f "$APP_NAME.fpk" ]; then
  cp "$APP_NAME.fpk" "$DIST_DIR/$APP_NAME.fpk"
elif [ -f "../$APP_NAME.fpk" ]; then
  cp "../$APP_NAME.fpk" "$DIST_DIR/$APP_NAME.fpk"
fi

if [ -f "$DIST_DIR/$APP_NAME.fpk" ]; then
  echo "Built: $DIST_DIR/$APP_NAME.fpk"
else
  echo "fnpack build finished, but $APP_NAME.fpk was not found under $DIST_DIR." >&2
  exit 1
fi
