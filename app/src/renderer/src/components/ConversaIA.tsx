import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import '@xterm/xterm/css/xterm.css'
import type { Api, Clip } from '../api'
import { useT } from '../i18n'
import { ponte, type AgenteIA, type Decisao, type EventoChat, type InfoChat, type InfoSessao } from '../ponte'
import { Markdown } from './Markdown'

// O que abrir: a conversa de um clip (pasta do clip) ou a do lote do passo 2 (pasta do projeto)
export type AlvoConversa = { tipo: 'clip'; clip: string } | { tipo: 'lote'; clips: string[]; lote: string }
export type PedidoConversa = { alvo: AlvoConversa; agente: AgenteIA; modo: 'abrir' | 'continuar'; pedido?: string; externo?: boolean; modelo?: string }
type Preparado = { cwd: string; frase: string; pasta: string }
type ModoPainel = 'chat' | 'terminal'

const LARGURA_PADRAO = 520
const chaveLargura = 'clipator.conversa.largura'
const chaveRecolhido = 'clipator.conversa.recolhido'
const chaveModo = 'clipator.conversa.modo'
const ler = (k: string): string | null => {
  try {
    return localStorage.getItem(k)
  } catch {
    return null
  }
}
const gravar = (k: string, v: string): void => {
  try {
    localStorage.setItem(k, v)
  } catch {
    /* sem armazenamento: vale só nesta sessão */
  }
}
export const modoPainel = (): ModoPainel => (ler(chaveModo) === 'terminal' ? 'terminal' : 'chat')

export const idAlvo = (canal: string, projeto: string, a: AlvoConversa): string =>
  a.tipo === 'clip' ? `${canal}/${projeto}/${a.clip}` : `${canal}/${projeto}/lote:${a.lote}`

const MODELOS_CLAUDE = ['opus', 'sonnet', 'haiku']

// Prepara o pedido no motor e abre a CLI: na conversa estilizada, no terminal embutido (Electron)
// ou numa janela externa. Devolve o id da conversa aberta no app (ou null, se foi para fora).
export async function abrirConversa(api: Api, base: string, canal: string, projeto: string, p: PedidoConversa,
  clips: Clip[], tamanho: { cols: number; rows: number }): Promise<string | null> {
  const externo = p.externo || !ponte.ia || !ponte.chat
  const destino = externo ? 'terminal' : 'app'
  const r = p.alvo.tipo === 'clip'
    ? await api.post<Preparado>(`${base}/clips/${encodeURIComponent(p.alvo.clip)}/editar-ia`, { agente: p.agente, modo: p.modo, pedido: p.pedido ?? '', destino })
    : await api.post<Preparado>(`${base}/pedido-ia`, { clips: p.alvo.clips, agente: p.agente, modo: p.modo, destino })
  if (externo || !ponte.ia || !ponte.chat) return null
  const titulo = p.alvo.tipo === 'clip'
    ? (clips.find((c) => p.alvo.tipo === 'clip' && c.id === p.alvo.clip)?.titulo || p.alvo.clip)
    : `Lote (${p.alvo.clips.length})`
  const pedido = { agente: p.agente, modo: p.modo, cwd: r.cwd, frase: r.frase, titulo, alvo: idAlvo(canal, projeto, p.alvo) }
  if (modoPainel() === 'terminal') return (await ponte.ia.abrir(pedido, tamanho.cols, tamanho.rows)).id
  return (await ponte.chat.abrir({ ...pedido, ...(p.modelo ? { modelo: p.modelo } : {}) })).id
}

