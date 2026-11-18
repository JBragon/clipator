# Instalador do Clipator para Windows.
#
#   irm https://raw.githubusercontent.com/JBragon/clipator/main/install.ps1 | iex
#   .\install.ps1                     (de dentro de uma cópia do repositório: instala o motor dela)
#
# Opções: -Sim (não pergunta nada e não instala Claude Code nem Codex), -SemApp, -ReinstalarApp, -SemHyperFrames, -SemModelos, -SemIA
# Pelo `irm | iex`, use variáveis: $env:CLIPATOR_SIM = "1", CLIPATOR_SEM_APP, CLIPATOR_SEM_MODELOS,
# CLIPATOR_SEM_HYPERFRAMES, CLIPATOR_SEM_IA, CLIPATOR_REINSTALAR_APP, e também CLIPATOR_FONTE e CLIPATOR_WORKSPACE.
#
# Instala só para o seu usuário: uv, Python 3.12 isolado, o comando `clipator`,
# o HyperFrames e os modelos. FFmpeg, Deno e Node.js vêm pelo winget.
param(
  [switch]$Sim,
  [switch]$SemApp,
  [switch]$ReinstalarApp,
  [switch]$SemHyperFrames,
  [switch]$SemModelos,
  [switch]$SemIA
)

$ErrorActionPreference = 'Stop'
# O npm vem com um npm.ps1, que a política padrão do Windows (Restricted) bloqueia mesmo
# dentro do `irm | iex`. Por isso o script chama sempre o npm.cmd.
$ProgressPreference = 'SilentlyContinue'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

$Repo = 'JBragon/clipator'
$HfVersao = '0.8.229'
$NodeMin = 22
$Base = Join-Path $HOME '.clipator'
$BinUsuario = Join-Path $HOME '.local\bin'

if ($env:CLIPATOR_SIM -eq '1') { $Sim = $true }
if ($env:CLIPATOR_SEM_APP -eq '1') { $SemApp = $true }
if ($env:CLIPATOR_SEM_HYPERFRAMES -eq '1') { $SemHyperFrames = $true }
if ($env:CLIPATOR_SEM_MODELOS -eq '1') { $SemModelos = $true }
if ($env:CLIPATOR_SEM_IA -eq '1') { $SemIA = $true }
if ($env:CLIPATOR_REINSTALAR_APP -eq '1') { $ReinstalarApp = $true }

function Passo($t) { Write-Host ''; Write-Host "==> $t" -ForegroundColor Magenta }
function Info($t)  { Write-Host "    $t" }
function Aviso($t) { Write-Host "    Aviso: $t" -ForegroundColor Yellow }
function Falha($t) { Write-Host "Erro: $t" -ForegroundColor Red; throw $t }
function Tem($nome) { [bool](Get-Command $nome -ErrorAction SilentlyContinue) }

function Perguntar($texto) {
  if ($Sim) { return $true }
  try { $r = Read-Host "    $texto [S/n]" } catch { return $true }
  return -not ($r -match '^(n|nao|não|no)$')
}

# O winget e os instaladores mudam o PATH do registro; a sessão atual precisa reler.
function Atualizar-Path {
  $maquina = [Environment]::GetEnvironmentVariable('Path', 'Machine')
  $usuario = [Environment]::GetEnvironmentVariable('Path', 'User')
  $extras = @($BinUsuario, (Join-Path $Base 'node'))
  $env:Path = (@($extras) + ($maquina -split ';') + ($usuario -split ';') + ($env:Path -split ';') |
    Where-Object { $_ } | Select-Object -Unique) -join ';'
}

