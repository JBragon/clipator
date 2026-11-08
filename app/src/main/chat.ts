// Conversa estilizada com o Claude Code ou o Codex do usuário (painel do passo 3).
//
// - Claude Code: `claude -p` com entrada e saída em stream-json. Os pedidos de permissão chegam
//   pelo mesmo canal (control_request "can_use_tool") e o app responde com o que o usuário clicou.
// - Codex: `codex app-server` (JSON-RPC por stdin/stdout, o mesmo que a extensão do VS Code usa).
//   Aprovações de comando e de arquivo chegam como pedidos do servidor e esperam o usuário.
//
// Os dois viram a mesma lista de eventos (Evento) para a tela. O texto do usuário vai só pelo
// stdin, como JSON; a linha de comando tem só flags fixas. Nada de flags que pulem permissões.

import { spawn, type ChildProcess } from 'node:child_process'
import { existsSync } from 'node:fs'
import { isAbsolute, relative, resolve } from 'node:path'
import { createInterface } from 'node:readline'
import { execFile, execFileSync } from 'node:child_process'
import { resolverCli, type Agente } from './terminal'

export type PedidoChat = { agente: Agente; modo: 'abrir' | 'continuar'; cwd: string; frase: string; titulo: string; alvo: string; modelo?: string }
export type Decisao = 'sim' | 'nao' | 'sempre'
export type Evento =
  | { tipo: 'sistema'; sessao?: string; modelo?: string; modelos?: string[]; aviso?: string }
  | { tipo: 'usuario'; texto: string }
  | { tipo: 'texto'; id: string; texto: string; parcial?: boolean }
  | { tipo: 'pensando'; id: string; texto: string; parcial?: boolean }
  | { tipo: 'ferramenta'; id: string; nome: string; entrada?: unknown; estado: 'rodando' | 'ok' | 'erro'; saida?: string; diffs?: { arquivo: string; diff: string }[] }
  | { tipo: 'permissao'; id: string; nome: string; resumo: string; detalhe?: string; resposta?: Decisao }
  | { tipo: 'ocupado'; ocupado: boolean }
  | { tipo: 'fim'; custo?: number; tokens?: { entrada?: number; saida?: number }; duracao?: number; erro?: string }
  | { tipo: 'erro'; texto: string }
  | { tipo: 'saiu'; codigo: number | null }
export type EventoNum = Evento & { n: number }
export type InfoChat = { id: string; agente: Agente; titulo: string; alvo: string; cwd: string; viva: boolean; ocupado: boolean; criada: number; modelo?: string }

const FRASE = /^Leia o arquivo [\w\-./]+\.md e siga o que ele pede\. Comece me mostrando o plano\.$/
const MODELO = /^[\w.\-[\]:]{1,60}$/
const MAX_EVENTOS = 5000

type Sessao = InfoChat & {
  proc: ChildProcess
  eventos: EventoNum[]
  n: number
  sempre: Set<string> // ferramentas liberadas "sempre nesta conversa"
  responder(permId: string, d: Decisao): void
  enviar(texto: string): void
  interromper(): void
}

const sessoes = new Map<string, Sessao>()
let seq = 0
let aoEvento: (id: string, e: EventoNum) => void = () => undefined

export function definirSaida(f: (id: string, e: EventoNum) => void): void {
  aoEvento = f
}

function dentro(pasta: string, raiz: string): boolean {
  const rel = relative(resolve(raiz), resolve(pasta))
  return rel !== '' && !rel.startsWith('..') && !isAbsolute(rel)
}

// .cmd/.bat no Windows não abrem sem o cmd; aqui só vão flags fixas, nunca texto do usuário
function iniciar(exe: string, args: string[], cwd: string): ChildProcess {
  const lote = process.platform === 'win32' && /\.(cmd|bat)$/i.test(exe)
  const [cmd, a] = lote ? [process.env.ComSpec || 'cmd.exe', ['/d', '/c', exe, ...args]] : [exe, args]
  return spawn(cmd, a, { cwd, stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true, env: { ...process.env, CLIPATOR_CHAT: '1' } })
}

