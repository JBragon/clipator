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

# ---- tela ---------------------------------------------------------------------
# Num console, cada etapa vira uma linha com √ e a etapa atual fica numa barra que se
# atualiza no lugar. A saída dos comandos vai para ~\.clipator\instalacao.log. Fora de
# um console (CI, saída redirecionada) ou com CLIPATOR_SIMPLES=1, a saída é a de sempre.
New-Item -ItemType Directory -Force -Path $Base | Out-Null
$Log = Join-Path $Base 'instalacao.log'
Set-Content -Path $Log -Value '' -Encoding UTF8
$UI = $false
try {
  $UI = (-not [Console]::IsOutputRedirected) -and (-not $env:CI) -and ($Host.Name -eq 'ConsoleHost') -and ($env:CLIPATOR_SIMPLES -ne '1')
} catch { $UI = $false }
$Total = 6 + [int](-not $SemHyperFrames) + [int](-not $SemModelos) + [int](-not $SemIA) + [int](-not $SemApp)
$N = 0; $Etapa = ''; $Detalhe = ''; $EtapaAviso = $false; $Giro = 0
$Giros = @('|', '/', '-', '\')

function Registrar($t) { try { Add-Content -Path $Log -Value $t -Encoding UTF8 } catch {} }

function Largura {
  try { $w = $Host.UI.RawUI.WindowSize.Width } catch { $w = 80 }
  if (-not $w -or $w -lt 20) { $w = 80 }
  return $w
}

function Limpar-Linha {
  if ($UI) { [Console]::Write("`r" + (' ' * ((Largura) - 1)) + "`r") }
}

function Desenhar {
  if (-not $UI -or -not $Etapa) { return }
  $cheio = [math]::Floor(($script:N - 1) * 20 / $Total)
  $barra = ([string][char]0x2588 * $cheio) + ([string][char]0x2591 * (20 - $cheio))
  $txt = $script:Etapa
  if ($script:Detalhe) { $txt = "$($script:Etapa) · $($script:Detalhe)" }
  $max = (Largura) - 36
  if ($max -lt 10) { $max = 10 }
  if ($txt.Length -gt $max) { $txt = $txt.Substring(0, $max - 1) + '…' }
  Limpar-Linha
  Write-Host ('  ' + $Giros[$script:Giro % 4] + ' ' + $barra) -ForegroundColor Magenta -NoNewline
  Write-Host (' {0,2}/{1}  ' -f $script:N, $Total) -ForegroundColor DarkGray -NoNewline
  Write-Host $txt -NoNewline
}

function Fechar-Etapa {
  if (-not $script:Etapa) { return }
  if ($UI) {
    Limpar-Linha
    if ($script:EtapaAviso) { Write-Host '  ! ' -ForegroundColor Yellow -NoNewline }
    else { Write-Host ('  ' + [char]0x221A + ' ') -ForegroundColor Green -NoNewline }
    Write-Host $script:Etapa
  }
  $script:Etapa = ''
}

function Banner {
  if (-not $UI) { return }
  Write-Host @'

     ____ _     ___ ____   _  _____ ___  ____
    / ___| |   |_ _|  _ \ / \|_   _/ _ \|  _ \
   | |   | |    | || |_) / _ \ | || | | | |_) |
   | |___| |___ | ||  __/ ___ \| || |_| |  _ <
    \____|_____|___|_| /_/   \_\_| \___/|_| \_\

'@ -ForegroundColor Magenta
  Write-Host '   Clips curtos de vídeos longos, de graça e na sua máquina' -ForegroundColor White
  Write-Host "   Detalhes da instalação: $Log" -ForegroundColor DarkGray
  Write-Host ''
}

function Passo($t) {
  Registrar ''; Registrar "==> $t"
  if ($UI) {
    Fechar-Etapa
    $script:N++; $script:Etapa = $t; $script:Detalhe = ''; $script:EtapaAviso = $false
    Desenhar
  } else {
    Write-Host ''; Write-Host "==> $t" -ForegroundColor Magenta
  }
}
function Info($t) {
  Registrar "    $t"
  if ($UI -and $script:Etapa) { $script:Detalhe = "$t"; Desenhar } else { Write-Host "    $t" }
}
function Aviso($t) {
  Registrar "    Aviso: $t"
  $script:EtapaAviso = $true
  Limpar-Linha
  Write-Host "    Aviso: $t" -ForegroundColor Yellow
  Desenhar
}
function Falha($t) {
  Registrar "Erro: $t"
  if ($UI) {
    Limpar-Linha
    if ($script:Etapa) { Write-Host '  x ' -ForegroundColor Red -NoNewline; Write-Host $script:Etapa }
    Write-Host ''
    Write-Host "    Últimas linhas de ${Log}:" -ForegroundColor DarkGray
    Get-Content $Log -Tail 15 -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "    $_" }
  }
  Write-Host ''
  Write-Host "Erro: $t" -ForegroundColor Red
  throw $t
}
function Tem($nome) { [bool](Get-Command $nome -ErrorAction SilentlyContinue) }