// Painel da direita do passo 3: a conversa com a IA dentro do app, com a largura ajustável.
export function PainelConversa(props: {
  api: Api
  base: string
  canal: string
  projeto: string
  clips: Clip[]
  ativa: string | null
  setAtiva(id: string | null): void
  versao: number // muda quando uma conversa nova é aberta de fora do painel
  alvoPreferido?: { clip: string; n: number } | null // o editor pede "conversar sobre este clip"
  editorAberto?: boolean // com o editor de vídeo aberto, o painel começa recolhido para dar espaço
}): React.JSX.Element {
  const { api, base, canal, projeto, clips, ativa, setAtiva, versao, alvoPreferido, editorAberto } = props
  const t = useT()
  const [largura, setLargura] = useState(() => Number(ler(chaveLargura)) || LARGURA_PADRAO)
  const [recolhido, setRecolhido] = useState(() => ler(chaveRecolhido) === '1')
  const [modo, setModo] = useState<ModoPainel>(modoPainel)
  const [terminais, setTerminais] = useState<InfoSessao[]>([])
  const [chats, setChats] = useState<InfoChat[]>([])
  const [disp, setDisp] = useState<Record<AgenteIA, boolean>>({ claude: false, codex: false })
  const [agente, setAgente] = useState<AgenteIA>('claude')
  const [modelo, setModelo] = useState('')
  const [alvoSel, setAlvoSel] = useState('')
  const [msg, setMsg] = useState('')
  const tamanho = useRef({ cols: 100, rows: 30 })
  const prefixo = `${canal}/${projeto}/`

  const lote = clips.find((c) => c.pedido_ia?.enviado)?.pedido_ia?.enviado ?? null
  const clipsDoLote = lote ? clips.filter((c) => c.pedido_ia?.enviado === lote).map((c) => c.id) : []
  const alvos: { chave: string; nome: string; alvo: AlvoConversa }[] = [
    ...(lote ? [{ chave: `lote:${lote}`, nome: t.conversaLote(clipsDoLote.length), alvo: { tipo: 'lote' as const, clips: clipsDoLote, lote } }] : []),
    ...clips.map((c) => ({ chave: c.id, nome: c.titulo || c.id, alvo: { tipo: 'clip' as const, clip: c.id } }))
  ]
  const sessoes: { id: string; agente: AgenteIA; titulo: string; alvo: string; viva: boolean; criada: number }[] = modo === 'chat' ? chats : terminais
  const sessao = sessoes.find((s) => s.id === ativa) ?? null
  const alvoAtual = alvos.find((a) => a.chave === alvoSel) ?? alvos.find((a) => sessao && idAlvo(canal, projeto, a.alvo) === sessao.alvo) ?? alvos[0]

  const recarregar = useCallback(() => {
    if (ponte.ia) void ponte.ia.listar().then((l) => setTerminais(l.filter((s) => s.alvo.startsWith(prefixo))))
    if (ponte.chat) void ponte.chat.listar().then((l) => setChats(l.filter((s) => s.alvo.startsWith(prefixo))))
  }, [prefixo])

  useEffect(() => {
    if (!ponte.ia) return
    void ponte.ia.disponivel().then((d) => {
      setDisp(d)
      setAgente((a) => (d[a] ? a : d.claude ? 'claude' : d.codex ? 'codex' : a))
    })
    recarregar()
    const tirar = [ponte.ia.aoSair(() => recarregar()), ponte.chat?.aoEvento((_id, e) => (e.tipo === 'saiu' || e.tipo === 'ocupado') && recarregar())]
    return () => tirar.forEach((f) => f?.())
  }, [recarregar, versao])

  // sem conversa escolhida: mostra a mais recente deste projeto (uma recém-aberta pode ainda não
  // estar na lista; por isso só escolhe quando não há nenhuma)
  useEffect(() => {
    if (!ativa && sessoes.length) setAtiva(sessoes[sessoes.length - 1].id)
  }, [ativa, sessoes, setAtiva])

  // conversa aberta de fora do painel (Editar com IA, lote do passo 2) num modo: o painel segue
  useEffect(() => {
    if (ativa?.startsWith('chat') && modo !== 'chat') setModo('chat')
    else if (ativa && !ativa.startsWith('chat') && modo !== 'terminal' && terminais.some((s) => s.id === ativa)) setModo('terminal')
  }, [ativa]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (editorAberto) setRecolhido(true)
    else setRecolhido(ler(chaveRecolhido) === '1')
  }, [editorAberto])

  useEffect(() => {
    if (!alvoPreferido) return
    setAlvoSel(alvoPreferido.clip)
    setRecolhido(false)
    gravar(chaveRecolhido, '0')
  }, [alvoPreferido])

  const trocarModo = (m: ModoPainel): void => {
    setModo(m)
    gravar(chaveModo, m)
    const lista = m === 'chat' ? chats : terminais
    setAtiva(lista.length ? lista[lista.length - 1].id : null)
  }

  const iniciar = async (modoAbrir: 'abrir' | 'continuar', externo = false): Promise<void> => {
    if (!alvoAtual) return
    setMsg('')
    try {
      const id = await abrirConversa(api, base, canal, projeto, { alvo: alvoAtual.alvo, agente, modo: modoAbrir, externo, modelo: modelo || undefined },
        clips, tamanho.current)
      if (id) {
        setAtiva(id)
        recarregar()
      } else setMsg(t.conversaExterna)
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e))
    }
  }

  // barra vertical: arrastar muda a largura; duplo clique volta ao padrão
  const arrastar = (e: React.PointerEvent<HTMLDivElement>): void => {
    e.preventDefault()
    const alca = e.currentTarget
    alca.setPointerCapture(e.pointerId)
    const pai = alca.parentElement?.parentElement?.getBoundingClientRect()
    const mover = (ev: PointerEvent): void => {
      if (!pai) return
      const max = Math.max(360, pai.width * 0.75)
      const l = Math.round(Math.min(max, Math.max(320, pai.right - ev.clientX)))
      setLargura(l)
      gravar(chaveLargura, String(l))
    }
    const soltar = (): void => {
      alca.removeEventListener('pointermove', mover)
      alca.removeEventListener('pointerup', soltar)
    }
    alca.addEventListener('pointermove', mover)
    alca.addEventListener('pointerup', soltar)
  }
  const alternar = (): void => {
    setRecolhido((r) => {
      gravar(chaveRecolhido, r ? '0' : '1')
      return !r
    })
  }

  if (recolhido) {
    return (
      <aside className="conversa-ia recolhida">
        <button className="link" title={t.mostrarConversa} aria-label={t.mostrarConversa} onClick={alternar}>⟨ ✨</button>
      </aside>
    )
  }

  const chatAtivo = modo === 'chat' ? chats.find((s) => s.id === ativa) ?? null : null
  const termAtivo = modo === 'terminal' ? terminais.find((s) => s.id === ativa) ?? null : null
  const modelos = agente === 'claude' ? MODELOS_CLAUDE : []
  return (
    <aside className="conversa-ia" style={{ width: largura }}>
      <div className="divisor-vertical" role="separator" aria-orientation="vertical" aria-label={t.larguraConversa} title={t.larguraConversa}
        onPointerDown={arrastar} onDoubleClick={() => {
          setLargura(LARGURA_PADRAO)
          gravar(chaveLargura, String(LARGURA_PADRAO))
        }} />
      <div className="conversa-topo">
        <div className="linha">
          <strong>✨ {t.conversaComIA}</strong>
          <span className="espaco" style={{ flex: 1 }} />
          {ponte.ia && (
            <label className="linha dica" title={t.modoTerminalDica}>
              <input type="checkbox" checked={modo === 'terminal'} onChange={(e) => trocarModo(e.target.checked ? 'terminal' : 'chat')} /> {t.modoTerminal}
            </label>
          )}
          <button className="link" title={t.esconderConversa} aria-label={t.esconderConversa} onClick={alternar}>⟩</button>
        </div>
        {!ponte.ia && <p className="dica" style={{ margin: 0 }}>{t.conversaSoNoApp}</p>}
        <div className="linha" style={{ flexWrap: 'wrap' }}>
          <select value={agente} onChange={(e) => {
            setAgente(e.target.value as AgenteIA)
            setModelo('')
          }} aria-label={t.agenteIA}>
            {(['claude', 'codex'] as const).map((a) => (
              <option key={a} value={a} disabled={!!ponte.ia && !disp[a]}>{a === 'claude' ? 'Claude Code' : 'Codex'}{ponte.ia && !disp[a] ? ` (${t.naoInstalado})` : ''}</option>
            ))}
          </select>
          {modo === 'chat' && ponte.chat && (
            <select value={modelo} onChange={(e) => setModelo(e.target.value)} aria-label={t.modelo} title={t.modeloDica}>
              <option value="">{t.modeloPadrao}</option>
              {modelos.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          )}
          <select value={alvoAtual?.chave ?? ''} onChange={(e) => setAlvoSel(e.target.value)} aria-label={t.alvoConversa} style={{ maxWidth: 220 }}>
            {alvos.map((a) => <option key={a.chave} value={a.chave}>{a.nome}</option>)}
          </select>
        </div>
        <div className="linha" style={{ flexWrap: 'wrap' }}>
          {ponte.ia && <button className="primario" disabled={!alvoAtual || !disp[agente]} onClick={() => void iniciar('abrir')}>{t.novaConversa}</button>}
          {ponte.ia && <button disabled={!alvoAtual || !disp[agente]} onClick={() => void iniciar('continuar')}>{t.continuar}</button>}
          {termAtivo && <button disabled={!termAtivo.viva} onClick={() => void ponte.ia?.parar(termAtivo.id).then(recarregar)}>{t.parar}</button>}
          {chatAtivo && <button disabled={!chatAtivo.viva} onClick={() => void ponte.chat?.fechar(chatAtivo.id).then(recarregar)} title={t.encerrarDica}>{t.encerrar}</button>}
          <button disabled={!alvoAtual} onClick={() => void iniciar('abrir', true)}>{t.terminalExterno}</button>
        </div>
        {sessoes.length > 1 && (
          <select value={ativa ?? ''} onChange={(e) => setAtiva(e.target.value)} aria-label={t.conversas}>
            {sessoes.map((s) => (
              <option key={s.id} value={s.id}>
                {s.viva ? '●' : '○'} {s.agente === 'claude' ? 'Claude' : 'Codex'} · {s.titulo} · {new Date(s.criada).toLocaleTimeString()}
              </option>
            ))}
          </select>
        )}
        {msg && <p className="dica" style={{ margin: 0 }}>{msg}</p>}
      </div>
      <div className="conversa-corpo">
        {modo === 'chat' && chatAtivo && <ChatIA key={chatAtivo.id} info={chatAtivo} />}
        {modo === 'terminal' && termAtivo && (
          <>
            <TerminalIA key={termAtivo.id} id={termAtivo.id} aoTamanho={(cols, rows) => (tamanho.current = { cols, rows })} />
            {!termAtivo.viva && <div className="conversa-fim">{t.conversaTerminou((termAtivo as InfoSessao).codigo ?? 0)}</div>}
          </>
        )}
        {!(modo === 'chat' ? chatAtivo : termAtivo) && (
          <p className="dica" style={{ padding: 12 }}>{ponte.ia ? t.semConversa : t.conversaSoNoAppDica}</p>
        )}
      </div>
    </aside>
  )
}

