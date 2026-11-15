import { useCallback, useEffect, useState } from 'react'
import type { Api, Job } from '../api'
import { useT } from '../i18n'
import { useAgentesIA } from './PedidoIA'
import { RelatoJob } from './RelatoJob'

type Versao = { n: number; criado: string; origem: string; modelo: string; feedback: string; resumo: string[]; descartados: { item: string; motivo: string }[]; itens: number; cortes: number; atual: boolean; previa: string | null }
type Lado = { n: number; resumo: string[]; feedback: string; origem: string; itens: { tipo: string; inicio: number; fim: number; rotulo: string; texto: string }[]; previa: string | null }

// pede para abrir as Configurações (o App escuta)
export const abrirConfiguracoes = (): void => { window.dispatchEvent(new CustomEvent('clipator:abrir-configuracoes')) }

// Passo 5: "Melhorar com IA" e o histórico de versões da edição de um clip. Cada rodada da IA, cada edição à
// mão e cada mudança pelo MCP vira uma versão (v1, v2…) que dá para ver, comparar e pôr de volta em uso.
export function MelhorarIA(props: { api: Api; base: string; clip: string; jobs: Record<string, Job>; aoMudar(): void }): React.JSX.Element {
  const { api, base, clip, jobs, aoMudar } = props
  const t = useT()
  const m = t.mel
  const url = `${base}/clips/${encodeURIComponent(clip)}`
  const { agentes } = useAgentesIA(api, true)
  const temIA = Object.values(agentes).some((a) => a.instalado)
  const [versoes, setVersoes] = useState<Versao[]>([])
  const [chips, setChips] = useState<string[]>([])
  const [feedback, setFeedback] = useState('')
  const [jobId, setJobId] = useState<string | null>(null)
  const [ultimoJob, setUltimoJob] = useState<string | null>(null) // o relato da última rodada fica à vista
  const [msg, setMsg] = useState('')
  const [comparar, setComparar] = useState<{ a: Lado; b: Lado; diferencas: string[] } | null>(null)
  const [vendo, setVendo] = useState<number | null>(null)
  const job = jobId ? jobs[jobId] : undefined

  const carregar = useCallback(() => {
    api.get<{ versoes: Versao[]; chips: string[] }>(`${url}/edicao/versoes`).then((r) => { setVersoes(r.versoes); setChips(r.chips) }, () => undefined)
  }, [api, url])
  useEffect(carregar, [carregar])
  useEffect(() => { // outra parte da tela (a direção de arte do clip) criou uma versão
    const ouvir = (e: Event): void => { if ((e as CustomEvent<string>).detail === clip) carregar() }
    window.addEventListener('clipator:versoes-mudaram', ouvir)
    return () => window.removeEventListener('clipator:versoes-mudaram', ouvir)
  }, [carregar, clip])
  useEffect(() => {
    if (!job || (job.status !== 'ok' && job.status !== 'erro' && job.status !== 'cancelado')) return
    if (job.status === 'erro') setMsg(job.erro ?? t.status.erro)
    setJobId(null)
    carregar()
    aoMudar()
  }, [job?.status]) // eslint-disable-line react-hooks/exhaustive-deps

  const atual = versoes.find((v) => v.atual)
  const melhorar = async (): Promise<void> => {
    setMsg('')
    try {
      const r = await api.post<{ job: string }>(`${url}/melhorar`, { feedback })
      setJobId(r.job)
      setUltimoJob(r.job)
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e))
    }
  }
  const usar = async (n: number): Promise<void> => {
    await api.post(`${url}/edicao/versoes/${n}/usar`)
    carregar()
    aoMudar()
  }
  const previa = async (n: number): Promise<void> => {
    const r = await api.post<{ job: string }>(`${url}/edicao/versoes/${n}/previa`)
    setJobId(r.job)
  }
  const abrirComparar = async (n: number): Promise<void> => {
    if (!atual) return
    setComparar(await api.get(`${url}/edicao/versoes/comparar`, { a: String(n), b: String(atual.n) }))
  }
  const alternarChip = (c: string): void => {
    const partes = feedback.split(',').map((x) => x.trim()).filter(Boolean)
    setFeedback((partes.includes(c) ? partes.filter((x) => x !== c) : [...partes, c]).join(', '))
  }

  return (
    <details className="melhorar-ia" open={versoes.length > 1 || undefined}>
      <summary>✨ {m.titulo} <span className="chip usa-ia">🤖 {t.usaIA}</span> {atual && <span className="dica">· {m.emUso(atual.n)}</span>}</summary>
      {!temIA && (
        <p className="dica sem-ia">{t.precisaIA} <button className="link" onClick={abrirConfiguracoes}>{t.abrirConfiguracoes}</button></p>
      )}
      <div className="linha" style={{ flexWrap: 'wrap', gap: 4 }}>
        {chips.map((c) => (
          <button key={c} className={`chip-filtro ${feedback.includes(c) ? 'ativo' : ''}`} onClick={() => alternarChip(c)}>{c}</button>
        ))}
      </div>
      <textarea rows={2} placeholder={m.placeholder} value={feedback} onChange={(e) => setFeedback(e.target.value)} />
      <div className="linha">
        <button className="primario" disabled={!temIA || !!job} onClick={() => void melhorar()}>✨ {m.botao}</button>
        {job && <span className="dica">{job.mensagem} {Math.round(job.progresso * 100)}%</span>}
        <span className="espaco" style={{ flex: 1 }} />
        {atual && versoes.some((v) => v.n < atual.n) && (
          <button className="link" onClick={() => void usar(Math.max(...versoes.filter((v) => v.n < atual.n).map((v) => v.n)))}>↶ {m.voltar}</button>
        )}
      </div>
      {ultimoJob && jobs[ultimoJob] && <RelatoJob api={api} job={jobs[ultimoJob]} aberto={!!job} />}
      {msg && <p className="erro-txt" style={{ margin: 0 }}>{msg}</p>}
      {versoes.length > 0 && (
        <ol className="lista-versoes">
          {versoes.map((v) => (
            <li key={v.n} className={v.atual ? 'atual' : ''}>
              <div className="linha">
                <strong>v{v.n}</strong>
                <span className="chip">{m.origens[v.origem as keyof typeof m.origens] ?? v.origem}{v.modelo ? ` · ${v.modelo}` : ''}</span>
                <span className="dica">{new Date(v.criado).toLocaleString()}</span>
                {v.atual && <span className="chip destaque">{m.atual}</span>}
                <span className="espaco" style={{ flex: 1 }} />
                {v.previa ? <button className="link" onClick={() => setVendo(vendo === v.n ? null : v.n)}>▶ {m.verPrevia}</button>
                  : <button className="link" disabled={!!job} onClick={() => void previa(v.n)}>{m.gerarPrevia}</button>}
                {!v.atual && atual && <button className="link" onClick={() => void abrirComparar(v.n)}>⇄ {m.comparar}</button>}
                {!v.atual && <button onClick={() => void usar(v.n)}>{m.usar}</button>}
              </div>
              {v.feedback && <div className="dica">“{v.feedback}”</div>}
              <ul className="o-que-mudou">{v.resumo.slice(0, 5).map((r, k) => <li key={k}>{r}</li>)}</ul>
              {v.descartados.length > 0 && (
                <details className="descartados"><summary className="dica">{m.descartados(v.descartados.length)}</summary>
                  <ul>{v.descartados.map((d, k) => <li key={k}><b>{d.item}</b>: {d.motivo}</li>)}</ul>
                </details>
              )}
              {vendo === v.n && v.previa && <video className="previa-versao" src={api.midia(v.previa, v.criado)} controls autoPlay />}
            </li>
          ))}
        </ol>
      )}
      {comparar && (
        <div className="modal-fundo" onClick={() => setComparar(null)}>
          <div className="modal comparar-versoes" onClick={(e) => e.stopPropagation()}>
            <div className="linha"><h3>{m.compararTitulo(comparar.a.n, comparar.b.n)}</h3><span className="espaco" style={{ flex: 1 }} />
              <button className="link" onClick={() => setComparar(null)}>✕</button></div>
            <ul className="o-que-mudou">{comparar.diferencas.map((d, k) => <li key={k}>{d}</li>)}</ul>
            <div className="lados">
              {[comparar.a, comparar.b].map((l) => (
                <div key={l.n} className="lado-versao">
                  <strong>v{l.n}{l === comparar.b ? ` · ${m.atual}` : ''}</strong>
                  {l.previa ? <video src={api.midia(l.previa, String(l.n))} controls muted autoPlay loop /> : <div className="dica sem-previa">{m.semPrevia}</div>}
                  <ul className="itens-versao">{l.itens.map((i, k) => <li key={k}>{i.inicio.toFixed(1)}–{i.fim.toFixed(1)} s · {i.rotulo}{i.texto ? `: ${i.texto}` : ''}</li>)}</ul>
                </div>
              ))}
            </div>
            <div className="linha">
              <button className="primario" onClick={() => { void usar(comparar.a.n); setComparar(null) }}>{m.usarV(comparar.a.n)}</button>
              <button onClick={() => setComparar(null)}>{m.ficarAtual}</button>
            </div>
          </div>
        </div>
      )}
    </details>
  )
}
