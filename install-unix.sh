#!/bin/sh
# Mingbird installer (macOS / Linux, experimental) · 鸣鸟安装脚本（macOS/Linux 实验版）
# Usage · 用法: sh install-unix.sh [target-dir]
set -e
DIR="${1:-$HOME/.local/share/Mingbird}"
SRC="$(cd "$(dirname "$0")" && pwd)/LocalAgent"
[ -d "$SRC" ] || { echo "LocalAgent/ not found next to this script · 未在脚本旁找到 LocalAgent/ 目录"; exit 1; }
mkdir -p "$DIR"
cp -r "$SRC/." "$DIR/"
chmod +x "$DIR/LocalAgent"

# desktop entry (Linux only · 仅 Linux)
if [ "$(uname)" = "Linux" ] && [ -d "$HOME/.local/share/applications" ]; then
  mkdir -p "$HOME/.local/share/applications"
  cat > "$HOME/.local/share/applications/mingbird.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=Mingbird
Comment=Local-first AI agent harness · 本地优先 AI agent
Exec=$DIR/LocalAgent
Icon=$DIR/app.png
Categories=Development;Utility;
DESK
fi

echo "Installed to · 已安装到: $DIR"
echo "Launch · 启动: \"$DIR/LocalAgent\""
echo "Note · 说明: requires Ollama (ollama.com). Microphone input · 麦克风输入:"
echo "  macOS: built-in   |   Linux: sudo apt install libportaudio2"
