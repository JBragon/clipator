import { useCallback, useEffect, useState } from 'react'
import type { Api, Clip } from '../api'
import { useT } from '../i18n'
import { ponte } from '../ponte'
import type { PedidoConversa } from './ConversaIA'
import { confirmar } from './Confirmar'

type InfoAgente = { nome: string; instalado: boolean; mcp: boolean | null }
type Versao = { id: string; videos: string[]; notas: string; pedido: boolean; escolhido: string | null }

// "Editar com IA": abre o Claude Code ou o Codex do usuário num terminal, na pasta do clip,
// com um pedido.md pronto. Fora do núcleo: o motor só prepara e depois lista o que foi gravado.
export function EditarComIA(props: { api: Api; base: string; clip: Clip; aoMudar(): void; conversar(p: PedidoConversa): Promise<string> }): React.JSX.Element {
  const { api, base, clip, aoMudar, conversar } = props
  const t = useT()
  const url = `${base}/clips/${encodeURIComponent(clip.id)}`
  const [aberto, setAberto] = useState(false)
  const [agentes, setAgentes] = useState<Record<string, InfoAgente>>({})
  const [sugestoes, setSugestoes] = useState<string[]>([])
  const [agente, setAgente] = useState('')
  const [pedido, setPedido] = useState('')
  const [msg, setMsg] = useState('')
  const [versoes, setVersoes] = useState<Versao[]>([])
  const [msgPedido, setMsgPedido] = useState('')

  const carregarVersoes = useCallback(() => {
    api.get<Versao[]>(`${url}/versoes`).then(setVersoes, () => setVersoes([]))
  }, [api, url])

  // a IA grava em edicoes/ no tempo dela: confere de tempos em tempos
  useEffect(() => {
    carregarVersoes()
    const id = setInterval(carregarVersoes, 5000)
    return () => clearInterval(id)
  }, [carregarVersoes])

  const abrirDialogo = async (): Promise<void> => {
    setAberto(true)
    setMsg('')
    const r = await api.get<{ agentes: Record<string, InfoAgente>; sugestoes: string[] }>('/api/edicao-ia')
    setAgentes(r.agentes)
    setSugestoes(r.sugestoes)
    setAgente((a) => a || Object.keys(r.agentes).find((k) => r.agentes[k].instalado) || '')
  }

  // no app a conversa abre no painel do passo 3; fora dele, num terminal externo
  const enviar = async (modo: 'abrir' | 'continuar'): Promise<void> => {
    try {
      setMsg(await conversar({ alvo: { tipo: 'clip', clip: clip.id }, agente: agente as 'claude' | 'codex', modo, pedido }))
      if (ponte.ia) setAberto(false)
      carregarVersoes()
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e))
    }
  }

  const copiar = async (): Promise<void> => {
    const r = await api.post<{ texto: string; pasta: string }>(`${url}/editar-ia/prompt`, { agente, pedido })
    await navigator.clipboard.writeText(r.texto)
    setMsg(t.promptCopiado(r.pasta))
  }

  const registrar = async (): Promise<void> => {
    try {
      await api.post(`/api/edicao-ia/${agente}/registrar-mcp`)
      const r = await api.get<{ agentes: Record<string, InfoAgente> }>('/api/edicao-ia')
      setAgentes(r.agentes)
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e))
    }
  }

  const usar = async (video: string | null): Promise<void> => {
    await api.post(`${url}/versoes/usar`, { video })
    carregarVersoes()
    aoMudar()
  }

  const apagar = async (v: Versao): Promise<void> => {
    if (!(await confirmar({ titulo: t.confirmarApagarVersao(v.id), ok: t.apagar, cancelar: t.cancelar, perigo: true }))) return
    await api.del(`${url}/versoes/${encodeURIComponent(v.id)}`, { confirmar: 'true' })
    carregarVersoes()
    aoMudar()
  }

  // pedido feito no passo 2: reabre (ou abre, se ainda não foi) a conversa do lote na pasta do projeto
  const conversaDoPasso2 = async (): Promise<void> => {
    const p = clip.pedido_ia
    if (!p) return
    try {
      const alvo = p.enviado ? { tipo: 'lote' as const, clips: [clip.id], lote: p.enviado } : { tipo: 'lote' as const, clips: [clip.id], lote: '' }
      setMsgPedido(await conversar({ alvo, agente: p.agente, modo: p.enviado ? 'continuar' : 'abrir' }))
    } catch (e) {
      setMsgPedido(e instanceof Error ? e.message : String(e))
    }
    aoMudar()
  }

  const info = agentes[agente]
  const instalados = Object.entries(agentes).filter(([, a]) => a.instalado)

  return (
    <div className="campo editar-ia">
      <div className="linha">
        <label>{t.edicoesIA}</label>
        <button onClick={() => void abrirDialogo()}>✨ {t.editarComIA}</button>
        {clip.versao && <span className="chip">{t.usandoVersao}</span>}
        {clip.versao && <button className="link" onClick={() => void usar(null)}>{t.voltarOriginal}</button>}
      </div>
      {clip.pedido_ia && (
        <div className="versao-ia">
          <div className="linha">
            <strong>{clip.pedido_ia.enviado ? t.pedidoEnviado(clip.pedido_ia.agente === 'codex' ? 'Codex' : 'Claude Code') : t.pedidoGuardado}</strong>
            <span className="espaco" style={{ flex: 1 }} />
            <button onClick={() => void conversaDoPasso2()}>{clip.pedido_ia.enviado ? t.reabrirConversa : t.abrirConversa}</button>
          </div>
          <pre className="notas-ia">{clip.pedido_ia.texto}</pre>
          {clip.pedido_ia.erro && <p className="erro-txt" style={{ margin: 0 }}>{t.conversaNaoAbriu(clip.pedido_ia.erro)}</p>}
          {msgPedido && <p className="dica" style={{ margin: 0 }}>{msgPedido}</p>}
        </div>
      )}
      {versoes.map((v) => (
        <div key={v.id} className="versao-ia">
          <div className="linha">
            <strong>{v.id}</strong>
            {!v.videos.length && <span className="dica">{t.semVideoEditado}</span>}
            <span className="espaco" />
            <button className="link" onClick={() => void apagar(v)}>{t.apagar}</button>
          </div>
          {v.videos.map((vid) => (
            <div key={vid} className="linha">
              <video src={api.midia(`${clip.pasta}/${vid}`)} controls preload="none" style={{ maxHeight: 200, borderRadius: 6 }} />
              {v.escolhido === vid
                ? <span className="chip" style={{ color: 'var(--ok)' }}>✓ {t.versaoEscolhida}</span>
                : <button onClick={() => void usar(vid)}>{t.usarVersao}</button>}
            </div>
          ))}
          {v.notas && <pre className="notas-ia">{v.notas}</pre>}
        </div>
      ))}

      {aberto && (
        <div className="modal-fundo" onMouseDown={(e) => e.target === e.currentTarget && setAberto(false)}>
          <div className="modal" role="dialog" aria-label={t.editarComIA}>
            <h3>✨ {t.editarComIA}</h3>
            <p className="dica">{t.editarComIADica}</p>
            {!instalados.length && <p className="erro-txt">{t.semCLI}</p>}
            <div className="linha">
              {Object.entries(agentes).map(([k, a]) => (
                <label key={k} className="linha" title={a.instalado ? '' : t.naoInstalado}>
                  <input type="radio" name="agente" disabled={!a.instalado} checked={agente === k} onChange={() => setAgente(k)} /> {a.nome}
                </label>
              ))}
            </div>
            {info?.instalado && info.mcp === false && (
              <div className="aviso-login">
                <span>{t.mcpNaoRegistrado(info.nome)}</span>
                <div className="linha"><button onClick={() => void registrar()}>{t.registrarMCP}</button></div>
              </div>
            )}
            <textarea rows={5} value={pedido} placeholder={t.pedidoEdicaoDica} onChange={(e) => setPedido(e.target.value)} />
            <div className="linha" style={{ flexWrap: 'wrap' }}>
              {sugestoes.map((s) => (
                <button key={s} className="chip" onClick={() => setPedido((p) => (p ? `${p}\n${s}` : s))}>+ {s}</button>
              ))}
            </div>
            <div className="linha">
              <button className="primario" disabled={!info?.instalado} onClick={() => void enviar('abrir')}>{t.abrirConversa}</button>
              <button disabled={!info?.instalado} onClick={() => void enviar('continuar')}>{t.continuarConversa}</button>
              <button onClick={() => void copiar()}>{t.copiarPrompt}</button>
              <span className="espaco" style={{ flex: 1 }} />
              <button onClick={() => setAberto(false)}>{t.fechar}</button>
            </div>
            {msg && <p className="dica">{msg}</p>}
          </div>
        </div>
      )}
    </div>
  )
}
