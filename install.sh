#!/usr/bin/env bash
# Instalador do Clipator para macOS e Linux.
#
#   curl -fsSL https://raw.githubusercontent.com/JBragon/clipator/main/install.sh | bash
#   ./install.sh                      (de dentro de uma cópia do repositório: instala o motor dela)
#
# Opções: --sim (não pergunta nada e não instala Claude Code nem Codex), --sem-app, --reinstalar-app, --sem-hyperframes, --sem-modelos, --sem-ia
# Variáveis: CLIPATOR_FONTE (de onde instalar o motor), CLIPATOR_WORKSPACE.
#
# Instala só para o seu usuário: uv, Python 3.12 isolado, o comando `clipator`,
# o HyperFrames e os modelos. Pede sudo apenas para o FFmpeg no Linux.
set -euo pipefail

# No Mac, o `curl | bash` costuma rodar sem locale UTF-8, e o bash 3.2 do sistema lê os
# acentos byte a byte. Toda variável colada num caractere acentuado vai entre chaves
# (${tag}…), e o locale vira UTF-8 para o resto do script e para os programas chamados.
if [ "$(uname -s)" = Darwin ]; then
  case "${LC_ALL:-${LC_CTYPE:-${LANG:-}}}" in
    *UTF-8*|*utf-8*|*UTF8*|*utf8*) ;;
    *) export LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 ;;
  esac
fi

REPO="JBragon/clipator"
HF_VERSAO="0.8.229"
NODE_MIN=22
BASE="$HOME/.clipator"

SIM=0; APP=1; REINSTALAR_APP=0; HF=1; MODELOS=1; IA=1
for a in "$@"; do
  case "$a" in
    --sim|-y) SIM=1 ;;
    --sem-app) APP=0 ;;
    --reinstalar-app) REINSTALAR_APP=1 ;;
    --sem-hyperframes) HF=0 ;;
    --sem-modelos) MODELOS=0 ;;
    --sem-ia) IA=0 ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "Opção desconhecida: $a" >&2; exit 2 ;;
  esac
done
[ "${CLIPATOR_SIM:-}" = "1" ] && SIM=1
[ "${CLIPATOR_REINSTALAR_APP:-}" = "1" ] && REINSTALAR_APP=1

# ---- tela -------------------------------------------------------------------
# Num terminal, cada etapa vira uma linha com ✓ e a etapa atual fica numa barra que se
# atualiza no lugar. A saída dos comandos vai para ~/.clipator/instalacao.log. Fora de
# um terminal (CI, saída redirecionada) ou com CLIPATOR_SIMPLES=1, a saída é a de sempre.
mkdir -p "$BASE"
LOG="$BASE/instalacao.log"
: > "$LOG"
UI=0
if [ -t 1 ] && [ -z "${CI:-}" ] && [ "${TERM:-dumb}" != dumb ] && [ "${CLIPATOR_SIMPLES:-}" != 1 ]; then UI=1; fi
TOTAL=$((6 + HF + MODELOS + IA + APP))
N=0; ETAPA=""; DETALHE=""; ETAPA_AVISO=0; GIRO=0
GIROS=(⠋ ⠙ ⠹ ⠸ ⠼ ⠴ ⠦ ⠧ ⠇ ⠏)

colunas() { local c; c="$(tput cols 2>/dev/null || echo 80)"; [ "$c" -gt 20 ] 2>/dev/null || c=80; echo "$c"; }

desenhar() {  # a linha da etapa atual: giro, barra, n/total, nome e detalhe
  [ "$UI" = 1 ] && [ -n "$ETAPA" ] || return 0
  local largura=20 cheio=$(( (N - 1) * 20 / TOTAL )) barra="" i
  for ((i = 0; i < largura; i++)); do if [ "$i" -lt "$cheio" ]; then barra+="█"; else barra+="░"; fi; done
  local txt="$ETAPA"; [ -n "$DETALHE" ] && txt="$ETAPA · $DETALHE"
  local max=$(( $(colunas) - 36 )); [ "$max" -lt 10 ] && max=10
  [ "${#txt}" -gt "$max" ] && txt="${txt:0:$((max - 1))}…"
  printf '\r\033[K  \033[35m%s\033[0m \033[35m%s\033[0m \033[2m%2d/%d\033[0m  %s' \
    "${GIROS[$((GIRO % 10))]}" "$barra" "$N" "$TOTAL" "$txt"
}

