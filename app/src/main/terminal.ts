// Conversas com o Claude Code ou o Codex do usuário dentro do app: cada uma é um pty (node-pty)
// que vive aqui no processo principal. A tela (xterm.js) pode fechar e voltar; a conversa continua.
//
// Segurança: só roda `claude` ou `codex` (o executável achado no PATH ou em CLIPATOR_CLAUDE /
// CLIPATOR_CODEX), com uma lista de argumentos montada aqui, a frase fixa que o motor devolve e
// uma pasta dentro do workspace. Nada passa por shell e não há flags que pulem as permissões.

import { spawn as spawnPty, type IPty } from 'node-pty'
import { execFile, execFileSync } from 'node:child_process'
import { existsSync, statSync } from 'node:fs'
import { join, relative, resolve, isAbsolute } from 'node:path'

export type Agente = 'claude' | 'codex'
export type PedidoSessao = { agente: Agente; modo: 'abrir' | 'continuar'; cwd: string; frase: string; titulo: string; alvo: string }
export type InfoSessao = { id: string; agente: Agente; modo: string; cwd: string; titulo: string; alvo: string; viva: boolean; criada: number; codigo?: number }

type Sessao = InfoSessao & { pty: IPty; saida: string; total: number }

const MAX_SAIDA = 1_000_000 // o que fica guardado para quando a tela volta
const FRASE = /^Leia o arquivo [\w\-./]+\.md e siga o que ele pede\. Comece me mostrando o plano\.$/
const sessoes = new Map<string, Sessao>()
let seq = 0

function acharNoPath(nome: string): string | null {
  const win = process.platform === 'win32'
  const exts = win ? ['.exe', '.cmd', '.bat', ''] : ['']
  for (const d of (process.env.PATH ?? '').split(win ? ';' : ':')) {
    for (const e of exts) {
      const p = d && join(d, nome + e)
      if (p && existsSync(p) && statSync(p).isFile()) return p
    }
  }
  return null
}

export function resolverCli(agente: Agente): string | null {
  const env = process.env[`CLIPATOR_${agente.toUpperCase()}`]
  if (env) return isAbsolute(env) ? (existsSync(env) ? env : null) : acharNoPath(env)
  return acharNoPath(agente)
}

// os mesmos comandos do motor (edicao_ia.comando)
export function argumentos(agente: Agente, modo: 'abrir' | 'continuar', frase: string): string[] {
  if (agente === 'claude') return modo === 'continuar' ? ['--continue', frase] : [frase]
  return modo === 'continuar' ? ['resume', '--last', frase] : [frase]
}

function dentro(pasta: string, raiz: string): boolean {
  const rel = relative(resolve(raiz), resolve(pasta))
  return rel !== '' && !rel.startsWith('..') && !isAbsolute(rel)
}

export function abrirSessao(p: PedidoSessao, workspace: string, cols: number, rows: number, aoDados: (id: string, d: string, total: number) => void,
  aoSair: (id: string, codigo: number) => void): InfoSessao {
  if (p.agente !== 'claude' && p.agente !== 'codex') throw new Error('Só Claude Code ou Codex.')
  if (p.modo !== 'abrir' && p.modo !== 'continuar') throw new Error('Modo inválido.')
  if (!FRASE.test(p.frase)) throw new Error('Frase inicial inesperada.')
  if (!workspace || !dentro(p.cwd, workspace) || !existsSync(p.cwd)) throw new Error('A pasta da conversa precisa estar dentro do workspace.')
  const exe = resolverCli(p.agente)
  if (!exe) throw new Error(`${p.agente === 'claude' ? 'Claude Code' : 'Codex'} não está instalado.`)
  const pty = spawnPty(exe, argumentos(p.agente, p.modo, p.frase), {
    name: 'xterm-256color',
    cols: Math.max(20, Math.floor(cols) || 100),
    rows: Math.max(5, Math.floor(rows) || 30),
    cwd: p.cwd,
    env: { ...process.env, TERM: 'xterm-256color', COLORTERM: 'truecolor' } as Record<string, string>
  })
  const id = `c${++seq}-${Date.now().toString(36)}`
  const s: Sessao = { id, agente: p.agente, modo: p.modo, cwd: p.cwd, titulo: String(p.titulo).slice(0, 120), alvo: String(p.alvo).slice(0, 200), viva: true, criada: Date.now(), pty, saida: '', total: 0 }
  sessoes.set(id, s)
  pty.onData((d) => {
    s.saida = (s.saida + d).slice(-MAX_SAIDA)
    s.total += d.length
    aoDados(id, d, s.total)
  })
  pty.onExit(({ exitCode }) => {
    s.viva = false
    s.codigo = exitCode
    aoSair(id, exitCode)
  })
  return info(s)
}

function info(s: Sessao): InfoSessao {
  const { pty: _p, saida: _s, total: _t, ...resto } = s
  return resto
}

export const listarSessoes = (): InfoSessao[] => [...sessoes.values()].map(info)
// o que a tela perdeu enquanto estava fechada; `total` diz até onde vai (para não repetir nem pular nada)
export const saidaDa = (id: string): { texto: string; total: number } => ({ texto: sessoes.get(id)?.saida ?? '', total: sessoes.get(id)?.total ?? 0 })

export function escrever(id: string, dados: string): void {
  const s = sessoes.get(id)
  if (s?.viva && typeof dados === 'string') s.pty.write(dados)
}

export function redimensionar(id: string, cols: number, rows: number): void {
  const s = sessoes.get(id)
  if (s?.viva && cols > 0 && rows > 0) s.pty.resize(Math.floor(cols), Math.floor(rows))
}

// para a CLI e tudo o que ela abriu (no Windows, a árvore inteira de processos). Ao fechar o app
// é síncrono: senão o app sai antes do taskkill e os processos ficam para trás.
export function parar(id: string, esperar = false): void {
  const s = sessoes.get(id)
  if (!s?.viva) return
  const pid = s.pty.pid
  if (process.platform === 'win32') {
    const args = ['/PID', String(pid), '/T', '/F']
    if (esperar) {
      try {
        execFileSync('taskkill', args, { stdio: 'ignore', windowsHide: true })
      } catch {
        /* já tinha fechado */
      }
    } else execFile('taskkill', args, { windowsHide: true }, () => undefined)
  }
  try {
    s.pty.kill()
  } catch {
    /* já fechou */
  }
}

export function fecharSessao(id: string): void {
  parar(id)
  sessoes.delete(id)
}

export function pararTodas(): void {
  for (const id of sessoes.keys()) parar(id, true)
}