// ---- conversa estilizada ------------------------------------------------------------------
type Item =
  | { k: 'usuario'; id: string; texto: string }
  | { k: 'texto'; id: string; texto: string }
  | { k: 'pensando'; id: string; texto: string }
  | { k: 'ferramenta'; id: string; nome: string; entrada?: unknown; estado: 'rodando' | 'ok' | 'erro'; saida?: string; diffs?: { arquivo: string; diff: string }[] }
  | { k: 'permissao'; id: string; nome: string; resumo: string; detalhe?: string; resposta?: Decisao }
  | { k: 'fim'; id: string; custo?: number; tokens?: { entrada?: number; saida?: number }; duracao?: number; erro?: string }
  | { k: 'aviso'; id: string; texto: string; erro?: boolean }

// junta os eventos na lista de mensagens que a tela mostra
function juntar(eventos: EventoChat[]): { itens: Item[]; ocupado: boolean; modelo?: string; viva: boolean } {
  const itens: Item[] = []
  const pos = new Map<string, number>()
  let ocupado = false
  let modelo: string | undefined
  let viva = true
  const achar = (k: string, id: string): number | undefined => pos.get(`${k}:${id}`)
  const por = (it: Item): void => {
    pos.set(`${it.k}:${it.id}`, itens.length)
    itens.push(it)
  }
  for (const e of eventos) {
    switch (e.tipo) {
      case 'usuario':
        por({ k: 'usuario', id: `u${e.n}`, texto: e.texto })
        break
      case 'texto':
      case 'pensando': {
        const i = achar(e.tipo, e.id)
        if (i === undefined) por({ k: e.tipo, id: e.id, texto: e.texto })
        else (itens[i] as { texto: string }).texto = e.parcial ? (itens[i] as { texto: string }).texto + e.texto : e.texto
        break
      }
      case 'ferramenta': {
        const i = achar('ferramenta', e.id)
        if (i === undefined) por({ k: 'ferramenta', id: e.id, nome: e.nome, entrada: e.entrada, estado: e.estado, saida: e.saida, diffs: e.diffs })
        else {
          const f = itens[i] as Extract<Item, { k: 'ferramenta' }>
          itens[i] = { ...f, nome: f.nome || e.nome, entrada: f.entrada ?? e.entrada, estado: e.estado, saida: e.saida ?? f.saida, diffs: e.diffs ?? f.diffs }
        }
        break
      }
      case 'permissao': {
        const i = achar('permissao', e.id)
        const it: Item = { k: 'permissao', id: e.id, nome: e.nome, resumo: e.resumo, detalhe: e.detalhe, resposta: e.resposta }
        if (i === undefined) por(it)
        else itens[i] = it
        break
      }
      case 'fim': {
        const ult = itens[itens.length - 1]
        if (ult?.k === 'fim') itens[itens.length - 1] = { ...ult, custo: e.custo ?? ult.custo, tokens: e.tokens ?? ult.tokens, duracao: e.duracao ?? ult.duracao, erro: e.erro ?? ult.erro }
        else por({ k: 'fim', id: `f${e.n}`, custo: e.custo, tokens: e.tokens, duracao: e.duracao, erro: e.erro })
        break
      }
      case 'ocupado':
        ocupado = e.ocupado
        break
      case 'sistema':
        modelo = e.modelo ?? modelo
        if (e.aviso) por({ k: 'aviso', id: `a${e.n}`, texto: e.aviso })
        break
      case 'erro':
        por({ k: 'aviso', id: `e${e.n}`, texto: e.texto, erro: true })
        break
      case 'saiu':
        viva = false
        break
    }
  }
  return { itens, ocupado, modelo, viva }
}