# Pacotes portáteis do winget (FFmpeg, Deno) às vezes ficam fora do PATH, quando o winget
# não consegue criar o atalho em WinGet\Links. Acha o .exe e põe a pasta no PATH do usuário.
function Corrigir-PathWinget {
  $base = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages'
  if (-not (Test-Path $base)) { return }
  foreach ($par in @(@('Gyan.FFmpeg*', 'ffmpeg.exe', 'ffmpeg'), @('DenoLand.Deno*', 'deno.exe', 'deno'))) {
    if (Tem $par[2]) { continue }
    $exe = Get-ChildItem -Path $base -Directory -Filter $par[0] -ErrorAction SilentlyContinue |
      ForEach-Object { Get-ChildItem -Path $_.FullName -Recurse -Filter $par[1] -ErrorAction SilentlyContinue } |
      Sort-Object FullName -Descending | Select-Object -First 1
    if ($exe) {
      $pasta = $exe.DirectoryName
      $usuario = [Environment]::GetEnvironmentVariable('Path', 'User')
      if (-not (($usuario -split ';') -contains $pasta)) {
        [Environment]::SetEnvironmentVariable('Path', (@($usuario, $pasta) | Where-Object { $_ }) -join ';', 'User')
        Info "Coloquei $pasta no PATH do usuário."
      }
      Atualizar-Path
    }
  }
}

function Instalar-Winget($id, $nome) {
  if (Tem 'winget') {
    Info "Instalando $nome pelo winget…"
    winget install --id $id -e --silent --accept-source-agreements --accept-package-agreements --disable-interactivity | Out-Host
    Atualizar-Path
    return $true
  }
  return $false
}

function Instalar-Choco($pacote, $nome) {
  if (Tem 'choco') {
    Info "Instalando $nome pelo Chocolatey…"
    choco install $pacote -y --no-progress | Out-Host
    Atualizar-Path
    return $true
  }
  return $false
}

function Ffmpeg-Ok {
  if (-not (Tem 'ffmpeg')) { return $false }
  try { $filtros = (& ffmpeg -hide_banner -filters) -join "`n" } catch { return $false }
  return $filtros -match ' subtitles '
}

function Node-Ok {
  if (-not (Tem 'node')) { return $false }
  # O PowerShell 5.1 tira as aspas dos argumentos de programas nativos; por isso, só --version.
  try { $txt = (& node --version) | Select-Object -First 1 } catch { return $false }
  if ($txt -notmatch '^v?(\d+)\.') { return $false }
  return [int]$Matches[1] -ge $NodeMin
}

# ---- 1. sistema ---------------------------------------------------------------
Passo 'Conferindo o sistema'
$Arq = $env:PROCESSOR_ARCHITECTURE
$Gpu = 'nenhuma (a transcrição roda na CPU com um modelo menor)'
try {
  $placas = Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name
  $nvidia = $placas | Where-Object { $_ -match 'NVIDIA' } | Select-Object -First 1
  if ($nvidia) { $Gpu = "NVIDIA: $nvidia" }
} catch {}
$disco = Get-PSDrive -Name ($HOME.Substring(0, 1))
$LivreGb = [math]::Floor($disco.Free / 1GB)
Info "Sistema: Windows $Arq"
Info "GPU: $Gpu"
Info "Espaço livre: $LivreGb GB"
if ($LivreGb -lt 5) { Aviso 'menos de 5 GB livres. Os modelos e o Chrome do HyperFrames ocupam uns 3 GB.' }
New-Item -ItemType Directory -Force -Path $Base, $BinUsuario | Out-Null
Atualizar-Path

# ---- 2. uv --------------------------------------------------------------------
Passo 'uv e Python'
if (-not (Tem 'uv')) {
  Info 'Instalando o uv…'
  powershell -NoProfile -ExecutionPolicy ByPass -Command 'irm https://astral.sh/uv/install.ps1 | iex' | Out-Null
  Atualizar-Path
  if (-not (Tem 'uv')) { Falha 'o uv não ficou disponível. Abra um PowerShell novo e rode o instalador de novo.' }
}
Info (& uv --version)

