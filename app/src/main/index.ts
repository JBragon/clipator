// Processo principal do Electron: sobe o motor Python e abre a janela.
//
// O motor roda como processo auxiliar (`clipator serve`), só em 127.0.0.1 e com
// um token aleatório que só esta janela conhece.

import { app, BrowserWindow, dialog, ipcMain, nativeTheme, shell } from 'electron'
import { spawn, type ChildProcess } from 'node:child_process'
import { randomBytes } from 'node:crypto'
import { existsSync, readFileSync, writeFileSync, mkdirSync } from 'node:fs'
import { createServer } from 'node:net'
import { homedir } from 'node:os'
import { isAbsolute, join, relative, resolve } from 'node:path'
import * as terminal from './terminal'
import * as chat from './chat'
import icone from '../../resources/icon.png?asset'

type Prefs = { workspace?: string; tema?: 'sistema' | 'claro' | 'escuro' }
type InfoMotor = { porta?: number; token?: string; erro?: string; log: string; workspace: string }

let janela: BrowserWindow | null = null
let motor: ChildProcess | null = null
let info: InfoMotor = { log: '', workspace: '' }
let prontoPromise: Promise<InfoMotor> | null = null

// CLIPATOR_DADOS_APP separa as preferências (útil para testar sem mexer no app do dia a dia)
if (process.env.CLIPATOR_DADOS_APP) app.setPath('userData', process.env.CLIPATOR_DADOS_APP)

const prefsPath = (): string => join(app.getPath('userData'), 'preferencias.json')

function lerPrefs(): Prefs {
  try {
    return JSON.parse(readFileSync(prefsPath(), 'utf-8')) as Prefs
  } catch {
    return {}
  }
}

function salvarPrefs(p: Prefs): void {
  mkdirSync(app.getPath('userData'), { recursive: true })
  writeFileSync(prefsPath(), JSON.stringify(p, null, 1))
}

function portaLivre(): Promise<number> {
  return new Promise((ok, falha) => {
    const s = createServer()
    s.unref()
    s.on('error', falha)
    s.listen(0, '127.0.0.1', () => {
      const end = s.address()
      s.close(() => ok(typeof end === 'object' && end ? end.port : 8765))
    })
  })
}

// App aberto pelo Finder, menu ou atalho recebe um PATH mínimo, sem ~/.local/bin
// (uv e clipator) nem o Homebrew (ffmpeg). Completa o PATH antes de subir o motor.
function completarPath(): void {
  const sep = process.platform === 'win32' ? ';' : ':'
  const casa = homedir()
  const extras =
    process.platform === 'win32'
      ? [join(casa, '.local', 'bin'), join(casa, '.clipator', 'node')]
      : [
          join(casa, '.local', 'bin'),
          join(casa, '.cargo', 'bin'),
          join(casa, '.clipator', 'node', 'bin'),
          '/opt/homebrew/opt/ffmpeg-full/bin',
          '/opt/homebrew/bin',
          '/usr/local/opt/ffmpeg-full/bin',
          '/usr/local/bin'
        ]
  const atual = (process.env.PATH ?? '').split(sep).filter(Boolean)
  const novos = extras.filter((d) => existsSync(d) && !atual.includes(d))
  if (novos.length) process.env.PATH = [...atual, ...novos].join(sep)
}
completarPath()

// Onde está o motor: variável de ambiente; em desenvolvimento, o código da pasta
// motor/ via uv; depois o `clipator` instalado pelo instalador (uv tool); por
// último o código empacotado junto com o app, rodando via uv.
function noPath(nome: string): boolean {
  const exts = process.platform === 'win32' ? ['.exe', '.cmd', '.bat', ''] : ['']
  return (process.env.PATH ?? '')
    .split(process.platform === 'win32' ? ';' : ':')
    .some((d) => d && exts.some((e) => existsSync(join(d, nome + e))))
}

function comandoMotor(): { cmd: string; args: string[] } {
  if (process.env.CLIPATOR_MOTOR) {
    const [cmd, ...args] = process.env.CLIPATOR_MOTOR.split(' ')
    return { cmd, args }
  }
  const dev = join(__dirname, '..', '..', '..', 'motor')
  if (!app.isPackaged && existsSync(join(dev, 'pyproject.toml'))) {
    // sem --extra visao o venv fica sem OpenCV/MediaPipe e o render quebra no recorte
    return { cmd: 'uv', args: ['run', '--project', dev, '--extra', 'visao', 'clipator'] }
  }
  if (noPath('clipator')) return { cmd: 'clipator', args: [] }
  const empacotado = join(process.resourcesPath ?? '', 'motor')
  return { cmd: 'uv', args: ['run', '--project', empacotado, '--extra', 'visao', 'clipator'] }
}