# Verificação: cada item termina com um estado, mostrado no fim. Rodar o instalador de
# novo confere tudo outra vez e só instala o que falta.
$Verif = New-Object System.Collections.ArrayList
function Marcar($estado, $item, $detalhe) {
  [void]$Verif.Add(@($estado, $item, $detalhe))
  Registrar "    [$estado] ${item}: $detalhe"
}
function Estado($antes, $agora, $item, $seFalta) {
  if ($agora) {
    if ($antes) { Marcar 'ok' $item 'já estava instalado' } else { Marcar 'novo' $item 'instalado agora' }
  } else { Marcar 'aviso' $item $seFalta }
}
function Mostrar-Verificacao {
  Write-Host ''
  Write-Host '  Verificação' -ForegroundColor White
  foreach ($v in $Verif) {
    if ($v[0] -eq 'aviso') { Write-Host '  ! ' -ForegroundColor Yellow -NoNewline }
    else { Write-Host ('  ' + [char]0x221A + ' ') -ForegroundColor Green -NoNewline }
    Write-Host ('{0,-22} ' -f $v[1]) -NoNewline
    Write-Host $v[2] -ForegroundColor DarkGray
  }
}

# Rodar programa argumentos…: no console, a saída vai para o log e a barra gira enquanto
# espera. Fora dele, roda como antes. Nos dois casos, o código de saída fica em $LASTEXITCODE.
function Rodar($exe, [string[]]$argumentos = @()) {
  Registrar ('$ ' + $exe + ' ' + ($argumentos -join ' '))
  if (-not $UI) {
    & $exe @argumentos | Out-Host
    return
  }
  $cmd = Get-Command $exe -ErrorAction SilentlyContinue | Select-Object -First 1
  $caminho = if ($cmd -and $cmd.Source) { $cmd.Source } else { $exe }
  # .cmd e .bat só abrem pelo cmd
  if ($caminho -match '\.(cmd|bat)$') {
    $argumentos = @('/d', '/c', $caminho) + $argumentos
    $caminho = if ($env:ComSpec) { $env:ComSpec } else { 'cmd.exe' }
  }
  $linha = ($argumentos | ForEach-Object {
    if ($_ -match '[\s"]') { '"' + ($_ -replace '"', '\"') + '"' } else { $_ }
  }) -join ' '
  $out = [IO.Path]::GetTempFileName(); $err = [IO.Path]::GetTempFileName(); $vazio = [IO.Path]::GetTempFileName()
  try {
    $opcoes = @{ FilePath = $caminho; NoNewWindow = $true; PassThru = $true
      RedirectStandardOutput = $out; RedirectStandardError = $err; RedirectStandardInput = $vazio }
    if ($linha) { $opcoes.ArgumentList = $linha }
    $p = Start-Process @opcoes
    $null = $p.Handle  # sem isso o ExitCode volta vazio no PowerShell 5.1
    while (-not $p.HasExited) { $script:Giro++; Desenhar; Start-Sleep -Milliseconds 120 }
    $p.WaitForExit()
    $global:LASTEXITCODE = $p.ExitCode
  } catch {
    Registrar "    $_"
    $global:LASTEXITCODE = 1
  } finally {
    Remove-Item $vazio -ErrorAction SilentlyContinue
    foreach ($f in @($out, $err)) {
      try { Get-Content $f -ErrorAction SilentlyContinue | Add-Content -Path $Log -Encoding UTF8 } catch {}
      Remove-Item $f -ErrorAction SilentlyContinue
    }
  }
}

function Perguntar($texto) {
  if ($Sim) { return $true }
  Limpar-Linha
  try { $r = Read-Host "    $texto [S/n]" } catch { return $true }
  Desenhar
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
    Rodar 'winget' @('install', '--id', $id, '-e', '--silent', '--accept-source-agreements', '--accept-package-agreements', '--disable-interactivity')
    Atualizar-Path
    return $true
  }
  return $false
}