limpar_linha() { [ "$UI" = 1 ] && printf '\r\033[K'; return 0; }

fechar_etapa() {  # troca a barra pela linha final da etapa
  [ -n "$ETAPA" ] || return 0
  if [ "$UI" = 1 ]; then
    limpar_linha
    if [ "$ETAPA_AVISO" = 1 ]; then printf '  \033[33m!\033[0m %s\n' "$ETAPA"
    else printf '  \033[32m✓\033[0m %s\n' "$ETAPA"; fi
  fi
  ETAPA=""
}

banner() {
  [ "$UI" = 1 ] || return 0
  printf '\033[35m'
  cat <<'ARTE'

     ____ _     ___ ____   _  _____ ___  ____
    / ___| |   |_ _|  _ \ / \|_   _/ _ \|  _ \
   | |   | |    | || |_) / _ \ | || | | | |_) |
   | |___| |___ | ||  __/ ___ \| || |_| |  _ <
    \____|_____|___|_| /_/   \_\_| \___/|_| \_\

ARTE
  printf '\033[0m   \033[1mClips curtos de vídeos longos, de graça e na sua máquina\033[0m\n'
  printf '   \033[2mDetalhes da instalação: %s\033[0m\n\n' "$LOG"
}

passo() {
  printf '\n==> %s\n' "$*" >> "$LOG"
  if [ "$UI" = 1 ]; then
    fechar_etapa
    N=$((N + 1)); ETAPA="$*"; DETALHE=""; ETAPA_AVISO=0
    desenhar
  else
    printf '\n\033[1;35m==>\033[0m \033[1m%s\033[0m\n' "$*"
  fi
}
info() {
  printf '    %s\n' "$*" >> "$LOG"
  if [ "$UI" = 1 ] && [ -n "$ETAPA" ]; then DETALHE="$*"; desenhar; else printf '    %s\n' "$*"; fi
}
aviso() {
  printf '    Aviso: %s\n' "$*" >> "$LOG"
  ETAPA_AVISO=1
  limpar_linha
  printf '\033[33m    Aviso: %s\033[0m\n' "$*"
  desenhar
}
falha() {
  printf 'Erro: %s\n' "$*" >> "$LOG"
  if [ "$UI" = 1 ]; then
    limpar_linha
    [ -n "$ETAPA" ] && printf '  \033[31m✗\033[0m %s\n' "$ETAPA"
    printf '\n\033[2m    Últimas linhas de %s:\033[0m\n' "$LOG"
    tail -n 15 "$LOG" | sed 's/^/    /'
  fi
  printf '\n\033[31mErro: %s\033[0m\n' "$*" >&2
  exit 1
}
tem()   { command -v "$1" >/dev/null 2>&1; }

# Verificação: cada item termina com um estado, mostrado no fim. Rodar o instalador de
# novo confere tudo outra vez e só instala o que falta.
VERIF=()
marcar() {  # marcar ok|novo|aviso ITEM DETALHE
  local m
  case "$1" in
    ok) m="\033[32m✓\033[0m" ;; novo) m="\033[32m✓\033[0m" ;; *) m="\033[33m!\033[0m" ;;
  esac
  VERIF+=("$(printf '  %b %-22s \033[2m%s\033[0m' "$m" "$2" "$3")")
  printf '    [%s] %s: %s\n' "$1" "$2" "$3" >> "$LOG"
}

# rodar COMANDO…: no terminal, a saída vai para o log e a barra gira enquanto espera.
rodar() {
  printf '$ %s\n' "$*" >> "$LOG"
  if [ "$UI" != 1 ]; then "$@"; return; fi
  "$@" >> "$LOG" 2>&1 < /dev/null &
  local pid=$!
  while kill -0 "$pid" 2>/dev/null; do GIRO=$((GIRO + 1)); desenhar; sleep 0.1; done
  wait "$pid"
}