function emitir(s: Sessao, e: Evento): void {
  const en = { ...e, n: ++s.n } as EventoNum
  if (e.tipo === 'ocupado') s.ocupado = e.ocupado
  s.eventos.push(en)
  if (s.eventos.length > MAX_EVENTOS) s.eventos.splice(0, s.eventos.length - MAX_EVENTOS)
  aoEvento(s.id, en)
}

const texto = (v: unknown): string => (typeof v === 'string' ? v : Array.isArray(v)
  ? v.map((x) => (typeof x === 'object' && x && 'text' in x ? String((x as { text: unknown }).text) : JSON.stringify(x))).join('\n')
  : v == null ? '' : JSON.stringify(v, null, 1))
const curto = (s: string, n = 400): string => (s.length > n ? `${s.slice(0, n)}…` : s)

// ---- Claude Code (stream-json) ------------------------------------------------------------
function abrirClaude(s: Sessao, exe: string, p: PedidoChat): ChildProcess {
  const args = ['-p', '--input-format', 'stream-json', '--output-format', 'stream-json', '--verbose', '--include-partial-messages']
  if (p.modo === 'continuar') args.push('--continue')
  if (p.modelo) args.push('--model', p.modelo)
  const proc = iniciar(exe, args, p.cwd)
  let sessaoId = ''
  let pedidoN = 0
  let msgAtual = 'msg'
  const escrever = (o: unknown): void => {
    proc.stdin?.write(`${JSON.stringify(o)}\n`)
  }
  const pendentes = new Map<string, { input: unknown }>()
  s.responder = (permId, d) => {
    const p0 = pendentes.get(permId)
    if (!p0) return
    pendentes.delete(permId)
    const resposta = d === 'nao' ? { behavior: 'deny', message: 'O usuário recusou no Clipator.' } : { behavior: 'allow', updatedInput: p0.input }
    escrever({ type: 'control_response', response: { subtype: 'success', request_id: permId, response: resposta } })
  }
  s.enviar = (t) => {
    escrever({ type: 'user', message: { role: 'user', content: [{ type: 'text', text: t }] }, parent_tool_use_id: null, session_id: sessaoId })
    emitir(s, { tipo: 'ocupado', ocupado: true })
  }
  s.interromper = () => escrever({ type: 'control_request', request_id: `clipator-${++pedidoN}`, request: { subtype: 'interrupt' } })

  createInterface({ input: proc.stdout! }).on('line', (linha) => {
    let m: Record<string, any>
    try {
      m = JSON.parse(linha)
    } catch {
      return
    }
    if (m.type === 'system' && m.subtype === 'init') {
      sessaoId = m.session_id ?? ''
      s.modelo = m.model
      emitir(s, { tipo: 'sistema', sessao: sessaoId, modelo: m.model })
    } else if (m.type === 'stream_event') {
      const ev = m.event ?? {}
      if (ev.type === 'message_start') msgAtual = ev.message?.id ?? msgAtual
      if (ev.type === 'content_block_delta') {
        const id = `${msgAtual}-${ev.index ?? 0}` // o mesmo id da mensagem final: o texto parcial é trocado por ela
        if (ev.delta?.type === 'text_delta') emitir(s, { tipo: 'texto', id, texto: ev.delta.text ?? '', parcial: true })
        if (ev.delta?.type === 'thinking_delta') emitir(s, { tipo: 'pensando', id, texto: ev.delta.thinking ?? '', parcial: true })
      }
    } else if (m.type === 'assistant') {
      const msg = m.message ?? {}
      ;(msg.content ?? []).forEach((b: Record<string, any>, i: number) => {
        const id = `${msg.id ?? 'msg'}-${i}`
        if (b.type === 'text') emitir(s, { tipo: 'texto', id, texto: b.text ?? '' })
        else if (b.type === 'thinking') emitir(s, { tipo: 'pensando', id, texto: b.thinking ?? '' })
        else if (b.type === 'tool_use') emitir(s, { tipo: 'ferramenta', id: b.id, nome: b.name, entrada: b.input, estado: 'rodando' })
      })
    } else if (m.type === 'user') {
      for (const b of m.message?.content ?? []) {
        if (b?.type === 'tool_result') {
          emitir(s, { tipo: 'ferramenta', id: b.tool_use_id, nome: '', estado: b.is_error ? 'erro' : 'ok', saida: curto(texto(b.content), 4000) })
        }
      }
    } else if (m.type === 'result') {
      emitir(s, {
        tipo: 'fim', custo: m.total_cost_usd, duracao: m.duration_ms,
        tokens: m.usage ? { entrada: m.usage.input_tokens, saida: m.usage.output_tokens } : undefined,
        erro: m.is_error ? texto(m.result) || m.subtype : undefined
      })
      emitir(s, { tipo: 'ocupado', ocupado: false })
    } else if (m.type === 'control_request' && m.request?.subtype === 'can_use_tool') {
      const nome = String(m.request.tool_name ?? 'ferramenta')
      const input = m.request.input ?? {}
      if (s.sempre.has(nome)) {
        pendentes.set(m.request_id, { input })
        s.responder(m.request_id, 'sim')
        return
      }
      pendentes.set(m.request_id, { input })
      emitir(s, { tipo: 'permissao', id: m.request_id, nome, resumo: resumoClaude(nome, input), detalhe: curto(texto(input), 3000) })
    } else if (m.type === 'control_response') {
      /* resposta ao interrupt */
    }
  })
  return proc
}

