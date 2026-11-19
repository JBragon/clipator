// Atualização do Clipator: ao abrir, o app pergunta ao GitHub qual é a release mais recente.
//
// Se houver versão nova, a interface pergunta "Atualizar agora / Depois". Atualizar fecha o
// app e roda o instalador oficial (install.ps1 ou install.sh) da tag nova numa janela de
// terminal: ele atualiza o motor (uv tool) e o app de desktop, e o script abre o Clipator de
// novo no fim. Não usa o electron-updater porque ele só atualiza o app (o motor ficaria
// velho) e, no Mac, só funciona com o app assinado, coisa que as releases ainda não são.
//
// Este arquivo só tem a lógica pura (versões, releases, scripts), testada em atualizacao.test.ts.

import type { Plataforma } from './caminho'

export const REPO = 'JBragon/clipator'
export const URL_RELEASE_MAIS_RECENTE = `https://api.github.com/repos/${REPO}/releases/latest`

export type Asset = { name: string; browser_download_url?: string }
export type Release = { tag_name?: string; html_url?: string; draft?: boolean; prerelease?: boolean; assets?: Asset[] }
export type Atualizacao = { atual: string; nova: string; tag: string; pagina: string }

// "v0.1.10" > "0.1.9". Pedaços que não são número (como "-beta") contam como 0.
export function compararVersoes(a: string, b: string): number {
  const partes = (v: string): number[] =>
    v.trim().replace(/^v/i, '').split(/[-+]/)[0].split('.').map((p) => Number.parseInt(p, 10) || 0)
  const x = partes(a)
  const y = partes(b)
  for (let i = 0; i < Math.max(x.length, y.length); i++) {
    const d = (x[i] ?? 0) - (y[i] ?? 0)
    if (d) return d > 0 ? 1 : -1
  }
  return 0
}

// O mesmo critério dos instaladores: .exe no Windows, .dmg no Mac, .AppImage no Linux.
// Enquanto a release ainda está sendo montada pelo GitHub Actions, o pacote do sistema
// pode não ter subido; nesse caso o app não oferece a atualização ainda.
export function temPacote(assets: Asset[], plataforma: Plataforma): boolean {
  const ext = plataforma === 'win32' ? '.exe' : plataforma === 'darwin' ? '.dmg' : '.appimage'
  return assets.some((a) => a.name.toLowerCase().endsWith(ext))
}

export function avaliarRelease(r: Release, versaoAtual: string, plataforma: Plataforma): Atualizacao | null {
  const tag = String(r.tag_name ?? '').trim()
  if (!tag || r.draft || r.prerelease || !/^v?\d+(\.\d+)*$/.test(tag)) return null
  if (compararVersoes(tag, versaoAtual) <= 0) return null
  if (!temPacote(r.assets ?? [], plataforma)) return null
  return {
    atual: versaoAtual.replace(/^v/i, ''),
    nova: tag.replace(/^v/i, ''),
    tag,
    pagina: r.html_url || `https://github.com/${REPO}/releases/tag/${tag}`
  }
}

// O motor vem do código da mesma tag (o zip do GitHub não precisa de git instalado).
export const fonteMotor = (tag: string): string =>
  `clipator[visao] @ https://github.com/${REPO}/archive/refs/tags/${tag}.zip#subdirectory=motor`

const instalador = (tag: string, arquivo: string): string => `https://raw.githubusercontent.com/${REPO}/${tag}/${arquivo}`