# Perguntas leem do terminal, mesmo quando o script chega por `curl | bash`.
perguntar() {
  [ "$SIM" = 1 ] && return 0
  local r=""
  if [ -r /dev/tty ]; then
    limpar_linha
    printf '    %s [S/n] ' "$1" > /dev/tty
    read -r r < /dev/tty || r=""
    desenhar
  fi
  case "$r" in n|N|nao|não|no) return 1 ;; *) return 0 ;; esac
}

baixar() {  # baixar URL DESTINO
  if tem curl; then curl -fsSL --retry 3 "$1" -o "$2"; else wget -q "$1" -O "$2"; fi
}

# ---- 1. sistema --------------------------------------------------------------
banner
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
UV_ANTES=0; tem uv && UV_ANTES=1
if ! tem uv; then
  info "Instalando o uv…"
  rodar bash -o pipefail -c 'curl -LsSf https://astral.sh/uv/install.sh | sh' || falha "não consegui instalar o uv."
  tem uv || falha "o uv não ficou disponível. Abra um terminal novo e rode o instalador de novo."
fi
info "$(uv --version)"
if [ "$UV_ANTES" = 1 ]; then marcar ok "uv e Python" "$(uv --version | cut -d' ' -f2) · já estava instalado"
else marcar novo "uv e Python" "$(uv --version | cut -d' ' -f2) · instalado agora"; fi

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
FF_ANTES=0; ffmpeg_ok && FF_ANTES=1
DENO_ANTES=0; tem deno && DENO_ANTES=1
NODE_ANTES=0; node_ok && NODE_ANTES=1
if [ "$SO" = mac ]; then
  if ! tem brew; then
    falha "o Homebrew é necessário no Mac. Instale em https://brew.sh e rode este instalador de novo."
  fi
  ffmpeg_ok || { info "Instalando o FFmpeg completo (com legendas)…"; rodar brew install ffmpeg-full || aviso "o brew não instalou o FFmpeg."; }
  tem deno  || { info "Instalando o Deno…"; rodar brew install deno || aviso "o brew não instalou o Deno."; }
  if [ "$HF" = 1 ] && ! node_ok; then info "Instalando o Node.js…"; rodar brew install node || aviso "o brew não instalou o Node.js."; fi
else
  if ! ffmpeg_ok; then
    info "Instalando o FFmpeg (pede sua senha)…"
    if [ -n "$SUDO" ] && [ "$UI" = 1 ]; then limpar_linha; $SUDO -v < /dev/tty || true; desenhar; fi
    rodar instalar_pacote_linux ffmpeg || aviso "não consegui instalar o FFmpeg. Instale pelo gerenciador do seu sistema."
  fi
  if ! tem deno; then
    info "Instalando o Deno…"
    rodar bash -o pipefail -c 'curl -fsSL https://deno.land/install.sh | env DENO_INSTALL="$1" sh -s -- -y --no-modify-path' _ "$BASE/deno" \
      && ln -sf "$BASE/deno/bin/deno" "$HOME/.local/bin/deno" \
      || aviso "não consegui instalar o Deno. Sem ele, links do YouTube podem falhar."
  fi
  if [ "$HF" = 1 ] && ! node_ok; then
    info "Instalando o Node.js $NODE_MIN em $BASE/node…"
    rodar node_linux || aviso "não consegui instalar o Node.js. Os estilos animados vão sair com a legenda simples."
  fi
