#!/usr/bin/env bash
set -Eeuo pipefail
REPO_URL="https://github.com/Abir-Ghosh-sudo/FORGEX/archive/refs/heads/main.tar.gz"
INSTALL_ROOT="\${XDG_DATA_HOME:-$HOME/.local/share}/forgex"
BIN_DIR="\${XDG_BIN_HOME:-$HOME/.local/bin}"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
WITH_OLLAMA=false
if [[ "${1:-}" == "--with-ollama" ]]; then WITH_OLLAMA=true; fi
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
"$VENV_PYTHON" -m pip install "${INSTALL_ROOT}[local]"
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
        if ! grep -Fq 'export PATH="$BIN_DIR:$PATH"' "$PROFILE"; then printf '\n# FORGEX CLI\nexport PATH="%s:$PATH"\n' "$BIN_DIR" >> "$PROFILE"; fi
        export PATH="$BIN_DIR:$PATH"
        ;;
esac
"$BIN_DIR/forgex" --version
if [[ "$WITH_OLLAMA" == true ]]; then
    if ! command -v curl >/dev/null 2>&1; then
        echo "curl is required to install Ollama." >&2
        exit 1
    fi
    echo "Installing Ollama (may request sudo)..."
    curl -fsSL https://ollama.com/install.sh | sh
    if ! command -v ollama >/dev/null 2>&1; then
        echo "Ollama installation finished. Open a new terminal, then run: ollama pull qwen2.5-coder:1.5b" >&2
        exit 1
    fi
    if ! ollama list >/dev/null 2>&1; then
        echo "Starting Ollama service..."
        nohup ollama serve >/tmp/forgex-ollama.log 2>&1 &
        for _ in $(seq 1 30); do
            sleep 1
            if ollama list >/dev/null 2>&1; then break; fi
        done
    fi
    ollama list >/dev/null 2>&1 || { echo "Ollama service did not start. Run ollama serve and retry the model setup." >&2; exit 1; }
    echo "Downloading lightweight default coding model (qwen2.5-coder:1.5b)..."
    ollama pull qwen2.5-coder:1.5b
    "$BIN_DIR/forgex" model use ollama qwen2.5-coder:1.5b
fi
echo "FORGEX installed successfully! Run: forgex doctor"
echo "If command is not found, open a new terminal or run: source ~/.profile"
