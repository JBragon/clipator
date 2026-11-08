#!/usr/bin/env bash
# Instalador do Clipator para macOS e Linux.
#
#   curl -fsSL https://raw.githubusercontent.com/JBragon/clipator/main/install.sh | bash
#   ./install.sh                      (de dentro de uma cópia do repositório: instala o motor dela)
#
# Opções: --sim (não pergunta nada e não instala Claude Code nem Codex), --sem-app, --sem-hyperframes, --sem-modelos, --sem-ia
# Variáveis: CLIPATOR_FONTE (de onde instalar o motor), CLIPATOR_WORKSPACE.
#
# Instala só para o seu usuário: uv, Python 3.12 isolado, o comando `clipator`,
# o HyperFrames e os modelos. Pede sudo apenas para o FFmpeg no Linux.
set -euo pipefail

REPO="JBragon/clipator"
HF_VERSAO="0.8.229"
NODE_MIN=22
BASE="$HOME/.clipator"

SIM=0; APP=1; HF=1; MODELOS=1; IA=1
for a in "$@"; do
  case "$a" in
    --sim|-y) SIM=1 ;;
    --sem-app) APP=0 ;;
    --sem-hyperframes) HF=0 ;;
    --sem-modelos) MODELOS=0 ;;
    --sem-ia) IA=0 ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "Opção desconhecida: $a" >&2; exit 2 ;;
  esac
done
[ "${CLIPATOR_SIM:-}" = "1" ] && SIM=1

passo() { printf '\n\033[1;35m==>\033[0m \033[1m%s\033[0m\n' "$*"; }
info()  { printf '    %s\n' "$*"; }
aviso() { printf '\033[33m    Aviso: %s\033[0m\n' "$*"; }
falha() { printf '\033[31mErro: %s\033[0m\n' "$*" >&2; exit 1; }
tem()   { command -v "$1" >/dev/null 2>&1; }

# Perguntas leem do terminal, mesmo quando o script chega por `curl | bash`.
perguntar() {
  [ "$SIM" = 1 ] && return 0
  local r=""
  if [ -r /dev/tty ]; then
    printf '    %s [S/n] ' "$1" > /dev/tty
    read -r r < /dev/tty || r=""
  fi
  case "$r" in n|N|nao|não|no) return 1 ;; *) return 0 ;; esac
}

baixar() {  # baixar URL DESTINO
  if tem curl; then curl -fsSL --retry 3 "$1" -o "$2"; else wget -q "$1" -O "$2"; fi
}

# ---- 1. sistema --------------------------------------------------------------
passo "Conferindo o sistema"
SO="$(uname -s)"; ARQ="$(uname -m)"
case "$SO" in
  Darwin) SO=mac ;;
  Linux)  SO=linux ;;
  *) falha "sistema $SO não suportado por este script. No Windows, use o install.ps1." ;;
esac
GPU="nenhuma (a transcrição roda na CPU com um modelo menor)"
if tem nvidia-smi && nvidia-smi -L >/dev/null 2>&1; then
  GPU="NVIDIA: $(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)"
elif [ "$SO" = mac ] && [ "$ARQ" = arm64 ]; then
  GPU="Apple Silicon (a transcrição roda na CPU, que é rápida nesses Macs)"
fi
LIVRE_GB=$(df -Pk "$HOME" | awk 'NR==2 {print int($4/1048576)}')
info "Sistema: $SO $ARQ"
info "GPU: $GPU"
info "Espaço livre: ${LIVRE_GB} GB"
[ "$LIVRE_GB" -lt 5 ] && aviso "menos de 5 GB livres. Os modelos e o Chrome do HyperFrames ocupam uns 3 GB."
mkdir -p "$BASE" "$HOME/.local/bin"
export PATH="$HOME/.local/bin:$BASE/node/bin:$PATH"

# ---- 2. uv (traz o Python 3.12 isolado) ---------------------------------------
passo "uv e Python"
if ! tem uv; then
  info "Instalando o uv…"
  curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null
  tem uv || falha "o uv não ficou disponível. Abra um terminal novo e rode o instalador de novo."
fi
info "$(uv --version)"

# ---- 3. FFmpeg, Deno e Node.js ----------------------------------------------
ffmpeg_ok() {
  local b=ffmpeg
  for d in /opt/homebrew/opt/ffmpeg-full/bin /usr/local/opt/ffmpeg-full/bin; do
    [ -x "$d/ffmpeg" ] && b="$d/ffmpeg"
  done
  local filtros; filtros="$("$b" -hide_banner -filters 2>/dev/null || true)"
  case "$filtros" in *" subtitles "*) return 0 ;; *) return 1 ;; esac
}