// contexto que dá para anexar à mensagem: arquivos da pasta da conversa
function contextos(frase: string, lote: boolean): { rotulo: string; caminho: string }[] {
  const m = /Leia o arquivo (\S+\.md)/.exec(frase)
  const pedido = m?.[1] ?? ''
  if (lote) return pedido ? [{ rotulo: 'pedido-lote.md', caminho: pedido }] : []
  return [
    { rotulo: 'clip', caminho: 'saida.mp4' },
    ...(pedido ? [{ rotulo: 'pedido.md', caminho: pedido }] : []),
    { rotulo: 'legenda', caminho: 'legenda.srt' }
  ]
}

function ChatIA(props: { info: InfoChat }): React.JSX.Element {
  const { info } = props
  const t = useT()
  const [eventos, setEventos] = useState<EventoChat[]>([])
  const [texto, setTexto] = useState('')
  const [anexos, setAnexos] = useState<Set<string>>(new Set())
  const lista = useRef<HTMLDivElement>(null)
  const colado = useRef(true) // a lista segue o fim enquanto o usuário não sobe para ler

  // repõe a conversa e segue os eventos novos (sem repetir: cada evento tem um número)
  useEffect(() => {
    const chat = ponte.chat
    if (!chat) return
    let visto = -1
    const pend: EventoChat[] = []
    const tirar = chat.aoEvento((id, e) => {
      if (id !== info.id) return
      if (visto < 0) pend.push(e)
      else if (e.n > visto) {
        visto = e.n
        setEventos((l) => [...l, e])
      }
    })
    void chat.eventos(info.id).then((l) => {
      visto = l.length ? l[l.length - 1].n : 0
      const novos = pend.filter((e) => e.n > visto)
      if (novos.length) visto = novos[novos.length - 1].n
      setEventos([...l, ...novos])
    })
    return tirar
  }, [info.id])

  const { itens, ocupado, modelo, viva } = useMemo(() => juntar(eventos), [eventos])
  const frase = eventos.find((e) => e.tipo === 'usuario')
  const ctx = contextos(frase && frase.tipo === 'usuario' ? frase.texto : '', info.alvo.includes('/lote:'))

  useEffect(() => {
    const el = lista.current
    if (el && colado.current) el.scrollTop = el.scrollHeight
  }, [itens])

  const enviar = (): void => {
    const msg = texto.trim()
    if (!msg || !ponte.chat || !viva) return
    const extra = ctx.filter((c) => anexos.has(c.rotulo)).map((c) => c.caminho)
    void ponte.chat.enviar(info.id, extra.length ? `${msg}\n\n${t.contextoAnexado}: ${extra.join(', ')}` : msg)
    setTexto('')
    colado.current = true
  }

  return (
    <div className="chat-ia">
      <div className="chat-lista" ref={lista} onScroll={(e) => {
        const el = e.currentTarget
        colado.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40
      }}>
        {itens.map((it) => <ItemChat key={`${it.k}:${it.id}`} it={it} chatId={info.id} />)}
        {ocupado && <div className="chat-trabalhando"><span className="pontos"><i /><i /><i /></span> {t.trabalhando}</div>}
        {!viva && <div className="chat-aviso">{t.conversaEncerrada}</div>}
      </div>
      <div className="chat-compositor">
        {ctx.length > 0 && (
          <div className="linha chips-contexto">
            {ctx.map((c) => (
              <button key={c.rotulo} className={`chip ${anexos.has(c.rotulo) ? 'ativo' : ''}`} title={c.caminho} onClick={() => {
                const n = new Set(anexos)
                if (n.has(c.rotulo)) n.delete(c.rotulo)
                else n.add(c.rotulo)
                setAnexos(n)
              }}>{anexos.has(c.rotulo) ? '✓' : '+'} {c.rotulo}</button>
            ))}
          </div>
        )}
        <textarea rows={3} value={texto} disabled={!viva} placeholder={viva ? t.mensagemDica : t.conversaEncerrada}
          onChange={(e) => setTexto(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault()
              enviar()
            }
          }} />
        <div className="linha">
          <span className="dica">{info.agente === 'claude' ? 'Claude Code' : 'Codex'}{modelo ? ` · ${modelo}` : ''}</span>
          <span className="espaco" style={{ flex: 1 }} />
          {ocupado && <button onClick={() => void ponte.chat?.interromper(info.id)} title={t.pararRespostaDica}>■ {t.parar}</button>}
          <button className="primario" disabled={!viva || !texto.trim()} onClick={enviar}>{t.enviar}</button>
        </div>
      </div>
    </div>
  )
}