function Instalar-Choco($pacote, $nome) {
  if (Tem 'choco') {
    Info "Instalando $nome pelo Chocolatey…"
    Rodar 'choco' @('install', $pacote, '-y', '--no-progress')
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
Banner
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
$UvAntes = Tem 'uv'
if (-not (Tem 'uv')) {
  Info 'Instalando o uv…'
  Rodar 'powershell' @('-NoProfile', '-ExecutionPolicy', 'ByPass', '-Command', 'irm https://astral.sh/uv/install.ps1 | iex')
  Atualizar-Path
  if (-not (Tem 'uv')) { Falha 'o uv não ficou disponível. Abra um PowerShell novo e rode o instalador de novo.' }
}
$UvVersao = [string]((& uv --version) | Select-Object -First 1)
Info $UvVersao
$UvCurta = ($UvVersao -split ' ')[1]
if ($UvAntes) { Marcar 'ok' 'uv e Python' "$UvCurta · já estava instalado" } else { Marcar 'novo' 'uv e Python' "$UvCurta · instalado agora" }

# ---- 3. FFmpeg, Deno e Node.js -----------------------------------------------
Passo 'FFmpeg, Deno e Node.js'
$FfAntes = Ffmpeg-Ok; $DenoAntes = Tem 'deno'; $NodeAntes = Node-Ok
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
Estado $FfAntes (Ffmpeg-Ok) 'FFmpeg com legendas' 'falta · os clips saem sem legenda'
Estado $DenoAntes (Tem 'deno') 'Deno' 'falta · links do YouTube podem falhar'
if (-not $SemHyperFrames) { Estado $NodeAntes (Node-Ok) "Node.js $NodeMin+" 'falta · estilos animados saem simples' }

# ---- 4. motor -----------------------------------------------------------------
Passo 'Motor do Clipator'
$MotorAntes = ''
if (Tem 'clipator') { try { $MotorAntes = [string]((& clipator --version) | Select-Object -First 1) } catch {} }
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
Info 'Instalando (pode levar alguns minutos)…'
Rodar 'uv' @('tool', 'install', '--python', '3.12', '--force', $Fonte)
if ($LASTEXITCODE -ne 0) { Falha 'o uv não conseguiu instalar o motor.' }
Atualizar-Path
if (-not (Tem 'clipator')) { Falha "o comando clipator não ficou no PATH. Abra um PowerShell novo e rode 'clipator doctor'." }
$MotorAgora = [string]((& clipator --version) | Select-Object -First 1)
Info $MotorAgora
if (-not $MotorAntes) { Marcar 'novo' 'Motor' "$MotorAgora · instalado agora" }
elseif ($MotorAntes -eq $MotorAgora) { Marcar 'ok' 'Motor' "$MotorAgora · conferido e atualizado" }
else { Marcar 'novo' 'Motor' "$MotorAntes → $MotorAgora" }

# ---- 5. HyperFrames -------------------------------------------------------------
if (-not $SemHyperFrames) {
  Passo 'HyperFrames (estilos animados)'
  $HfAntes = Test-Path (Join-Path $Base 'hyperframes\node_modules\hyperframes')
  if ((Node-Ok) -and (Tem 'npm.cmd')) {
    Rodar 'npm.cmd' @('install', '--silent', '--no-fund', '--no-audit', '--prefix', (Join-Path $Base 'hyperframes'), "hyperframes@$HfVersao")
    if ($LASTEXITCODE -eq 0) { Info "HyperFrames $HfVersao instalado."; Estado $HfAntes $true 'HyperFrames' '' }
    else {
      Aviso 'o npm falhou. Os estilos animados vão sair com a legenda simples.'
      Marcar 'aviso' 'HyperFrames' 'o npm falhou · estilos animados saem simples'
    }
  } else {
    Aviso "sem Node.js $NodeMin+, pulei o HyperFrames."
    Marcar 'aviso' 'HyperFrames' "sem Node.js $NodeMin+ · estilos animados saem simples"
  }
}

# ---- 6. workspace e modelos -----------------------------------------------------
Passo 'Workspace'
$Ws = if ($env:CLIPATOR_WORKSPACE) { $env:CLIPATOR_WORKSPACE } else { Join-Path $HOME 'Clipator' }
$WsAntes = Test-Path $Ws
if ($env:CLIPATOR_WORKSPACE) { Rodar 'clipator' @('init', $env:CLIPATOR_WORKSPACE) } else { Rodar 'clipator' @('init') }
if ($LASTEXITCODE -ne 0) { Falha 'não consegui criar o workspace.' }
Info $Ws
if ($WsAntes) { Marcar 'ok' 'Workspace' "$Ws · já existia" } else { Marcar 'novo' 'Workspace' "$Ws · criado agora" }

if (-not $SemModelos) {
  Passo 'Modelos (pode levar alguns minutos na primeira vez)'
  Info 'Baixando os modelos de transcrição e de rosto…'
  Rodar 'clipator' @('preparar')
  if ($LASTEXITCODE -ne 0) {
    Aviso 'parte dos downloads falhou. O Clipator baixa o que faltar no primeiro uso.'
    Marcar 'aviso' 'Modelos' 'parte falhou · o que faltar vem no primeiro uso'
  } else { Marcar 'ok' 'Modelos' 'conferidos e prontos para usar offline' }
}

# ---- 7. Claude Code e Codex -----------------------------------------------------
if (-not $SemIA) {
  Passo 'IA (Claude Code ou Codex)'
  if (-not (Tem 'claude') -and -not (Tem 'codex')) {
    Info 'O Clipator funciona sem IA, mas fica melhor com o Claude Code ou o Codex da sua assinatura.'
    if ($Sim) {
      Info 'Para instalar depois: irm https://claude.ai/install.ps1 | iex   (ou: npm install -g @openai/codex)'
    } elseif (Perguntar 'Instalar o Claude Code agora?') {
      Info 'Instalando o Claude Code…'
      Rodar 'powershell' @('-NoProfile', '-ExecutionPolicy', 'ByPass', '-Command', 'irm https://claude.ai/install.ps1 | iex')
      if ($LASTEXITCODE -ne 0) { Aviso 'a instalação do Claude Code falhou.' }
      Atualizar-Path
    } elseif ((Tem 'npm.cmd') -and (Perguntar 'Instalar o Codex agora?')) {
      Info 'Instalando o Codex…'
      Rodar 'npm.cmd' @('install', '-g', '@openai/codex')
      Atualizar-Path
    }
  }
  Rodar 'clipator' @('mcp', 'registrar')
  $McpOk = ($LASTEXITCODE -eq 0)
  if (-not $McpOk) { Aviso "não consegui registrar o MCP. Rode 'clipator mcp registrar' depois." }
  $Ias = @(); if (Tem 'claude') { $Ias += 'Claude Code' }; if (Tem 'codex') { $Ias += 'Codex' }
  if (-not $Ias) { Marcar 'aviso' 'IA' 'nenhuma instalada · opcional, funciona sem' }
  elseif ($McpOk) { Marcar 'ok' 'IA' (($Ias -join ' e ') + ' · MCP registrado') }
  else { Marcar 'aviso' 'IA' (($Ias -join ' e ') + ' · o MCP não foi registrado') }
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
  if (Tem 'curl.exe') {
    Rodar 'curl.exe' @('-fsSL', '--retry', '3', '-o', $tmp, $asset.browser_download_url)
    if ($LASTEXITCODE -ne 0) { return $false }
  } else {
    Invoke-WebRequest $asset.browser_download_url -OutFile $tmp -UseBasicParsing
  }
  Info 'Instalando o app…'
  Rodar $tmp @('/S')
  Remove-Item $tmp -ErrorAction SilentlyContinue
  Info "App $($rel.tag_name) instalado."
  return $true
}

$Releases = "https://github.com/$Repo/releases"
$AppOk = $false
if (-not $SemApp) {
  Passo 'App de desktop'
  $AppAntes = $null; try { $AppAntes = (App-Instalado).DisplayVersion } catch {}
  $AppOk = try { [bool](Instalar-App) } catch { $false }
  if ($AppOk) {
    $AppAgora = $null; try { $AppAgora = (App-Instalado).DisplayVersion } catch {}
    if ($AppAntes -and $AppAntes -eq $AppAgora -and -not $ReinstalarApp) { Marcar 'ok' 'App de desktop' "v$AppAgora · já estava na versão mais recente" }
    elseif ($AppAgora) { Marcar 'novo' 'App de desktop' "v$AppAgora · instalado agora" }
    else { Marcar 'novo' 'App de desktop' 'instalado agora' }
  } else { Marcar 'aviso' 'App de desktop' "não instalado · baixe em $Releases" }
  if (-not $AppOk) {
    Aviso "não consegui baixar o app de desktop. O motor foi instalado e o comando 'clipator' já funciona. Baixe o app em $Releases ou rode este instalador de novo mais tarde."
  }
}

Passo 'Conferindo a instalação'
$Doctor = (& clipator doctor | Out-String)
$DoctorOk = ($LASTEXITCODE -eq 0)
Registrar $Doctor
if ($DoctorOk) { Marcar 'ok' 'clipator doctor' 'tudo pronto' } else { Marcar 'aviso' 'clipator doctor' 'faltam itens obrigatórios · veja abaixo' }
Fechar-Etapa
if ($UI) {
  Write-Host ''
  Write-Host ('  ' + ([string][char]0x2588 * 20) + ' Pronto!') -ForegroundColor Green
}
Mostrar-Verificacao
# Num console, o relatório completo do doctor só aparece quando falta algo (está no log).
if (-not $UI -or -not $DoctorOk) { Write-Host ''; Write-Host $Doctor }
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