# ---- 3. FFmpeg, Deno e Node.js -----------------------------------------------
Passo 'FFmpeg, Deno e Node.js'
if (-not (Ffmpeg-Ok)) {
  if (-not (Instalar-Winget 'Gyan.FFmpeg' 'o FFmpeg')) { [void](Instalar-Choco 'ffmpeg-full' 'o FFmpeg') }
}
if (-not (Tem 'deno')) {
  if (-not (Instalar-Winget 'DenoLand.Deno' 'o Deno')) { [void](Instalar-Choco 'deno' 'o Deno') }
}
if (-not $SemHyperFrames -and -not (Node-Ok)) {
  if (-not (Instalar-Winget 'OpenJS.NodeJS.LTS' 'o Node.js')) { [void](Instalar-Choco 'nodejs-lts' 'o Node.js') }
}
Corrigir-PathWinget
if (Ffmpeg-Ok) { Info 'FFmpeg com legendas: ok' } else { Aviso "FFmpeg não encontrado ou sem legendas. Rode 'clipator doctor' depois." }
if (Tem 'deno') { Info ('Deno: ' + ((& deno --version) | Select-Object -First 1)) } else { Aviso 'sem o Deno, links do YouTube podem falhar.' }
if (Node-Ok) { Info ('Node.js: ' + (& node --version)) }

# ---- 4. motor -----------------------------------------------------------------
Passo 'Motor do Clipator'
if ($env:CLIPATOR_FONTE) {
  $Fonte = $env:CLIPATOR_FONTE
} elseif ($PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot 'motor\pyproject.toml'))) {
  $Fonte = (Join-Path $PSScriptRoot 'motor') + '[visao]'
} elseif (Tem 'git') {
  $Fonte = "clipator[visao] @ git+https://github.com/$Repo#subdirectory=motor"
} else {
  $Fonte = "clipator[visao] @ https://github.com/$Repo/archive/refs/heads/main.zip#subdirectory=motor"
}
Info "Origem: $Fonte"
& uv tool install --python 3.12 --force $Fonte
if ($LASTEXITCODE -ne 0) { Falha 'o uv não conseguiu instalar o motor.' }
Atualizar-Path
if (-not (Tem 'clipator')) { Falha "o comando clipator não ficou no PATH. Abra um PowerShell novo e rode 'clipator doctor'." }
Info (& clipator --version)

# ---- 5. HyperFrames -------------------------------------------------------------
if (-not $SemHyperFrames) {
  Passo 'HyperFrames (estilos animados)'
  if ((Node-Ok) -and (Tem 'npm.cmd')) {
    & npm.cmd install --silent --no-fund --no-audit --prefix (Join-Path $Base 'hyperframes') "hyperframes@$HfVersao"
    if ($LASTEXITCODE -eq 0) { Info "HyperFrames $HfVersao instalado." }
    else { Aviso 'o npm falhou. Os estilos animados vão sair com a legenda simples.' }
  } else {
    Aviso "sem Node.js $NodeMin+, pulei o HyperFrames."
  }
}

# ---- 6. workspace e modelos -----------------------------------------------------
Passo 'Workspace'
if ($env:CLIPATOR_WORKSPACE) { & clipator init $env:CLIPATOR_WORKSPACE } else { & clipator init }
if ($LASTEXITCODE -ne 0) { Falha 'não consegui criar o workspace.' }

if (-not $SemModelos) {
  Passo 'Modelos (pode levar alguns minutos na primeira vez)'
  & clipator preparar
  if ($LASTEXITCODE -ne 0) { Aviso 'parte dos downloads falhou. O Clipator baixa o que faltar no primeiro uso.' }
}