function ItemChat(props: { it: Item; chatId: string }): React.JSX.Element | null {
  const { it, chatId } = props
  const t = useT()
  switch (it.k) {
    case 'usuario':
      return <div className="msg msg-usuario">{it.texto}</div>
    case 'texto':
      return it.texto.trim() ? <div className="msg msg-ia"><Markdown texto={it.texto} /></div> : null
    case 'pensando':
      return it.texto.trim() ? (
        <details className="msg-pensando">
          <summary>💭 {t.pensamento}</summary>
          <div className="dica"><Markdown texto={it.texto} /></div>
        </details>
      ) : null
    case 'ferramenta':
      return <CartaoFerramenta it={it} />
    case 'permissao':
      return (
        <div className={`cartao-permissao ${it.resposta ? 'respondida' : ''}`}>
          <div className="linha"><strong>🔐 {t.pedePermissao}</strong></div>
          <div className="resumo">{it.resumo}</div>
          {it.detalhe && (
            <details>
              <summary className="dica">{t.detalhes}</summary>
              <pre>{it.detalhe}</pre>
            </details>
          )}
          {it.resposta ? (
            <div className="dica">{it.resposta === 'nao' ? `✗ ${t.recusado}` : it.resposta === 'sempre' ? `✓ ${t.aprovadoSempre}` : `✓ ${t.aprovado}`}</div>
          ) : (
            <div className="linha" style={{ flexWrap: 'wrap' }}>
              <button className="primario" onClick={() => void ponte.chat?.responder(chatId, it.id, 'sim')}>{t.aprovar}</button>
              <button onClick={() => void ponte.chat?.responder(chatId, it.id, 'nao')}>{t.recusar}</button>
              <button className="link" onClick={() => void ponte.chat?.responder(chatId, it.id, 'sempre')}>{t.sempreNestaConversa}</button>
            </div>
          )}
        </div>
      )
    case 'fim': {
      const partes = [
        it.duracao ? `${(it.duracao / 1000).toFixed(1)} s` : '',
        it.tokens?.entrada || it.tokens?.saida ? `${t.tokens}: ${it.tokens?.entrada ?? 0} ↑ ${it.tokens?.saida ?? 0} ↓` : '',
        typeof it.custo === 'number' ? `US$ ${it.custo.toFixed(4)}` : ''
      ].filter(Boolean)
      return (
        <div className="chat-rodape">
          {it.erro && <span className="erro-txt">{it.erro}</span>}
          {partes.join(' · ')}
        </div>
      )
    }
    case 'aviso':
      return <div className={`chat-aviso ${it.erro ? 'erro-txt' : ''}`}>{it.texto}</div>
  }
}

