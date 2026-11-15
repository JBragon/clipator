import { useEffect, useState } from 'react'
import { hms, type Api, type Candidato, type Job } from '../api'
import { useT } from '../i18n'
import { GaleriaEstilos, type AjustesEstilo } from './GaleriaEstilos'
import { PainelPedidoIA, type PedidoIA } from './PedidoIA'

// Escolhas do passo 3 que sobrevivem à troca de passo (ficam no ProjetoView)
export type EscolhaEstilo = { estilo: string; ajustes: AjustesEstilo; formato: string; cartela: boolean; pedidoIA: PedidoIA | null }
// tira os campos vazios (um grupo que o usuário abriu e não mexeu não vai para o clip)
const semVazios = (a: AjustesEstilo): AjustesEstilo => Object.fromEntries(Object.entries(a)
  .map(([k, v]) => [k, v && typeof v === 'object' ? Object.fromEntries(Object.entries(v).filter(([, x]) => x !== undefined && x !== '')) : v])
  .filter(([, v]) => v !== undefined && (typeof v !== 'object' || Object.keys(v as object).length))) as AjustesEstilo
export const escolhaInicial = (): EscolhaEstilo => ({ estilo: '', ajustes: {}, formato: '', cartela: true, pedidoIA: null })
const temAjustesEm = (a: AjustesEstilo): boolean => Object.values(a).some((v) => v !== undefined && (typeof v !== 'object' || Object.keys(v).length))

// cria os clips dos cortes escolhidos com o estilo do passo 3 (e manda renderizar); usado nos passos 3 e 4
export async function criarClips(api: Api, base: string, escolhidos: Candidato[], escolha: EscolhaEstilo, renderizar: boolean): Promise<number> {
  const pedido = escolha.pedidoIA?.texto.trim() ? { ...escolha.pedidoIA, texto: escolha.pedidoIA.texto.trim() } : null
  const clips = await api.post<{ id: string }[]>(`${base}/selecionar`, {
    ids: escolhidos.map((c) => c.id),
    formato: escolha.formato || null,
    estilo: escolha.estilo || null,
    cartela: escolha.cartela,
    pedido_ia: pedido,
    ajustes: temAjustesEm(escolha.ajustes) ? semVazios(escolha.ajustes) : null
  })
  if (renderizar) await api.post(`${base}/renderizar`, { clips: clips.map((c) => c.id) })
  return clips.length
}