fi
ffmpeg_ok && info "FFmpeg com legendas: ok" || aviso "FFmpeg sem legendas. Rode 'clipator doctor' depois."
tem deno && info "Deno: $(deno --version | head -1)"
node_ok && info "Node.js: $(node --version)"
estado() {  # estado ANTES AGORA_OK ITEM DETALHE_SE_FALTA
  if [ "$2" = 1 ]; then
    if [ "$1" = 1 ]; then marcar ok "$3" "já estava instalado"; else marcar novo "$3" "instalado agora"; fi
  else marcar aviso "$3" "$4"; fi
}
AGORA=0; ffmpeg_ok && AGORA=1; estado "$FF_ANTES" "$AGORA" "FFmpeg com legendas" "falta · os clips saem sem legenda"
AGORA=0; tem deno && AGORA=1; estado "$DENO_ANTES" "$AGORA" "Deno" "falta · links do YouTube podem falhar"
if [ "$HF" = 1 ]; then
  AGORA=0; node_ok && AGORA=1; estado "$NODE_ANTES" "$AGORA" "Node.js $NODE_MIN+" "falta · estilos animados saem simples"
fi

# ---- 4. motor ---------------------------------------------------------------
passo "Motor do Clipator"
MOTOR_ANTES=""; tem clipator && MOTOR_ANTES="$(clipator --version 2>/dev/null || true)"
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
info "Instalando (pode levar alguns minutos)…"
rodar uv tool install --python 3.12 --force "$FONTE" || falha "o uv não conseguiu instalar o motor."
tem clipator || falha "o comando clipator não ficou no PATH. Abra um terminal novo e rode 'clipator doctor'."
MOTOR_AGORA="$(clipator --version 2>/dev/null || true)"
info "$MOTOR_AGORA"
if [ -z "$MOTOR_ANTES" ]; then marcar novo "Motor" "$MOTOR_AGORA · instalado agora"
elif [ "$MOTOR_ANTES" = "$MOTOR_AGORA" ]; then marcar ok "Motor" "$MOTOR_AGORA · conferido e atualizado"
else marcar novo "Motor" "$MOTOR_ANTES → $MOTOR_AGORA"; fi

# ---- 5. HyperFrames -----------------------------------------------------------
if [ "$HF" = 1 ]; then
  passo "HyperFrames (estilos animados)"
  HF_ANTES=0; [ -d "$BASE/hyperframes/node_modules/hyperframes" ] && HF_ANTES=1
  if node_ok && tem npm; then
    if rodar npm install --silent --no-fund --no-audit --prefix "$BASE/hyperframes" "hyperframes@$HF_VERSAO"; then
      info "HyperFrames $HF_VERSAO instalado."
      estado "$HF_ANTES" 1 "HyperFrames" ""
    else
      aviso "o npm falhou. Os estilos animados vão sair com a legenda simples."
      marcar aviso "HyperFrames" "o npm falhou · estilos animados saem simples"
    fi
  else
    aviso "sem Node.js $NODE_MIN+, pulei o HyperFrames."
    marcar aviso "HyperFrames" "sem Node.js $NODE_MIN+ · estilos animados saem simples"
  fi
fi

# ---- 6. workspace e modelos ---------------------------------------------------
passo "Workspace"
WS="${CLIPATOR_WORKSPACE:-$HOME/Clipator}"
WS_ANTES=0; [ -d "$WS" ] && WS_ANTES=1
rodar clipator init ${CLIPATOR_WORKSPACE:+"$CLIPATOR_WORKSPACE"} || falha "não consegui criar o workspace."
info "$WS"
if [ "$WS_ANTES" = 1 ]; then marcar ok "Workspace" "$WS · já existia"; else marcar novo "Workspace" "$WS · criado agora"; fi

if [ "$MODELOS" = 1 ]; then
  passo "Modelos (pode levar alguns minutos na primeira vez)"
  info "Baixando os modelos de transcrição e de rosto…"
  if rodar clipator preparar; then marcar ok "Modelos" "conferidos e prontos para usar offline"
  else
    aviso "parte dos downloads falhou. O Clipator baixa o que faltar no primeiro uso."
    marcar aviso "Modelos" "parte falhou · o que faltar vem no primeiro uso"
  fi
fi