const aspasPs = (s: string): string => `'${s.replace(/'/g, "''")}'`
const aspasSh = (s: string): string => `'${s.replace(/'/g, `'\\''`)}'`

export type DadosScript = { tag: string; pid: number; executavel: string; appImage?: string }

// Windows: espera o app fechar, roda o install.ps1 da tag e abre o app de novo.
export function scriptWindows(d: DadosScript): string {
  return [
    "$ErrorActionPreference = 'Stop'",
    'try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}',
    `$Host.UI.RawUI.WindowTitle = 'Atualizando o Clipator'`,
    `Write-Host ''`,
    `Write-Host ${aspasPs(`  Atualizando o Clipator para a ${d.tag}. Não feche esta janela.`)} -ForegroundColor Magenta`,
    `Wait-Process -Id ${d.pid} -Timeout 60 -ErrorAction SilentlyContinue`,
    'Start-Sleep -Seconds 2',
    `$env:CLIPATOR_FONTE = ${aspasPs(fonteMotor(d.tag))}`,
    "$env:CLIPATOR_SIM = '1'",
    '$ok = $true',
    'try {',
    `  Invoke-RestMethod ${aspasPs(instalador(d.tag, 'install.ps1'))} | Invoke-Expression`,
    '} catch {',
    '  $ok = $false',
    '  Write-Host ""',
    "  Write-Host ('Erro: ' + $_) -ForegroundColor Red",
    '}',
    `$app = ${aspasPs(d.executavel)}`,
    'if ($ok) {',
    "  Write-Host ''",
    "  Write-Host '  Pronto! Abrindo o Clipator…' -ForegroundColor Green",
    '  if (Test-Path $app) { Start-Process -FilePath $app }',
    '  Start-Sleep -Seconds 3',
    '} else {',
    "  Write-Host ''",
    `  Write-Host ${aspasPs(`  A atualização não terminou. Veja os detalhes em ~\\.clipator\\instalacao.log ou baixe o app em https://github.com/${REPO}/releases`)} -ForegroundColor Yellow`,
    "  Read-Host '  Aperte Enter para fechar e abrir o Clipator'",
    '  if (Test-Path $app) { Start-Process -FilePath $app }',
    '}',
    ''
  ].join('\r\n')
}

// Mac e Linux: o install.sh guarda em ~/.clipator/app-versao onde pôs o app ("v0.1.2 /caminho").
// No Linux, se o AppImage aberto estava em outro lugar, ele é trocado pelo novo, para a
// próxima abertura não oferecer a mesma atualização de novo.
export function scriptUnix(d: DadosScript, plataforma: Plataforma): string {
  const abrir =
    plataforma === 'darwin'
      ? ['  if [ -n "$destino" ] && [ -e "$destino" ]; then open "$destino"; else open -a Clipator; fi']
      : [
          ...(d.appImage
            ? [
                `  antigo=${aspasSh(d.appImage)}`,
                '  if [ -n "$destino" ] && [ -f "$destino" ] && [ "$antigo" != "$destino" ] && [ -w "$antigo" ]; then',
                '    cp -f "$destino" "$antigo" && chmod +x "$antigo" && destino="$antigo"',
                '  fi'
              ]
            : []),
          `  [ -n "$destino" ] && [ -x "$destino" ] || destino=${aspasSh(d.executavel)}`,
          '  nohup "$destino" >/dev/null 2>&1 &'
        ]
  return [
    '#!/usr/bin/env bash',
    "printf '\\033]0;Atualizando o Clipator\\007'",
    `printf '\\n  \\033[35m%s\\033[0m\\n' ${aspasSh(`Atualizando o Clipator para a ${d.tag}. Não feche esta janela.`)}`,
    `for _ in $(seq 60); do kill -0 ${d.pid} 2>/dev/null || break; sleep 1; done`,
    'sleep 1',
    `export CLIPATOR_FONTE=${aspasSh(fonteMotor(d.tag))}`,
    `if curl -fsSL ${aspasSh(instalador(d.tag, 'install.sh'))} | bash -s -- --sim; then ok=1; else ok=0; fi`,
    'destino=""',
    'if [ -f "$HOME/.clipator/app-versao" ]; then read -r _ destino < "$HOME/.clipator/app-versao" || true; fi',
    'abrir_app() {',
    ...abrir,
    '}',
    'if [ "$ok" = 1 ]; then',
    "  printf '\\n  \\033[32mPronto! Abrindo o Clipator…\\033[0m\\n'",
    '  abrir_app',
    '  sleep 2',
    'else',
    `  printf '\\n  \\033[33m%s\\033[0m\\n' ${aspasSh(`A atualização não terminou. Veja os detalhes em ~/.clipator/instalacao.log ou baixe o app em https://github.com/${REPO}/releases`)}`,
    "  read -r -p '  Aperte Enter para fechar e abrir o Clipator ' _ < /dev/tty || true",
    '  abrir_app',
    'fi',
    ''
  ].join('\n')
}

// Terminais do Linux, na ordem de tentativa, com o jeito de cada um rodar um comando.
export const TERMINAIS_LINUX: [string, string[]][] = [
  ['x-terminal-emulator', ['-e']],
  ['gnome-terminal', ['--']],
  ['konsole', ['-e']],
  ['xfce4-terminal', ['-x']],
  ['mate-terminal', ['-x']],
  ['tilix', ['-e']],
  ['kitty', []],
  ['alacritty', ['-e']],
  ['wezterm', ['start', '--']],
  ['xterm', ['-e']]
]