# ---- 7. Claude Code e Codex -----------------------------------------------------
if (-not $SemIA) {
  Passo 'IA (Claude Code ou Codex)'
  if (-not (Tem 'claude') -and -not (Tem 'codex')) {
    Info 'O Clipator funciona sem IA, mas fica melhor com o Claude Code ou o Codex da sua assinatura.'
    if ($Sim) {
      Info 'Para instalar depois: irm https://claude.ai/install.ps1 | iex   (ou: npm install -g @openai/codex)'
    } elseif (Perguntar 'Instalar o Claude Code agora?') {
      try { powershell -NoProfile -ExecutionPolicy ByPass -Command 'irm https://claude.ai/install.ps1 | iex' | Out-Host; Atualizar-Path }
      catch { Aviso 'a instalação do Claude Code falhou.' }
    } elseif ((Tem 'npm.cmd') -and (Perguntar 'Instalar o Codex agora?')) {
      & npm.cmd install -g '@openai/codex'
      Atualizar-Path
    }
  }
  & clipator mcp registrar
  if ($LASTEXITCODE -ne 0) { Aviso "não consegui registrar o MCP. Rode 'clipator mcp registrar' depois." }
  if (Tem 'claude') { Info "Para entrar na sua conta: rode 'claude' uma vez." }
  if (Tem 'codex') { Info "Para entrar na sua conta: rode 'codex login' uma vez." }
}

# ---- 8. app de desktop ----------------------------------------------------------
# O instalador do app (NSIS, só para o usuário) se registra em "Programas e Recursos".
# A versão de lá diz se o download pode ser pulado.
function App-Instalado {
  $chaves = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
            'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*'
  Get-ItemProperty $chaves -ErrorAction SilentlyContinue |
    Where-Object { $_.PSObject.Properties['DisplayName'] -and $_.DisplayName -like 'Clipator*' } |
    Select-Object -First 1
}

function Instalar-App {
  try {
    $rel = Invoke-RestMethod "https://api.github.com/repos/$Repo/releases/latest" -Headers @{ 'User-Agent' = 'clipator-install' }
  } catch { return $false }
  $versao = ([string]$rel.tag_name).TrimStart('v')
  $atual = App-Instalado
  if (-not $ReinstalarApp -and $atual -and $versao -and $atual.DisplayVersion -eq $versao) {
    Info "O app já está na versão mais recente ($($rel.tag_name)). Para baixar de novo: -ReinstalarApp"
    return $true
  }
  $exes = $rel.assets | Where-Object { $_.name -match '\.exe$' }
  $asset = if ($Arq -eq 'ARM64') { $exes | Where-Object { $_.name -match 'arm64' } | Select-Object -First 1 } else { $null }
  if (-not $asset) { $asset = $exes | Where-Object { $_.name -notmatch 'arm64' } | Select-Object -First 1 }
  if (-not $asset) { return $false }
  Info "Baixando o app $($rel.tag_name)…"
  $tmp = Join-Path $env:TEMP $asset.name
  Invoke-WebRequest $asset.browser_download_url -OutFile $tmp -UseBasicParsing
  Start-Process -FilePath $tmp -ArgumentList '/S' -Wait
  Remove-Item $tmp -ErrorAction SilentlyContinue
  Info "App $($rel.tag_name) instalado."
  return $true
}

$Releases = "https://github.com/$Repo/releases"
$AppOk = $false
if (-not $SemApp) {
  Passo 'App de desktop'
  $AppOk = try { [bool](Instalar-App) } catch { $false }
  if (-not $AppOk) {
    Aviso "não consegui baixar o app de desktop. O motor foi instalado e o comando 'clipator' já funciona. Baixe o app em $Releases ou rode este instalador de novo mais tarde."
  }
}

Passo 'Pronto'
& clipator doctor
if (-not $SemApp -and -not $AppOk) {
  Write-Host ''
  Aviso "o app de desktop NÃO foi instalado. Baixe em $Releases"
} elseif ($AppOk) {
  Write-Host ''
  Info 'Para abrir o app: procure "Clipator" no menu Iniciar ou use o atalho na área de trabalho.'
}
Write-Host @'

    Para começar, abra o app ou use o canal de exemplo:
      clipator processar meu-canal "https://www.youtube.com/watch?v=..."
      clipator canal criar "Outro canal"

    Abra um PowerShell novo se o comando clipator não for encontrado.
    Para desinstalar: clipator desinstalar; uv tool uninstall clipator
'@
