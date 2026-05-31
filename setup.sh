#!/usr/bin/env bash
# RepoSense setup — installs Coral, connects all sources, installs reposense.
# Run once after cloning: bash setup.sh
set -e

BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
CYAN="\033[0;36m"
RESET="\033[0m"

step() { echo -e "\n${BOLD}${CYAN}▶ $1${RESET}"; }
ok()   { echo -e "${GREEN}✓ $1${RESET}"; }
warn() { echo -e "${YELLOW}! $1${RESET}"; }

echo -e "${BOLD}"
echo "  ██████╗ ███████╗██████╗  ██████╗ ███████╗███████╗███╗   ██╗███████╗███████╗"
echo "  ██╔══██╗██╔════╝██╔══██╗██╔═══██╗██╔════╝██╔════╝████╗  ██║██╔════╝██╔════╝"
echo "  ██████╔╝█████╗  ██████╔╝██║   ██║███████╗█████╗  ██╔██╗ ██║███████╗█████╗  "
echo "  ██╔══██╗██╔══╝  ██╔═══╝ ██║   ██║╚════██║██╔══╝  ██║╚██╗██║╚════██║██╔══╝  "
echo "  ██║  ██║███████╗██║     ╚██████╔╝███████║███████╗██║ ╚████║███████║███████╗"
echo "  ╚═╝  ╚═╝╚══════╝╚═╝      ╚═════╝ ╚══════╝╚══════╝╚═╝  ╚═══╝╚══════╝╚══════╝"
echo -e "${RESET}"
echo "  GitHub intelligence for any repo — 12 commands, 6 live data sources."
echo ""

# ── 1. Check / install Coral ───────────────────────────────────────────────
step "Checking Coral installation"
if command -v coral &>/dev/null; then
    ok "Coral already installed ($(coral --version 2>/dev/null || echo 'version unknown'))"
else
    warn "Coral not found — installing now..."
    curl -fsSL https://withcoral.com/install.sh | sh
    # Add to PATH for the rest of this script
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    if ! command -v coral &>/dev/null; then
        echo "Coral installed — please open a new terminal and re-run: bash setup.sh"
        exit 0
    fi
    ok "Coral installed"
fi

# ── 2. Connect GitHub ──────────────────────────────────────────────────────
step "Connecting GitHub source"
echo "  You need a GitHub Personal Access Token with these scopes:"
echo "  → repo (read)   read:org   security_events (for Dependabot alerts)"
echo "  Get one at: GitHub → Settings → Developer settings → Personal access tokens"
echo ""
if coral source list 2>/dev/null | grep -q "^github"; then
    ok "GitHub source already connected"
else
    coral source add --interactive github
    ok "GitHub connected"
fi

# ── 3. Add community sources ───────────────────────────────────────────────
step "Adding data sources"

add_source() {
    local name="$1"
    local file="$2"
    if coral source list 2>/dev/null | grep -q "^$name"; then
        ok "$name already installed — skipping"
    else
        coral source add --file "$file"
        ok "$name connected"
    fi
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

add_source "hn"            "$SCRIPT_DIR/sources/hn/manifest.yaml"
add_source "osv"           "$SCRIPT_DIR/sources/osv/manifest.yaml"
add_source "stackoverflow" "$SCRIPT_DIR/sources/stackoverflow/manifest.yaml"
add_source "devto"         "$SCRIPT_DIR/sources/devto/manifest.yaml"
add_source "scorecard"     "$SCRIPT_DIR/sources/scorecard/manifest.yaml"

# ── 4. Install RepoSense ───────────────────────────────────────────────────
step "Installing RepoSense"
if ! command -v uv &>/dev/null; then
    warn "uv not found — installing now (fast Python package manager)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"
fi
if command -v uv &>/dev/null; then
    uv tool install . --reinstall-package reposense 2>/dev/null || uv tool install .
    export PATH="$HOME/.local/bin:$PATH"
    ok "reposense installed (uv)"
else
    warn "uv install failed — falling back to pip install -e ."
    pip install -e . --quiet
    ok "reposense installed (pip)"
fi

# ── 5. Create .env ─────────────────────────────────────────────────────────
step "Setting up configuration"
if [ -f "$SCRIPT_DIR/.env" ]; then
    ok ".env already exists — skipping"
else
    cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
    ok "Created .env from .env.example"
    warn "Edit .env to add LLM API keys for agent mode (optional)"
fi

# ── Done ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "${BOLD}${GREEN}  Setup complete!${RESET}"
echo -e "${BOLD}${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo ""
echo "  Try it now:"
echo ""
echo "    reposense --repo withcoral/coral triage"
echo "    reposense --repo django/django health"
echo "    reposense --repo expressjs/express scorecard"
echo ""
echo "  Interactive mode (AI agent):"
echo "    reposense --repo withcoral/coral"
echo ""
echo "  Edit .env to add ANTHROPIC_API_KEY / GROQ_API_KEY for AI mode."
echo ""