# ---- 7. Claude Code e Codex ---------------------------------------------------
if [ "$IA" = 1 ]; then
  passo "IA (Claude Code ou Codex)"
  if ! tem claude && ! tem codex; then
    info "O Clipator funciona sem IA, mas fica melhor com o Claude Code ou o Codex da sua assinatura."
    if [ "$SIM" = 1 ]; then
      info "Para instalar depois: curl -fsSL https://claude.ai/install.sh | bash   (ou: npm install -g @openai/codex)"
    elif perguntar "Instalar o Claude Code agora?"; then
      info "Instalando o Claude Code…"
      rodar bash -o pipefail -c 'curl -fsSL https://claude.ai/install.sh | bash' || aviso "a instalação do Claude Code falhou."
    elif tem npm && perguntar "Instalar o Codex agora?"; then
      info "Instalando o Codex…"
      rodar npm install -g @openai/codex || aviso "a instalação do Codex falhou."
    fi
  fi
  MCP_OK=1
  rodar clipator mcp registrar || { MCP_OK=0; aviso "não consegui registrar o MCP. Rode 'clipator mcp registrar' depois."; }
  IAS=""; tem claude && IAS="Claude Code"; tem codex && IAS="${IAS:+$IAS e }Codex"
  if [ -z "$IAS" ]; then marcar aviso "IA" "nenhuma instalada · opcional, funciona sem"
  elif [ "$MCP_OK" = 1 ]; then marcar ok "IA" "$IAS · MCP registrado"
  else marcar aviso "IA" "$IAS · o MCP não foi registrado"; fi
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