// Passo 3: o estilo de animação e edição dos cortes escolhidos no passo 2, com a amostra de cada estilo.
// Daqui o usuário segue para a checagem de fatos (passo 4) ou já cria os clips.
export function PassoEstilo(props: {
  api: Api
  base: string
  canal: string
  cands: Candidato[]
  selecionados: Set<string>
  setSelecionados(s: Set<string>): void
  jobs: Record<string, Job>
  escolha: EscolhaEstilo
  setEscolha(e: EscolhaEstilo): void
  voltarCortes(): void
  checarFatos(): void
  aposCriar(n: number): void
}): React.JSX.Element {
  const { api, base, canal, cands, selecionados, setSelecionados, jobs, escolha, setEscolha, voltarCortes, checarFatos, aposCriar } = props
  const t = useT()
  const g = t.gal
  const [msg, setMsg] = useState('')
  const [enviando, setEnviando] = useState(false)
  const escolhidos = cands.filter((c) => selecionados.has(c.id)).sort((a, b) => b.nota - a.nota)
  const mudar = (m: Partial<EscolhaEstilo>): void => setEscolha({ ...escolha, ...m })
  // o estilo animado que combina com o tema do primeiro corte escolhido (conta offline do motor)
  const [sugestao, setSugestao] = useState<{ estilo: string; nota: number; motivo: string; palavras: string[] }[]>([])
  const primeiro = escolhidos[0]?.id
  useEffect(() => {
    if (!primeiro) { setSugestao([]); return }
    let vivo = true
    api.get<{ estilo: string; nota: number; motivo: string; palavras: string[] }[]>(`${base}/candidatos/${primeiro}/estilo-sugerido`)
      .then((r) => { if (vivo) setSugestao(r) }).catch(() => { if (vivo) setSugestao([]) })
    return () => { vivo = false }
  }, [api, base, primeiro])
  const melhor = sugestao[0]
  const temAjustes = temAjustesEm(escolha.ajustes)

  const criar = async (): Promise<void> => {
    setEnviando(true)
    try {
      const n = await criarClips(api, base, escolhidos, escolha, false)
      setMsg('')
      setSelecionados(new Set())
      setEscolha({ ...escolha, pedidoIA: null })
      aposCriar(n)
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e))
    }
    setEnviando(false)
  }

  return (
    <div className="passo-conteudo passo-estilo">
      <div className="barra-grade barra-estilo">
        <button className="link" onClick={voltarCortes}>← {g.voltarCortes}</button>
        <strong>{t.selecionados(escolhidos.length)}</strong>
        <div className="chips-cortes">
          {escolhidos.slice(0, 6).map((c) => (
            <span key={c.id} className="chip" title={c.titulos?.[0] ?? c.texto}>
              {hms(c.inicio)} · {Math.round(c.fim - c.inicio)}s
              <button className="link" aria-label={t.remover} onClick={() => { const s = new Set(selecionados); s.delete(c.id); setSelecionados(s) }}>×</button>
            </span>
          ))}
          {escolhidos.length > 6 && <span className="dica">+{escolhidos.length - 6}</span>}
        </div>
        <span className="espaco" />
        <select value={escolha.formato} onChange={(e) => mudar({ formato: e.target.value })} aria-label={t.formato}>
          <option value="">{t.formato}: {g.doEstilo}</option>
          {['9:16', '1:1', '4:5', '16:9'].map((f) => <option key={f}>{f}</option>)}
        </select>
        <label className="linha">
          <input type="checkbox" checked={escolha.cartela} onChange={(e) => mudar({ cartela: e.target.checked })} /> {t.cartela}
        </label>
        <button disabled={!escolhidos.length || enviando} onClick={() => void criar()}>{t.criarClips}</button>
        <button className="primario" disabled={!escolhidos.length || enviando} onClick={checarFatos}>
          {t.fatos.irPara} →
        </button>
      </div>
      {!escolhidos.length && (
        <div className="sem-longos">
          <span className="dica">{g.semCortes}</span>
          <button onClick={voltarCortes}>{g.voltarCortes}</button>
        </div>
      )}
      {msg && <p className="erro-txt" style={{ margin: '0 12px' }}>{msg}</p>}
      <div className="estilo-colunas">
        <GaleriaEstilos api={api} canal={canal} jobs={jobs} escolhido={escolha.estilo || undefined}
          aoEscolher={(id) => setEscolha({ ...escolha, estilo: id, ajustes: id === escolha.estilo ? escolha.ajustes : {} })}
          ajustes={escolha.ajustes} setAjustes={(a) => mudar({ ajustes: a })}
          base={base} candidato={escolhidos[0]?.id} formato={escolha.formato || undefined} />
        <aside className="lado-estilo">
          <div className="resumo-estilo">
            <span className="dica">{g.estiloEscolhido}</span>
            <strong>{escolha.estilo || g.padraoDoCanal}</strong>
            {temAjustes && <span className="chip">{g.comAjustes}</span>}
            {!escolha.estilo && <span className="dica">{g.padraoDica}</span>}
          </div>
          {melhor && (
            <div className="resumo-estilo sugestao-estilo">
              <span className="dica">{g.sugerido}</span>
              <strong>{melhor.estilo.replace(/^arte-/, '').replace(/-/g, ' ')}</strong>
              <span className="dica">{melhor.motivo}{melhor.palavras.length ? ` (${g.sugeridoPorque(melhor.palavras.join(', '))})` : ''}</span>
              {escolha.estilo !== melhor.estilo && (
                <button onClick={() => setEscolha({ ...escolha, estilo: melhor.estilo, ajustes: {} })}>{g.usarSugerido}</button>
              )}
            </div>
          )}
          <div className="barra-pedido-ia">
            <PainelPedidoIA api={api} pedido={escolha.pedidoIA} setPedido={(p) => mudar({ pedidoIA: p })} />
          </div>
        </aside>
      </div>
    </div>
  )
}