node_ok() {
  tem node || return 1
  local v; v="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)"
  [ "$v" -ge "$NODE_MIN" ]
}

SUDO=""; [ "$(id -u)" != 0 ] && tem sudo && SUDO="sudo"
instalar_pacote_linux() {
  if tem apt-get; then $SUDO apt-get update -qq && $SUDO apt-get install -y -qq "$@"
  elif tem dnf; then $SUDO dnf install -y "$@"
  elif tem pacman; then $SUDO pacman -S --noconfirm --needed "$@"
  elif tem zypper; then $SUDO zypper --non-interactive install "$@"
  else return 1; fi
}

node_linux() {  # Node.js 22 só para o usuário, em ~/.clipator/node
  local a; case "$ARQ" in x86_64) a=x64 ;; aarch64|arm64) a=arm64 ;; *) return 1 ;; esac
  local idx="https://nodejs.org/dist/latest-v${NODE_MIN}.x"
  local tmp; tmp="$(mktemp -d)"
  baixar "$idx/SHASUMS256.txt" "$tmp/SHASUMS256.txt"
  local arq; arq="$(awk -v a="linux-$a.tar.xz" '$2 ~ a"$" {print $2; exit}' "$tmp/SHASUMS256.txt")"
  [ -n "$arq" ] || return 1
  baixar "$idx/$arq" "$tmp/$arq"
  (cd "$tmp" && grep " $arq\$" SHASUMS256.txt | sha256sum -c - >/dev/null) || return 1
  rm -rf "$BASE/node" && mkdir -p "$BASE/node"
  tar -xJf "$tmp/$arq" -C "$BASE/node" --strip-components=1
  rm -rf "$tmp"
}

passo "FFmpeg, Deno e Node.js"
if [ "$SO" = mac ]; then
  if ! tem brew; then
    falha "o Homebrew é necessário no Mac. Instale em https://brew.sh e rode este instalador de novo."
  fi
  ffmpeg_ok || { info "Instalando o FFmpeg completo (com legendas)…"; brew install ffmpeg-full; }
  tem deno  || { info "Instalando o Deno…"; brew install deno; }
  if [ "$HF" = 1 ] && ! node_ok; then info "Instalando o Node.js…"; brew install node; fi
else
  if ! ffmpeg_ok; then
    info "Instalando o FFmpeg (pede sua senha)…"
    instalar_pacote_linux ffmpeg || aviso "não consegui instalar o FFmpeg. Instale pelo gerenciador do seu sistema."
  fi
  if ! tem deno; then
    info "Instalando o Deno…"
    curl -fsSL https://deno.land/install.sh | env DENO_INSTALL="$BASE/deno" sh -s -- -y --no-modify-path >/dev/null \
      && ln -sf "$BASE/deno/bin/deno" "$HOME/.local/bin/deno" \
      || aviso "não consegui instalar o Deno. Sem ele, links do YouTube podem falhar."
  fi
  if [ "$HF" = 1 ] && ! node_ok; then
    info "Instalando o Node.js $NODE_MIN em $BASE/node…"
    node_linux || aviso "não consegui instalar o Node.js. Os estilos animados vão sair com a legenda simples."
  fi
fi
ffmpeg_ok && info "FFmpeg com legendas: ok" || aviso "FFmpeg sem legendas. Rode 'clipator doctor' depois."
tem deno && info "Deno: $(deno --version | head -1)"
node_ok && info "Node.js: $(node --version)"

# ---- 4. motor ---------------------------------------------------------------
passo "Motor do Clipator"
DIR_SCRIPT=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
  DIR_SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi
if [ -n "${CLIPATOR_FONTE:-}" ]; then
  FONTE="$CLIPATOR_FONTE"
elif [ -n "$DIR_SCRIPT" ] && [ -f "$DIR_SCRIPT/motor/pyproject.toml" ]; then
  FONTE="$DIR_SCRIPT/motor[visao]"
elif tem git; then
  FONTE="clipator[visao] @ git+https://github.com/$REPO#subdirectory=motor"
else
  FONTE="clipator[visao] @ https://github.com/$REPO/archive/refs/heads/main.zip#subdirectory=motor"
fi
info "Origem: $FONTE"
uv tool install --python 3.12 --force "$FONTE"
tem clipator || falha "o comando clipator não ficou no PATH. Abra um terminal novo e rode 'clipator doctor'."
info "$(clipator --version)"

