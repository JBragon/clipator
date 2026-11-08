import { useEffect, useState } from 'react'
import type { Api } from '../api'
import { useT } from '../i18n'

export type InfoAgente = { nome: string; instalado: boolean; mcp: boolean | null }
export type PedidoIA = { agente: 'claude' | 'codex'; texto: string; abrir_ao_terminar: boolean; enviado?: string | null; erro?: string | null }

// Claude Code e Codex instalados neste computador e as sugestões rápidas do motor
// comMcp: pergunta também se o MCP está registrado, o que leva segundos (só quem mostra esse aviso precisa)
export function useAgentesIA(api: Api, ativo: boolean, comMcp = false): { agentes: Record<string, InfoAgente>; sugestoes: string[]; recarregar(): void } {
  const [agentes, setAgentes] = useState<Record<string, InfoAgente>>({})
  const [sugestoes, setSugestoes] = useState<string[]>([])
  const [n, setN] = useState(0)
  useEffect(() => {
    if (!ativo) return
    api.get<{ agentes: Record<string, InfoAgente>; sugestoes: string[] }>('/api/edicao-ia', { mcp: String(comMcp) }).then((r) => {
      setAgentes(r.agentes)
      setSugestoes(r.sugestoes)
    }, () => undefined)
  }, [api, ativo, comMcp, n])
  return { agentes, sugestoes, recarregar: () => setN((x) => x + 1) }
}

// Passo 2: pedido opcional para a IA, guardado nos clips criados. Quando o render do lote termina,
// o motor abre UMA conversa para todos eles (o usuário aprova cada ação no terminal).
export function PainelPedidoIA(props: { api: Api; pedido: PedidoIA | null; setPedido(p: PedidoIA | null): void }): React.JSX.Element {
  const { api, pedido, setPedido } = props
  const t = useT()
  const aberto = pedido !== null
  const { agentes, sugestoes } = useAgentesIA(api, aberto, true)
  const instalados = Object.entries(agentes).filter(([, a]) => a.instalado)

  // escolhe o primeiro instalado quando a lista chega
  useEffect(() => {
    if (pedido && instalados.length && !agentes[pedido.agente]?.instalado) setPedido({ ...pedido, agente: instalados[0][0] as PedidoIA['agente'] })
  }, [agentes]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!pedido) {
    return (
      <button className="link" onClick={() => setPedido({ agente: 'claude', texto: '', abrir_ao_terminar: true })}>
        ✨ {t.pedidoParaIA}
      </button>
    )
  }
  const info = agentes[pedido.agente]
  return (
    <div className="pedido-ia-passo2">
      <div className="linha">
        <strong>✨ {t.pedidoParaIA}</strong>
        <span className="dica">{t.pedidoParaIADica}</span>
        <span className="espaco" style={{ flex: 1 }} />
        <button className="link" onClick={() => setPedido(null)}>{t.semPedidoIA}</button>
      </div>
      {Object.keys(agentes).length > 0 && !instalados.length && <p className="erro-txt">{t.semCLI}</p>}
      <div className="linha">
        {Object.entries(agentes).map(([k, a]) => (
          <label key={k} className="linha" title={a.instalado ? '' : t.naoInstalado}>
            <input type="radio" name="agente-passo2" disabled={!a.instalado} checked={pedido.agente === k}
              onChange={() => setPedido({ ...pedido, agente: k as PedidoIA['agente'] })} /> {a.nome}
          </label>
        ))}
        {info?.instalado && info.mcp === false && <span className="dica">{t.mcpNaoRegistrado(info.nome)}</span>}
      </div>
      <textarea rows={3} value={pedido.texto} placeholder={t.pedidoEdicaoDica} onChange={(e) => setPedido({ ...pedido, texto: e.target.value })} />
      <div className="linha" style={{ flexWrap: 'wrap' }}>
        {sugestoes.map((s) => (
          <button key={s} className="chip" onClick={() => setPedido({ ...pedido, texto: pedido.texto ? `${pedido.texto}\n${s}` : s })}>+ {s}</button>
        ))}
      </div>
      <label className="linha">
        <input type="checkbox" checked={pedido.abrir_ao_terminar} onChange={(e) => setPedido({ ...pedido, abrir_ao_terminar: e.target.checked })} />
        {t.abrirAoTerminar}
      </label>
    </div>
  )
}