# A versão instalada fica em ~/.clipator/app-versao ("v0.1.0 /caminho/do/app"). Se a release
# mais recente for a mesma e o app ainda estiver lá, o download é pulado.
VERSAO_APP="$BASE/app-versao"
APP_LOCAL=""
instalar_app() {
  local api="https://api.github.com/repos/$REPO/releases/latest" json url tmp tag antes="" destino=""
  json="$(curl -fsSL "$api" 2>/dev/null)" || return 1
  tag="$(printf '%s' "$json" | grep -o '"tag_name": *"[^"]*"' | head -1 | cut -d'"' -f4)"
  if [ "$REINSTALAR_APP" = 0 ] && [ -n "$tag" ] && [ -f "$VERSAO_APP" ]; then
    read -r antes destino < "$VERSAO_APP" || true
    if [ "$antes" = "$tag" ] && [ -n "$destino" ] && [ -e "$destino" ]; then
      APP_LOCAL="$destino"
      info "O app já está na versão mais recente ($tag). Para baixar de novo: --reinstalar-app"
      return 0
    fi
  fi
  if [ "$SO" = mac ]; then
    url="$(asset "$json" dmg)"; [ -n "$url" ] || return 1
    # /Applications é a pasta que o Finder mostra; sem permissão, fica em ~/Applications.
    if [ -w /Applications ]; then destino="/Applications/Clipator.app"
    else mkdir -p "$HOME/Applications"; destino="$HOME/Applications/Clipator.app"
    fi
    info "Baixando o app ${tag}…"
    tmp="$(mktemp -d)"; rodar baixar "$url" "$tmp/Clipator.dmg" || return 1
    local vol; vol="$(hdiutil attach -nobrowse -quiet "$tmp/Clipator.dmg" | awk -F'\t' 'END {print $NF}')"
    if [ -z "$vol" ] || [ ! -d "$vol/Clipator.app" ]; then
      [ -n "$vol" ] && hdiutil detach -quiet "$vol" 2>/dev/null
      rm -rf "$tmp"; return 1
    fi
    rm -rf "/Applications/Clipator.app" "$HOME/Applications/Clipator.app" 2>/dev/null || true
    if ! cp -R "$vol/Clipator.app" "$destino"; then hdiutil detach -quiet "$vol"; rm -rf "$tmp"; return 1; fi
    hdiutil detach -quiet "$vol" || true; rm -rf "$tmp"
    # O app ainda não é assinado pela Apple: sem a marca de quarentena e com assinatura
    # local (ad-hoc), o macOS abre o app sem dizer que ele "está danificado".
    xattr -dr com.apple.quarantine "$destino" 2>/dev/null || true
    codesign --verify "$destino" >/dev/null 2>&1 || codesign --force --deep --sign - "$destino" >/dev/null 2>&1 || true
  else
    url="$(asset "$json" AppImage)"; [ -n "$url" ] || return 1
    destino="$HOME/.local/bin/clipator-app"
    info "Baixando o app ${tag}…"
    rodar baixar "$url" "$destino" || return 1; chmod +x "$destino"
    local icone="$HOME/.local/share/icons/clipator.png"
    mkdir -p "$(dirname "$icone")" "$HOME/.local/share/applications"
    baixar "https://raw.githubusercontent.com/$REPO/${tag:-main}/app/resources/icon.png" "$icone" 2>/dev/null \
      || rm -f "$icone"
    cat > "$HOME/.local/share/applications/clipator.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Clipator
Comment=Clips curtos de vídeos longos
Exec=$destino
Icon=$icone
Terminal=false
Categories=AudioVideo;Video;
EOF
    if command -v update-desktop-database >/dev/null 2>&1; then
      update-desktop-database -q "$HOME/.local/share/applications" 2>/dev/null || true
    fi
  fi
  if [ -n "$tag" ]; then printf '%s %s\n' "$tag" "$destino" > "$VERSAO_APP"; fi
  APP_LOCAL="$destino"
  info "App $tag instalado."
}


RELEASES="https://github.com/$REPO/releases"
APP_OK=0
if [ "$APP" = 1 ]; then
  passo "App de desktop"
  APP_ANTES="$(cat "$VERSAO_APP" 2>/dev/null | cut -d' ' -f1 || true)"
  if instalar_app; then
    APP_OK=1
    APP_AGORA="$(cut -d' ' -f1 "$VERSAO_APP" 2>/dev/null || true)"
    if [ -n "$APP_ANTES" ] && [ "$APP_ANTES" = "$APP_AGORA" ] && [ "$REINSTALAR_APP" = 0 ]; then
      marcar ok "App de desktop" "$APP_AGORA · já estava na versão mais recente"
    else marcar novo "App de desktop" "${APP_AGORA:-instalado} · instalado agora"; fi
  else
    marcar aviso "App de desktop" "não instalado · baixe em $RELEASES"
    aviso "não consegui baixar o app de desktop. O motor foi instalado e o comando 'clipator' já funciona. Baixe o app em $RELEASES ou rode este instalador de novo mais tarde."
  fi
fi

passo "Conferindo a instalação"
DOCTOR_OK=1
DOCTOR="$(clipator doctor 2>&1)" || DOCTOR_OK=0
printf '%s\n' "$DOCTOR" >> "$LOG"
if [ "$DOCTOR_OK" = 1 ]; then marcar ok "clipator doctor" "tudo pronto"
else marcar aviso "clipator doctor" "faltam itens obrigatórios · veja abaixo"; fi
fechar_etapa
if [ "$UI" = 1 ]; then
  printf '\n  \033[32m████████████████████ Pronto!\033[0m\n'
fi
printf '\n  \033[1mVerificação\033[0m\n'
for l in "${VERIF[@]}"; do printf '%s\n' "$l"; done
# Num terminal, o relatório completo do doctor só aparece quando falta algo (está no log).
if [ "$UI" != 1 ] || [ "$DOCTOR_OK" = 0 ]; then printf '\n%s\n' "$DOCTOR"; fi
if [ "$APP" = 1 ] && [ "$APP_OK" = 0 ]; then
  printf '\n'
  aviso "o app de desktop NÃO foi instalado. Baixe em $RELEASES"
elif [ "$APP_OK" = 1 ]; then
  printf '\n'
  if [ "$SO" = mac ]; then
    info "Para abrir o app: procure \"Clipator\" no Launchpad ou no Spotlight (Cmd+Espaço). Ele fica em $APP_LOCAL"
  else
    info "Para abrir o app: procure \"Clipator\" no menu de aplicativos, ou rode clipator-app no terminal."
  fi
fi
cat <<EOF

    Para começar, abra o app ou use o canal de exemplo:
      clipator processar meu-canal "https://www.youtube.com/watch?v=..."
      clipator canal criar "Outro canal"

    Abra um terminal novo se o comando clipator não for encontrado.
    Para desinstalar: clipator desinstalar && uv tool uninstall clipator
EOF