// o three.js (MIT, dependência npm do app) que a maquete 3D usa no render: o motor recebe o caminho do arquivo
function threeJs(): Record<string, string> {
  if (process.env.CLIPATOR_THREE) return {}
  const p = app.isPackaged
    ? join(process.resourcesPath ?? '', 'three', 'three.min.js')
    : join(__dirname, '..', '..', 'node_modules', 'three', 'build', 'three.min.js')
  return existsSync(p) ? { CLIPATOR_THREE: p } : {}
}

async function subirMotor(): Promise<InfoMotor> {
  const prefs = lerPrefs()
  const workspace = process.env.CLIPATOR_WORKSPACE || prefs.workspace || join(homedir(), 'Clipator')
  const porta = await portaLivre()
  const token = randomBytes(24).toString('base64url')
  const { cmd, args } = comandoMotor()
  info = { log: '', workspace }
  return new Promise((ok) => {
    let terminou = false
    const fim = (i: InfoMotor): void => {
      if (!terminou) {
        terminou = true
        ok(i)
      }
    }
    try {
      motor = spawn(cmd, [...args, '-w', workspace, 'serve', '--porta', String(porta), '--token', token, '--vigiar-stdin'], {
        env: { ...process.env, PYTHONUNBUFFERED: '1', PYTHONIOENCODING: 'utf-8', ...threeJs() },
        windowsHide: true,
        stdio: ['pipe', 'pipe', 'pipe'],
        shell: process.platform === 'win32'
      })
    } catch (e) {
      fim({ ...info, erro: String(e) })
      return
    }
    const ler = (b: Buffer): void => {
      const txt = b.toString('utf-8')
      info.log = (info.log + txt).slice(-20000)
      if (txt.includes('CLIPATOR_PRONTO')) {
        info = { ...info, porta, token }
        // dá um instante para o uvicorn abrir a porta
        setTimeout(() => fim(info), 300)
      }
    }
    motor.stdout?.on('data', ler)
    motor.stderr?.on('data', ler)
    motor.on('error', (e) => fim({ ...info, erro: `Não consegui iniciar o motor (${cmd}): ${e.message}` }))
    motor.on('exit', (code) => {
      motor = null
      fim({ ...info, erro: `O motor fechou (código ${code}). Rode "clipator doctor" no terminal.` })
    })
    setTimeout(() => fim({ ...info, erro: 'O motor demorou mais de 60 s para abrir.' }), 60000)
  })
}

function pararMotor(): void {
  if (motor && !motor.killed) motor.kill()
  motor = null
}

function criarJanela(): void {
  const prefs = lerPrefs()
  nativeTheme.themeSource = prefs.tema === 'claro' ? 'light' : prefs.tema === 'escuro' ? 'dark' : 'system'
  janela = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 640,
    title: 'Clipator',
    icon: icone,
    backgroundColor: nativeTheme.shouldUseDarkColors ? '#1e1e1e' : '#ffffff',
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false
    }
  })
  janela.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('https://')) shell.openExternal(url)
    return { action: 'deny' }
  })
  if (process.env.ELECTRON_RENDERER_URL) janela.loadURL(process.env.ELECTRON_RENDERER_URL)
  else janela.loadFile(join(__dirname, '../renderer/index.html'))
}