function resumoClaude(nome: string, input: Record<string, any>): string {
  if (input.command) return `${nome}: ${curto(String(input.command), 300)}`
  if (input.file_path) return `${nome}: ${input.file_path}`
  if (input.url) return `${nome}: ${input.url}`
  if (input.pattern) return `${nome}: ${input.pattern}`
  return nome
}

// ---- Codex (app-server, JSON-RPC) ---------------------------------------------------------
function abrirCodex(s: Sessao, exe: string, p: PedidoChat): ChildProcess {
  const proc = iniciar(exe, ['app-server'], p.cwd)
  let nId = 0
  const esperando = new Map<number, (r: { result?: any; error?: any }) => void>()
  const escrever = (o: unknown): void => {
    proc.stdin?.write(`${JSON.stringify(o)}\n`)
  }
  const pedir = (method: string, params: unknown): Promise<any> => new Promise((ok, falha) => {
    const id = ++nId
    esperando.set(id, (r) => (r.error ? falha(new Error(r.error.message ?? JSON.stringify(r.error))) : ok(r.result)))
    escrever({ id, method, params })
  })
  let thread = ''
  let turno = ''
  const fila: string[] = []
  const pendentes = new Map<string, { rpcId: number | string; legado: boolean; tipo: 'comando' | 'arquivo' }>()
  const arquivos = new Map<string, { arquivo: string; diff: string }[]>() // itemId -> mudanças propostas

  s.responder = (permId, d) => {
    const p0 = pendentes.get(permId)
    if (!p0) return
    pendentes.delete(permId)
    const decision = p0.legado
      ? (d === 'nao' ? 'denied' : d === 'sempre' ? 'approved_for_session' : 'approved')
      : (d === 'nao' ? 'decline' : d === 'sempre' ? 'acceptForSession' : 'accept')
    escrever({ id: p0.rpcId, result: { decision } })
  }
  const enviarAgora = (t: string): void => {
    emitir(s, { tipo: 'ocupado', ocupado: true })
    pedir('turn/start', { threadId: thread, input: [{ type: 'text', text: t, text_elements: [] }] })
      .then((r) => {
        turno = r?.turn?.id ?? turno
      }, (e) => emitir(s, { tipo: 'erro', texto: String(e.message ?? e) }))
  }
  s.enviar = (t) => (thread ? enviarAgora(t) : fila.push(t))
  s.interromper = () => {
    if (thread && turno) void pedir('turn/interrupt', { threadId: thread, turnId: turno }).catch(() => undefined)
  }

  createInterface({ input: proc.stdout! }).on('line', (linha) => {
    let m: Record<string, any>
    try {
      m = JSON.parse(linha)
    } catch {
      return
    }
    // resposta a um pedido nosso
    if (m.id !== undefined && !m.method) {
      esperando.get(m.id)?.(m)
      esperando.delete(m.id)
      return
    }
    const pr = m.params ?? {}
    // pedidos do servidor: aprovações
    if (m.id !== undefined && m.method) {
      const permId = `cx-${m.id}`
      if (m.method === 'item/commandExecution/requestApproval' || m.method === 'execCommandApproval') {
        const cmd = Array.isArray(pr.command) ? pr.command.join(' ') : String(pr.command ?? '')
        if (s.sempre.has('comando')) return escrever({ id: m.id, result: { decision: m.method === 'execCommandApproval' ? 'approved' : 'accept' } })
        pendentes.set(permId, { rpcId: m.id, legado: m.method === 'execCommandApproval', tipo: 'comando' })
        emitir(s, { tipo: 'permissao', id: permId, nome: 'comando', resumo: `Rodar: ${curto(cmd, 300)}`, detalhe: [pr.reason, pr.cwd && `pasta: ${pr.cwd}`].filter(Boolean).join('\n') })
      } else if (m.method === 'item/fileChange/requestApproval' || m.method === 'applyPatchApproval') {
        if (s.sempre.has('arquivo')) return escrever({ id: m.id, result: { decision: m.method === 'applyPatchApproval' ? 'approved' : 'accept' } })
        const mud = arquivos.get(pr.itemId) ?? Object.entries(pr.fileChanges ?? {}).map(([arquivo, c]) => ({ arquivo, diff: texto((c as any)?.unified_diff ?? c) }))
        pendentes.set(permId, { rpcId: m.id, legado: m.method === 'applyPatchApproval', tipo: 'arquivo' })
        emitir(s, { tipo: 'permissao', id: permId, nome: 'arquivo', resumo: `Alterar ${mud.map((x) => x.arquivo).join(', ') || 'arquivos'}`, detalhe: [pr.reason, ...mud.map((x) => x.diff)].filter(Boolean).join('\n') })
      } else {
        escrever({ id: m.id, error: { code: -32601, message: 'Não suportado pelo Clipator' } })
      }
      return
    }
    switch (m.method) {
      case 'item/agentMessage/delta':
        emitir(s, { tipo: 'texto', id: pr.itemId, texto: pr.delta ?? '', parcial: true })
        break
      case 'item/reasoning/summaryTextDelta':
      case 'item/reasoning/textDelta':
        emitir(s, { tipo: 'pensando', id: pr.itemId, texto: pr.delta ?? '', parcial: true })
        break
      case 'item/started':
      case 'item/completed': {
        const it = pr.item ?? {}
        const fim = m.method === 'item/completed'
        if (it.type === 'agentMessage' && fim) emitir(s, { tipo: 'texto', id: it.id, texto: it.text ?? '' })
        else if (it.type === 'reasoning' && fim) emitir(s, { tipo: 'pensando', id: it.id, texto: [...(it.summary ?? []), ...(it.content ?? [])].join('\n') })
        else if (it.type === 'commandExecution') {
          emitir(s, { tipo: 'ferramenta', id: it.id, nome: 'Comando', entrada: { command: it.command, cwd: it.cwd },
            estado: !fim ? 'rodando' : it.exitCode && it.exitCode !== 0 ? 'erro' : 'ok', saida: fim ? curto(texto(it.aggregatedOutput ?? ''), 4000) : undefined })
        } else if (it.type === 'fileChange') {
          const diffs = (it.changes ?? []).map((c: Record<string, any>) => ({ arquivo: String(c.path), diff: String(c.diff ?? '') }))
          arquivos.set(it.id, diffs)
          emitir(s, { tipo: 'ferramenta', id: it.id, nome: 'Arquivos', entrada: { files: diffs.map((d: { arquivo: string }) => d.arquivo) },
            estado: !fim ? 'rodando' : it.status === 'failed' || it.status === 'declined' ? 'erro' : 'ok', diffs })
        } else if (it.type === 'mcpToolCall') {
          emitir(s, { tipo: 'ferramenta', id: it.id, nome: `${it.server ?? 'mcp'}.${it.tool ?? ''}`, entrada: it.arguments,
            estado: !fim ? 'rodando' : it.error ? 'erro' : 'ok', saida: fim ? curto(texto(it.result ?? it.error ?? ''), 4000) : undefined })
        }
        break
      }
      case 'turn/started':
        turno = pr.turn?.id ?? turno
        break
      case 'turn/completed':
        emitir(s, { tipo: 'fim', erro: pr.turn?.status === 'failed' ? texto(pr.turn?.error?.message ?? 'falhou') : undefined })
        emitir(s, { tipo: 'ocupado', ocupado: false })
        break
      case 'thread/tokenUsage/updated': {
        const u = pr.tokenUsage?.total ?? pr.tokenUsage ?? {}
        emitir(s, { tipo: 'fim', tokens: { entrada: u.inputTokens, saida: u.outputTokens } })
        break
      }
      case 'error':
        emitir(s, { tipo: 'erro', texto: texto(pr.error?.message ?? pr.message ?? pr) })
        break
    }
  })

  // começa: initialize, thread nova (ou a última desta pasta) e a primeira mensagem
  void (async () => {
    try {
      await pedir('initialize', { clientInfo: { name: 'clipator', title: 'Clipator', version: '1' }, capabilities: null })
      escrever({ method: 'initialized' })
      const politica = { cwd: p.cwd, approvalPolicy: 'on-request', sandbox: 'workspace-write', ...(p.modelo ? { model: p.modelo } : {}) }
      let r: any = null
      if (p.modo === 'continuar') {
        const lista = await pedir('thread/list', { cwd: p.cwd, limit: 1 }).catch(() => null)
        const ultima = (lista?.data ?? lista?.threads ?? [])[0]?.id
        if (ultima) r = await pedir('thread/resume', { threadId: ultima, ...politica }).catch(() => null)
        if (!r) emitir(s, { tipo: 'sistema', aviso: 'Não achei uma conversa anterior do Codex nesta pasta; comecei uma nova.' })
      }
      r = r ?? await pedir('thread/start', politica)
      thread = r?.thread?.id ?? ''
      s.modelo = r?.model
      const modelos = await pedir('model/list', {}).then((x) => (x?.data ?? x?.models ?? []).map((mm: any) => String(mm.id ?? mm.model ?? mm)), () => undefined)
      emitir(s, { tipo: 'sistema', sessao: thread, modelo: r?.model, modelos })
      for (const t of fila.splice(0)) enviarAgora(t)
    } catch (e) {
      emitir(s, { tipo: 'erro', texto: `Não consegui iniciar o Codex: ${String((e as Error).message ?? e)}` })
    }
  })()
  return proc
}

