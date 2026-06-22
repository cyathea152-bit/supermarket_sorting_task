#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
APP_BUNDLE="RobotSimControl"
APP_EXEC="$ROOT_DIR/dist/$APP_BUNDLE/$APP_BUNDLE"

if [[ -z "${CONDA_PREFIX:-}" ]]; then
  echo "ERROR: Please activate the robot simulation conda environment first."
  echo "Example: conda activate robot_sim"
  exit 1
fi

echo "Using conda environment: $CONDA_PREFIX"
echo "Python: $(python -c 'import sys; print(sys.executable)')"

python -m pip install -e .
python -m pip install pyinstaller
python -m PyInstaller --clean -y DISCOVERSE.spec

echo
echo "Checking packaged imports..."
"$APP_EXEC" --self-check

cat > "$ROOT_DIR/dist/$APP_BUNDLE/$APP_BUNDLE.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=机器人仿真智能控制系统
Comment=机器人仿真智能控制系统
Exec=$APP_EXEC
Path=$ROOT_DIR/dist/$APP_BUNDLE
Icon=$ROOT_DIR/dist/$APP_BUNDLE/_internal/scripts/assets/shentoon_window_icon.png
StartupWMClass=RobotSimControl
Terminal=false
Categories=Science;Education;Development;
EOF
chmod +x "$ROOT_DIR/dist/$APP_BUNDLE/$APP_BUNDLE.desktop"

echo
echo "Build complete:"
echo "  App executable: $APP_EXEC"
echo "  Desktop launcher: $ROOT_DIR/dist/$APP_BUNDLE/$APP_BUNDLE.desktop"
echo
echo "Do not run files from build/$APP_BUNDLE; that is PyInstaller's intermediate build directory."