// resumo de uma linha do que a ferramenta recebeu
function resumoEntrada(nome: string, e: unknown): string {
  if (!e || typeof e !== 'object') return ''
  const o = e as Record<string, unknown>
  const v = o.command ?? o.file_path ?? o.path ?? o.pattern ?? o.url ?? o.query ?? (Array.isArray(o.files) ? (o.files as string[]).join(', ') : undefined)
  if (typeof v === 'string') return v.length > 120 ? `${v.slice(0, 120)}…` : v
  return nome === 'TodoWrite' ? '' : JSON.stringify(o).slice(0, 120)
}

// diff de uma edição do Claude (Edit/MultiEdit/Write) a partir da entrada da ferramenta
function diffsDaEntrada(nome: string, e: unknown): { arquivo: string; diff: string }[] {
  if (!e || typeof e !== 'object') return []
  const o = e as Record<string, unknown>
  const arquivo = String(o.file_path ?? o.path ?? '')
  const linhas = (s: unknown, p: string): string => String(s ?? '').split('\n').map((l) => p + l).join('\n')
  if (nome === 'Edit' && (o.old_string !== undefined || o.new_string !== undefined)) return [{ arquivo, diff: `${linhas(o.old_string, '-')}\n${linhas(o.new_string, '+')}` }]
  if (nome === 'MultiEdit' && Array.isArray(o.edits)) {
    return [{ arquivo, diff: (o.edits as Record<string, unknown>[]).map((x) => `${linhas(x.old_string, '-')}\n${linhas(x.new_string, '+')}`).join('\n@@\n') }]
  }
  if (nome === 'Write' && typeof o.content === 'string') return [{ arquivo, diff: linhas(o.content.slice(0, 6000), '+') }]
  return []
}