// ---- sessões ----------------------------------------------------------------------------
export function abrirChat(p: PedidoChat, workspace: string): InfoChat {
  if (p.agente !== 'claude' && p.agente !== 'codex') throw new Error('Só Claude Code ou Codex.')
  if (p.modo !== 'abrir' && p.modo !== 'continuar') throw new Error('Modo inválido.')
  if (!FRASE.test(p.frase)) throw new Error('Frase inicial inesperada.')
  if (p.modelo && !MODELO.test(p.modelo)) throw new Error('Modelo inválido.')
  if (!workspace || !dentro(p.cwd, workspace) || !existsSync(p.cwd)) throw new Error('A pasta da conversa precisa estar dentro do workspace.')
  const exe = resolverCli(p.agente)
  if (!exe) throw new Error(`${p.agente === 'claude' ? 'Claude Code' : 'Codex'} não está instalado.`)
  const id = `chat${++seq}-${Date.now().toString(36)}`
  const s = {
    id, agente: p.agente, titulo: String(p.titulo).slice(0, 120), alvo: String(p.alvo).slice(0, 200), cwd: p.cwd,
    viva: true, ocupado: false, criada: Date.now(), eventos: [], n: 0, sempre: new Set<string>(),
    responder: () => undefined, enviar: () => undefined, interromper: () => undefined
  } as unknown as Sessao
  sessoes.set(id, s)
  s.proc = p.agente === 'claude' ? abrirClaude(s, exe, p) : abrirCodex(s, exe, p)
  let erros = ''
  s.proc.stderr?.on('data', (b: Buffer) => {
    erros = (erros + b.toString('utf-8')).slice(-2000)
  })
  s.proc.on('error', (e) => emitir(s, { tipo: 'erro', texto: `Não consegui abrir: ${e.message}` }))
  s.proc.on('exit', (codigo) => {
    s.viva = false
    if (codigo && erros.trim()) emitir(s, { tipo: 'erro', texto: curto(erros.trim(), 1500) })
    emitir(s, { tipo: 'ocupado', ocupado: false })
    emitir(s, { tipo: 'saiu', codigo })
  })
  // a primeira mensagem é sempre a frase fixa que aponta o pedido.md
  emitir(s, { tipo: 'usuario', texto: p.frase })
  s.enviar(p.frase)
  return info(s)
}