ipcMain.handle('motor:info', () => prontoPromise ?? Promise.resolve(info))
ipcMain.handle('motor:reiniciar', async () => {
  pararMotor()
  prontoPromise = subirMotor()
  return prontoPromise
})
ipcMain.handle('dialogo:video', async () => {
  const r = await dialog.showOpenDialog({
    properties: ['openFile'],
    filters: [{ name: 'Vídeos', extensions: ['mp4', 'mkv', 'webm', 'mov', 'm4v', 'avi', 'ts', 'flv'] }]
  })
  return r.canceled ? null : r.filePaths[0]
})
ipcMain.handle('dialogo:pasta', async () => {
  const r = await dialog.showOpenDialog({ properties: ['openDirectory', 'createDirectory'] })
  return r.canceled ? null : r.filePaths[0]
})
ipcMain.handle('dialogo:zip', async () => {
  const r = await dialog.showOpenDialog({ properties: ['openFile'], filters: [{ name: 'Skill (.zip)', extensions: ['zip'] }] })
  return r.canceled ? null : r.filePaths[0]
})
ipcMain.handle('dialogo:cookies', async () => {
  const r = await dialog.showOpenDialog({ properties: ['openFile'], filters: [{ name: 'cookies.txt', extensions: ['txt'] }] })
  return r.canceled ? null : r.filePaths[0]
})
ipcMain.handle('dialogo:salvar', async (_e, nome: string) => {
  const r = await dialog.showSaveDialog({ defaultPath: join(app.getPath('documents'), nome) })
  return r.canceled || !r.filePath ? null : r.filePath
})
ipcMain.handle('workspace:definir', async (_e, pasta: string) => {
  salvarPrefs({ ...lerPrefs(), workspace: pasta })
  pararMotor()
  prontoPromise = subirMotor()
  return prontoPromise
})
ipcMain.handle('tema:definir', (_e, tema: Prefs['tema']) => {
  salvarPrefs({ ...lerPrefs(), tema })
  nativeTheme.themeSource = tema === 'claro' ? 'light' : tema === 'escuro' ? 'dark' : 'system'
})
ipcMain.handle('shell:mostrar', (_e, caminho: string) => shell.showItemInFolder(caminho))
ipcMain.handle('shell:abrir', (_e, caminho: string) => shell.openPath(caminho))
// manda um canal ou vídeo para a Lixeira (só pastas dentro de <workspace>/canais)
ipcMain.handle('shell:lixeira', async (_e, caminho: string) => {
  const raiz = resolve(info.workspace, 'canais')
  const alvo = resolve(String(caminho))
  const rel = relative(raiz, alvo)
  if (!info.workspace || !rel || rel.startsWith('..') || isAbsolute(rel)) throw new Error('Só dá para apagar canais e vídeos do workspace.')
  await shell.trashItem(alvo)
})
ipcMain.handle('app:idioma', () => app.getLocale())

// conversas com a IA no terminal embutido (ver terminal.ts)
const enviar = (canal: string, ...args: unknown[]): void => {
  if (janela && !janela.isDestroyed()) janela.webContents.send(canal, ...args)
}
ipcMain.handle('ia:disponivel', () => ({ claude: !!terminal.resolverCli('claude'), codex: !!terminal.resolverCli('codex') }))
ipcMain.handle('ia:abrir', (_e, p: terminal.PedidoSessao, cols: number, rows: number) =>
  terminal.abrirSessao(p, info.workspace, cols, rows, (id, d, n) => enviar('ia:dados', id, d, n), (id, c) => enviar('ia:saiu', id, c)))
ipcMain.handle('ia:listar', () => terminal.listarSessoes())
ipcMain.handle('ia:saida', (_e, id: string) => terminal.saidaDa(String(id)))
ipcMain.on('ia:escrever', (_e, id: string, dados: string) => terminal.escrever(String(id), String(dados)))
ipcMain.on('ia:redimensionar', (_e, id: string, cols: number, rows: number) => terminal.redimensionar(String(id), Number(cols), Number(rows)))
ipcMain.handle('ia:parar', (_e, id: string) => terminal.parar(String(id)))
ipcMain.handle('ia:fechar', (_e, id: string) => terminal.fecharSessao(String(id)))

// conversa estilizada (ver chat.ts)
chat.definirSaida((id, e) => enviar('chat:evento', id, e))
ipcMain.handle('chat:abrir', (_e, p: chat.PedidoChat) => chat.abrirChat(p, info.workspace))
ipcMain.handle('chat:listar', () => chat.listarChats())
ipcMain.handle('chat:eventos', (_e, id: string) => chat.eventosDo(String(id)))
ipcMain.handle('chat:enviar', (_e, id: string, texto: string) => chat.enviarChat(String(id), String(texto)))
ipcMain.handle('chat:responder', (_e, id: string, perm: string, d: chat.Decisao) => chat.responderChat(String(id), String(perm), d))
ipcMain.handle('chat:interromper', (_e, id: string) => chat.interromperChat(String(id)))
ipcMain.handle('chat:fechar', (_e, id: string) => chat.fecharChat(String(id)))

app.whenReady().then(() => {
  prontoPromise = subirMotor()
  criarJanela()
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) criarJanela()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})
const encerrar = (): void => {
  terminal.pararTodas()
  chat.fecharTodosChats()
  pararMotor()
}
app.on('before-quit', encerrar)
app.on('will-quit', encerrar)
process.on('exit', encerrar)