function CartaoFerramenta(props: { it: Extract<Item, { k: 'ferramenta' }> }): React.JSX.Element {
  const { it } = props
  const t = useT()
  const diffs = it.diffs?.length ? it.diffs : diffsDaEntrada(it.nome, it.entrada)
  const icone = it.estado === 'rodando' ? '⏳' : it.estado === 'erro' ? '✗' : '✓'
  return (
    <details className={`cartao-ferramenta ${it.estado}`}>
      <summary>
        <span className="estado">{icone}</span> <strong>{it.nome || t.ferramenta}</strong> <span className="dica">{resumoEntrada(it.nome, it.entrada)}</span>
      </summary>
      {diffs.map((d, i) => (
        <div key={i} className="diff">
          <div className="dica">{d.arquivo}</div>
          <pre>{d.diff.split('\n').map((l, j) => (
            <span key={j} className={l.startsWith('+') && !l.startsWith('+++') ? 'mais' : l.startsWith('-') && !l.startsWith('---') ? 'menos' : l.startsWith('@@') ? 'meta' : ''}>{l || ' '}</span>
          ))}</pre>
        </div>
      ))}
      {it.entrada !== undefined && !diffs.length && <pre className="entrada">{typeof it.entrada === 'string' ? it.entrada : JSON.stringify(it.entrada, null, 1)}</pre>}
      {it.saida && <pre className="saida">{it.saida}</pre>}
    </details>
  )
}