function info(s: Sessao): InfoChat {
  return { id: s.id, agente: s.agente, titulo: s.titulo, alvo: s.alvo, cwd: s.cwd, viva: s.viva, ocupado: s.ocupado, criada: s.criada, modelo: s.modelo }
}

export const listarChats = (): InfoChat[] => [...sessoes.values()].map(info)
export const eventosDo = (id: string): EventoNum[] => sessoes.get(id)?.eventos ?? []

export function enviarChat(id: string, t: string): void {
  const s = sessoes.get(id)
  if (!s?.viva || typeof t !== 'string' || !t.trim()) return
  const msg = t.slice(0, 20000)
  emitir(s, { tipo: 'usuario', texto: msg })
  s.enviar(msg)
}

export function responderChat(id: string, permId: string, d: Decisao): void {
  const s = sessoes.get(id)
  if (!s?.viva || !['sim', 'nao', 'sempre'].includes(d)) return
  const ev = s.eventos.find((e) => e.tipo === 'permissao' && e.id === permId) as (Evento & { tipo: 'permissao' }) | undefined
  if (!ev || ev.resposta) return
  if (d === 'sempre') s.sempre.add(ev.nome)
  ev.resposta = d
  s.responder(permId, d)
  emitir(s, { ...ev, resposta: d })
}

export function interromperChat(id: string): void {
  sessoes.get(id)?.interromper()
}

export function fecharChat(id: string, esperar = false): void {
  const s = sessoes.get(id)
  if (!s?.viva || !s.proc.pid) return
  if (process.platform === 'win32') {
    const args = ['/PID', String(s.proc.pid), '/T', '/F']
    if (esperar) {
      try {
        execFileSync('taskkill', args, { stdio: 'ignore', windowsHide: true })
      } catch {
        /* já tinha fechado */
      }
    } else execFile('taskkill', args, { windowsHide: true }, () => undefined)
  } else s.proc.kill()
}

export function fecharTodosChats(): void {
  for (const id of sessoes.keys()) fecharChat(id, true)
}