# ---- 5. HyperFrames -----------------------------------------------------------
if [ "$HF" = 1 ]; then
  passo "HyperFrames (estilos animados)"
  if node_ok && tem npm; then
    npm install --silent --no-fund --no-audit --prefix "$BASE/hyperframes" "hyperframes@$HF_VERSAO" \
      && info "HyperFrames $HF_VERSAO instalado." \
      || aviso "o npm falhou. Os estilos animados vão sair com a legenda simples."
  else
    aviso "sem Node.js $NODE_MIN+, pulei o HyperFrames."
  fi
fi

# ---- 6. workspace e modelos ---------------------------------------------------
passo "Workspace"
clipator init ${CLIPATOR_WORKSPACE:+"$CLIPATOR_WORKSPACE"}

if [ "$MODELOS" = 1 ]; then
  passo "Modelos (pode levar alguns minutos na primeira vez)"
  clipator preparar || aviso "parte dos downloads falhou. O Clipator baixa o que faltar no primeiro uso."
fi

# ---- 7. Claude Code e Codex ---------------------------------------------------
if [ "$IA" = 1 ]; then
  passo "IA (Claude Code ou Codex)"
  if ! tem claude && ! tem codex; then
    info "O Clipator funciona sem IA, mas fica melhor com o Claude Code ou o Codex da sua assinatura."
    if [ "$SIM" = 1 ]; then
      info "Para instalar depois: curl -fsSL https://claude.ai/install.sh | bash   (ou: npm install -g @openai/codex)"
    elif perguntar "Instalar o Claude Code agora?"; then
      curl -fsSL https://claude.ai/install.sh | bash || aviso "a instalação do Claude Code falhou."
    elif tem npm && perguntar "Instalar o Codex agora?"; then
      npm install -g @openai/codex || aviso "a instalação do Codex falhou."
    fi
  fi
  clipator mcp registrar || aviso "não consegui registrar o MCP. Rode 'clipator mcp registrar' depois."
  tem claude && info "Para entrar na sua conta: rode 'claude' uma vez."
  tem codex && info "Para entrar na sua conta: rode 'codex login' uma vez."
fi

# ---- 8. app de desktop ---------------------------------------------------------
# O electron-builder põe "-arm64" no nome dos pacotes ARM; o de Intel/x64 fica sem sufixo.
asset() {  # asset JSON EXTENSAO
  local todos; todos="$(printf '%s' "$1" | grep -o "\"browser_download_url\": *\"[^\"]*\\.$2\"" | cut -d'"' -f4)"
  case "$ARQ" in
    arm64|aarch64) printf '%s\n' "$todos" | grep -E 'arm64|universal' | head -1 ;;
    *) printf '%s\n' "$todos" | grep -v arm64 | head -1 ;;
  esac
}

instalar_app() {
  local api="https://api.github.com/repos/$REPO/releases/latest" json url tmp
  json="$(curl -fsSL "$api" 2>/dev/null)" || return 1
  if [ "$SO" = mac ]; then
    url="$(asset "$json" dmg)"; [ -n "$url" ] || return 1
    tmp="$(mktemp -d)"; baixar "$url" "$tmp/Clipator.dmg"
    local vol; vol="$(hdiutil attach -nobrowse -quiet "$tmp/Clipator.dmg" | awk -F'\t' 'END {print $NF}')"
    mkdir -p "$HOME/Applications"; rm -rf "$HOME/Applications/Clipator.app"
    cp -R "$vol/Clipator.app" "$HOME/Applications/"
    hdiutil detach -quiet "$vol"; rm -rf "$tmp"
    info "App instalado em ~/Applications/Clipator.app"
  else
    url="$(asset "$json" AppImage)"; [ -n "$url" ] || return 1
    baixar "$url" "$HOME/.local/bin/clipator-app"; chmod +x "$HOME/.local/bin/clipator-app"
    mkdir -p "$HOME/.local/share/applications"
    cat > "$HOME/.local/share/applications/clipator.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Clipator
Comment=Clips curtos de vídeos longos
Exec=$HOME/.local/bin/clipator-app
Terminal=false
Categories=AudioVideo;Video;
EOF
    info "App instalado: procure 'Clipator' no menu, ou rode clipator-app."
  fi
}

if [ "$APP" = 1 ]; then
  passo "App de desktop"
  instalar_app || info "Ainda não há um app publicado para baixar. Por enquanto, use o comando 'clipator' ou rode o app pelo código (veja o README)."
fi

passo "Pronto"
clipator doctor || true
cat <<EOF

    Para começar, abra o app ou use o canal de exemplo:
      clipator processar meu-canal "https://www.youtube.com/watch?v=..."
      clipator canal criar "Outro canal"

    Abra um terminal novo se o comando clipator não for encontrado.
    Para desinstalar: clipator desinstalar && uv tool uninstall clipator
EOF
