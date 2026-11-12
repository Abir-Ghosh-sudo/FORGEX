#!/usr/bin/env bash
set -Eeuo pipefail
REPO_URL="https://github.com/Abir-Ghosh-sudo/FORGEX/archive/refs/heads/main.tar.gz"
INSTALL_ROOT="\${XDG_DATA_HOME:-$HOME/.local/share}/forgex"
BIN_DIR="\${XDG_BIN_HOME:-$HOME/.local/bin}"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
echo "=== FORGEX Installer ==="
PYTHON=""
for candidate in python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3, 11))'; then PYTHON="$candidate"; break; fi
done
if [[ -z "$PYTHON" ]]; then echo "Python 3.11 or newer is required. Install Python and retry." >&2; exit 1; fi
echo "Using $("$PYTHON" --version)"
echo "Downloading FORGEX..."
curl -fsSL "$REPO_URL" -o "$TMP_DIR/forgex.tar.gz"
mkdir -p "$TMP_DIR/source"
tar -xzf "$TMP_DIR/forgex.tar.gz" -C "$TMP_DIR/source"
SOURCE_DIR="$(find "$TMP_DIR/source" -mindepth 1 -maxdepth 1 -type d -name 'FORGEX-*' -print -quit)"
[[ -n "$SOURCE_DIR" ]] || { echo "Could not extract FORGEX source." >&2; exit 1; }
mkdir -p "$(dirname "$INSTALL_ROOT")"
rm -rf "$INSTALL_ROOT"
mv "$SOURCE_DIR" "$INSTALL_ROOT"
echo "Creating virtual environment..."
"$PYTHON" -m venv "$INSTALL_ROOT/.venv"
VENV_PYTHON="$INSTALL_ROOT/.venv/bin/python"
echo "Installing FORGEX..."
"$VENV_PYTHON" -m pip install --upgrade pip
"$VENV_PYTHON" -m pip install "$INSTALL_ROOT"
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/forgex" <<EOF
#!/usr/bin/env bash
exec "$VENV_PYTHON" -m forgex.cli.app "\$@"
EOF
chmod +x "$BIN_DIR/forgex"
case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *)
        PROFILE="$HOME/.profile"
        touch "$PROFILE"
        if ! grep -Fq 'export PATH="$HOME/.local/bin:$PATH"' "$PROFILE"; then printf '\n# FORGEX CLI\nexport PATH="$HOME/.local/bin:$PATH"\n' >> "$PROFILE"; fi
        export PATH="$BIN_DIR:$PATH"
        ;;
esac
"$BIN_DIR/forgex" --version
echo "FORGEX installed successfully! Run: forgex doctor"
echo "If command is not found, open a new terminal or run: source ~/.profile"