// ---- terminal (modo terminal) -------------------------------------------------------------
// A tela da conversa. Ao montar, repõe o que a CLI escreveu enquanto ela estava fechada.
function TerminalIA(props: { id: string; aoTamanho(cols: number, rows: number): void }): React.JSX.Element {
  const { id, aoTamanho } = props
  const el = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const ia = ponte.ia
    if (!ia || !el.current) return
    const css = getComputedStyle(document.documentElement)
    const cor = (v: string, padrao: string): string => css.getPropertyValue(v).trim() || padrao
    const term = new Terminal({
      cursorBlink: true,
      fontFamily: 'Cascadia Mono, Consolas, Menlo, monospace',
      fontSize: 13,
      scrollback: 5000,
      theme: { background: cor('--fundo', '#1e1e1e'), foreground: cor('--texto', '#d4d4d4'), cursor: cor('--texto', '#d4d4d4') }
    })
    const fit = new FitAddon()
    term.loadAddon(fit)
    term.open(el.current)
    let visto = -1 // até onde a tela já mostrou (contagem de caracteres da CLI)
    const pendentes: [string, number][] = []
    const tirar = ia.aoDados((sid, d, total) => {
      if (sid !== id) return
      if (visto < 0) pendentes.push([d, total])
      else if (total > visto) {
        term.write(d.slice(Math.max(0, d.length - (total - visto))))
        visto = total
      }
    })
    void ia.saida(id).then(({ texto, total }) => {
      term.write(texto)
      visto = total
      for (const [d, n] of pendentes) {
        if (n > visto) {
          term.write(d.slice(Math.max(0, d.length - (n - visto))))
          visto = n
        }
      }
    })
    const entrada = term.onData((d) => ia.escrever(id, d))
    const ajustar = (): void => {
      if (!el.current?.offsetWidth) return
      try {
        fit.fit()
        ia.redimensionar(id, term.cols, term.rows)
        aoTamanho(term.cols, term.rows)
      } catch {
        /* ainda sem tamanho */
      }
    }
    const obs = new ResizeObserver(ajustar)
    obs.observe(el.current)
    ajustar()
    term.focus()
    return () => {
      obs.disconnect()
      tirar()
      entrada.dispose()
      term.dispose()
    }
  }, [id]) // eslint-disable-line react-hooks/exhaustive-deps

  return <div className="terminal-ia" ref={el} />
}
