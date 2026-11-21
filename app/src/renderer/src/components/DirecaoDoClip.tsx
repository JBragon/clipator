import { useCallback, useEffect, useState } from 'react'
import type { Api, Job } from '../api'
import { useT } from '../i18n'
import { abrirConfiguracoes } from './MelhorarIA'
import { useAgentesIA } from './PedidoIA'
import { RelatoJob } from './RelatoJob'

type DirecaoVideo = {
  historia: { assunto: string; metafora: string; logline: string; comeco: string; meio: string; fim: string }
  elenco: { id: string; papel: string; tipo: string; nome: string; visual: string }[]
  cenarios: { id: string; lugar: string; descricao: string }[]
  rodadas?: { problemas: string[] }[]
}
type CenaRoteiro = { inicio: number; fim: number; ancora: string; etiqueta: string; descricao: string; dado: string; balao: string }
type Camada = { tipo: string; peca?: string; rotulo?: string; valor?: string; grafico?: string }
type LimiteArte = { tipo: 'inteiro' | 'numero' | 'booleano' | 'texto'; minimo?: number; maximo?: number; opcoes?: string[] }
type CenaArte = { id: string; inicio: number; fim: number; texto: string; nota: string; dado: string; itens: string[]; ancora: string; acao?: string; objetos?: string[]; lugares?: string[]; pendencias?: Pendencia[]; escolha?: { falado: string; nivel: string; id: string } }
type Pendencia = { falado: string; motivo: string; mensagem: string; opcoes: { id: string; nome: string; nivel: string; descricao: string }[] }
type Arte = { id: string; nome: string; alternativa: string; limites: Record<string, LimiteArte>; parametros: Record<string, number | string | boolean>; cenas: CenaArte[]; acoes: string[] }
type Composicao = { layout: string; proporcao: number; janela_canto: string | null; janela_escala: number; janela_encaixe: string }
type Direcao = {
  arte: Arte | null
  composicao: Composicao
  ativa: boolean; modo: 'cenas' | 'desenho' | 'arte'; layout: string; ficha: string; estilo: string; cores: Record<string, string>
  analise: { tema: string; ideias: { ancora: string; tipo: string; resumo: string; dado: string }[] } | null
  roteiro: CenaRoteiro[] | null; camadas: Camada[][] | null; modelo: string | null; criado: string | null
  direcao_video: DirecaoVideo | null
  cenas: { inicio: number; fim: number; cena: string; texto: string }[]; pecas: string[]; nomes_pecas: Record<string, string>
}

const CORES = ['fundo', 'texto', 'primaria', 'destaque', 'bom', 'ruim'] as const
const CANTOS = ['inferior-direito', 'inferior-esquerdo', 'superior-direito', 'superior-esquerdo'] as const
const opcaoDe = (c: Composicao): string => (c.layout === 'janela' ? (c.janela_canto ?? 'inferior-direito') : c.layout)

// Passo 5, depois do render: a direção de arte que a IA fez para o clip (análise, roteiro cena a cena, peças e
// cores). O usuário ajusta o roteiro ou as cores e pede "Refazer com esta direção", que vira uma versão nova.
export function DirecaoDoClip(props: { api: Api; base: string; clip: string; jobs: Record<string, Job>; aoMudar(): void }): React.JSX.Element | null {
  const { api, base, clip, jobs, aoMudar } = props
  const t = useT()
  const d = t.dir
  const url = `${base}/clips/${encodeURIComponent(clip)}`
  const { agentes } = useAgentesIA(api, true)
  const temIA = Object.values(agentes).some((a) => a.instalado)
  const [info, setInfo] = useState<Direcao | null>(null)
  const [roteiro, setRoteiro] = useState<CenaRoteiro[]>([])
  const [cores, setCores] = useState<Record<string, string>>({})
  const [jobId, setJobId] = useState<string | null>(null)
  const [ultimoJob, setUltimoJob] = useState<string | null>(null)
  const [msg, setMsg] = useState('')
  const [cenasArte, setCenasArte] = useState<CenaArte[]>([])
  const [paramsArte, setParamsArte] = useState<Arte['parametros']>({})
  const [comp, setComp] = useState<Composicao | null>(null)
  const job = jobId ? jobs[jobId] : undefined

  const carregar = useCallback(() => {
    api.get<Direcao>(`${url}/direcao-arte`).then((r) => {
      setInfo(r)
      setRoteiro(r.roteiro ?? [])
      setCores(r.cores)
      setCenasArte(r.arte?.cenas ?? [])
      setParamsArte(r.arte?.parametros ?? {})
      setComp(r.composicao)
    }, () => setInfo(null))
  }, [api, url])
  useEffect(carregar, [carregar])
  useEffect(() => {
    if (!job || (job.status !== 'ok' && job.status !== 'erro' && job.status !== 'cancelado')) return
    if (job.status === 'erro') setMsg(job.erro ?? t.status.erro)
    setJobId(null)
    carregar()
    aoMudar()
    window.dispatchEvent(new CustomEvent('clipator:versoes-mudaram', { detail: clip }))
  }, [job?.status]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!info || !info.ativa) return null
  const desenho = info.modo === 'desenho'
  const temRoteiro = desenho || (info.roteiro?.length ?? 0) > 0 // clips antigos de cenas não têm pré-produção
  const roteiroMudou = JSON.stringify(roteiro) !== JSON.stringify(info.roteiro ?? [])
  const coresMudaram = CORES.some((k) => cores[k] !== info.cores[k])
  const mudar = (k: number, campo: keyof CenaRoteiro, v: string): void =>
    setRoteiro(roteiro.map((c, i) => (i === k ? { ...c, [campo]: campo === 'inicio' || campo === 'fim' ? Number(v) : v } : c)))

  const refazer = async (tudo: boolean): Promise<void> => {
    setMsg('')
    try {
      const r = await api.post<{ job: string }>(`${url}/direcao-arte/refazer`, {
        roteiro: temRoteiro && !tudo ? roteiro : null,
        cores: coresMudaram ? Object.fromEntries(CORES.map((k) => [k, cores[k]])) : null,
        tudo,
      })
      setJobId(r.job)
      setUltimoJob(r.job)
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e))
    }
  }

  const arte = info.arte
  const arteMudou = !!arte && (JSON.stringify(cenasArte) !== JSON.stringify(arte.cenas) || JSON.stringify(paramsArte) !== JSON.stringify(arte.parametros))
  const mudarCena = (k: number, campo: 'texto' | 'nota' | 'dado', v: string): void =>
    setCenasArte(cenasArte.map((c, i) => (i === k ? { ...c, [campo]: v } : c)))
  const moverCena = (k: number, para: number): void => {
    const l = [...cenasArte]
    l.splice(para, 0, l.splice(k, 1)[0])
    setCenasArte(l)
  }
  const compMudou = !!comp && JSON.stringify(comp) !== JSON.stringify(info.composicao)
  const aplicarComposicao = async (): Promise<void> => {
    if (!comp) return
    setMsg('')
    try {
      const r = await api.post<{ job: string }>(`${url}/direcao-arte/ajustar`, {
        composicao: comp.layout === 'janela'
          ? { layout: 'janela', janela_canto: comp.janela_canto ?? 'inferior-direito', janela_escala: comp.janela_escala, janela_encaixe: comp.janela_encaixe }
          : { layout: 'em-cima', proporcao: comp.proporcao },
      })
      setJobId(r.job)
      setUltimoJob(r.job)
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e))
    }
  }
  const aplicarArte = async (): Promise<void> => {
    setMsg('')
    try {
      const r = await api.post<{ job: string }>(`${url}/direcao-arte/ajustar`, {
        cenas: cenasArte, parametros: paramsArte,
        cores: coresMudaram ? { ...info.cores, ...Object.fromEntries(CORES.map((k) => [k, cores[k]])) } : null,
      })
      setJobId(r.job)
      setUltimoJob(r.job)
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e))
    }
  }

  return (
    <details className="direcao-do-clip">
      <summary>🎨 {d.titulo} <span className="chip">{arte ? arte.nome : desenho ? d.desenho : d.cenas}</span>
        <span className="dica"> · {info.estilo} · {d.ficha} {info.ficha}{info.modelo ? ` · ${info.modelo}` : ''}</span></summary>
      {!temIA && !arte && <p className="dica sem-ia">{t.precisaIA} <button className="link" onClick={abrirConfiguracoes}>{t.abrirConfiguracoes}</button></p>}

      {info.analise && (
        <section>
          <h5>1 · {d.analise}</h5>
          <p style={{ margin: 0 }}><b>{d.tema}:</b> {info.analise.tema || '—'}</p>
          <ul className="ideias">
            {info.analise.ideias.map((i, k) => (
              <li key={k}><span className="chip">{i.tipo}</span> {i.resumo}{i.dado ? <b> · {i.dado}</b> : null} <span className="dica">“{i.ancora}”</span></li>
            ))}
          </ul>
        </section>
      )}

      {info.direcao_video && <PainelDirecaoVideo dv={info.direcao_video} />}

      {temRoteiro && (
        <section>
          <h5>{info.direcao_video ? 3 : 2} · {desenho ? d.roteiro : d.roteiroCenas}</h5>
          {roteiro.length === 0 && <p className="dica">{d.semRoteiro}</p>}
          <ol className="roteiro-desenho">
            {roteiro.map((c, k) => (
              <li key={k}>
                <div className="linha">
                  <input className="tempo" type="number" step="0.1" value={c.inicio} onChange={(e) => mudar(k, 'inicio', e.target.value)} aria-label={d.inicio} />
                  <span>–</span>
                  <input className="tempo" type="number" step="0.1" value={c.fim} onChange={(e) => mudar(k, 'fim', e.target.value)} aria-label={d.fim} />
                  <span>s</span>
                  <input className="etiqueta" value={c.etiqueta} placeholder={d.etiqueta} onChange={(e) => mudar(k, 'etiqueta', e.target.value)} />
                  <button className="link" title={d.tirarCena} onClick={() => setRoteiro(roteiro.filter((_, i) => i !== k))}>✕</button>
                </div>
                <textarea rows={2} value={c.descricao} placeholder={d.descricao} onChange={(e) => mudar(k, 'descricao', e.target.value)} />
                <div className="linha">
                  <input value={c.dado} placeholder={d.dado} onChange={(e) => mudar(k, 'dado', e.target.value)} />
                  <input value={c.balao} placeholder={d.balao} onChange={(e) => mudar(k, 'balao', e.target.value)} style={{ flex: 2 }} />
                </div>
                <div className="dica">“{c.ancora}”{info.camadas?.[k]?.length ? ` · ${d.pecasDaCena}: ${resumoCamadas(info.camadas[k], info.nomes_pecas)}` : ''}</div>
              </li>
            ))}
          </ol>
        </section>
      )}
      {comp && (comp.layout === 'em-cima' || comp.layout === 'janela') && (
        <section>
          <h5>{d.composicao}</h5>
          <div className="linha" style={{ flexWrap: 'wrap', gap: 6 }} role="radiogroup" aria-label={d.composicao}>
            {(['em-cima', ...CANTOS] as string[]).map((o) => (
              <button key={o} role="radio" aria-checked={opcaoDe(comp) === o} className={opcaoDe(comp) === o ? 'primario' : ''}
                onClick={() => setComp(o === 'em-cima' ? { ...comp, layout: 'em-cima', proporcao: 0.5 } : { ...comp, layout: 'janela', janela_canto: o })}>
                {d.composicoes[o]}
              </button>
            ))}
          </div>
          {comp.layout === 'janela' && (
            <div className="parametros-arte">
              <label><span>{d.janelaTamanho}</span>
                <input type="range" min={0.2} max={0.5} step={0.01} value={comp.janela_escala} onChange={(e) => setComp({ ...comp, janela_escala: Number(e.target.value) })} /></label>
              <label><span>{d.janelaEncaixe}</span>
                <select value={comp.janela_encaixe} onChange={(e) => setComp({ ...comp, janela_encaixe: e.target.value })}>
                  <option value="enquadrar">{d.janelaEnquadrar}</option><option value="barras">{d.janelaBarras}</option>
                </select></label>
            </div>
          )}
          <div className="linha">
            <button className="primario" disabled={!!job || !compMudou} onClick={() => void aplicarComposicao()}>🖼️ {d.arteAplicar}</button>
            {compMudou && <button className="link" onClick={() => setComp(info.composicao)}>{d.desfazer}</button>}
          </div>
        </section>
      )}
      {arte && (
        <section>
          <h5>{d.arteCenas}</h5>
          <ol className="roteiro-desenho">
            {cenasArte.map((c, k) => (
              <li key={c.id}>
                <div className="linha">
                  <span className="dica">{d.arteCena(k + 1)}</span>
                  {c.lugares === undefined || arte.id !== 'geo-em-cena' ? <>
                    <input value={c.nota} placeholder={d.arteNota} onChange={(e) => mudarCena(k, 'nota', e.target.value)} />
                    <input value={c.dado} placeholder={d.dado} onChange={(e) => mudarCena(k, 'dado', e.target.value)} />
                  </> : <span>{c.lugares.join(' · ') || d.arteSemLugar}</span>}
                  {arte.acoes.length > 0 && <select value={c.acao ?? ''} aria-label={d.arteAcao} onChange={(e) => setCenasArte(cenasArte.map((x, i) => (i === k ? { ...x, acao: e.target.value } : x)))}>
                    {arte.acoes.map((a) => <option key={a} value={a}>{a.replaceAll('_', ' ')}</option>)}</select>}
                  <button className="link" disabled={k === 0} title={d.arteSobe} onClick={() => moverCena(k, k - 1)}>↑</button>
                  <button className="link" disabled={k === cenasArte.length - 1} title={d.arteDesce} onClick={() => moverCena(k, k + 1)}>↓</button>
                </div>
                {arte.id !== 'geo-em-cena' && <textarea rows={2} value={c.texto} placeholder={d.arteTexto} onChange={(e) => mudarCena(k, 'texto', e.target.value)} />}
                {c.pendencias?.map((p) => (
                  <div className="dica" key={p.falado}>⚠️ {p.mensagem}
                    {p.opcoes.length > 0 && <select aria-label={d.arteLugar} value={c.escolha?.falado === p.falado ? `${c.escolha.nivel}|${c.escolha.id}` : ''}
                      onChange={(e) => { const [nivel, id] = e.target.value.split('|'); setCenasArte(cenasArte.map((x, i) => (i === k ? { ...x, escolha: id ? { falado: p.falado, nivel, id } : undefined } : x))) }}>
                      <option value="">{d.arteLugar}</option>
                      {p.opcoes.map((o) => <option key={o.id} value={`${o.nivel}|${o.id}`}>{o.nome} ({o.descricao})</option>)}</select>}
                  </div>
                ))}
                <div className="dica">“{c.ancora}”{c.objetos?.length ? ` · ${c.objetos.join(', ')}` : ''}</div>
              </li>
            ))}
          </ol>
          <h5>{d.arteParametros}</h5>
          <div className="parametros-arte">
            {Object.entries(arte.limites).filter(([k]) => k !== 'semente').map(([k, l]) => (
              <label key={k}>
                <span>{k === 'leve' ? d.arteLeve : k.replaceAll('_', ' ')}</span>
                {l.tipo === 'booleano'
                  ? <input type="checkbox" checked={!!paramsArte[k]} onChange={(e) => setParamsArte({ ...paramsArte, [k]: e.target.checked })} />
                  : l.tipo === 'texto'
                    ? <select value={String(paramsArte[k] ?? '')} onChange={(e) => setParamsArte({ ...paramsArte, [k]: e.target.value })}>{l.opcoes?.map((o) => <option key={o}>{o}</option>)}</select>
                    : <input type="number" min={l.minimo} max={l.maximo} step={l.tipo === 'inteiro' ? 1 : 0.01} value={Number(paramsArte[k] ?? 0)}
                        onChange={(e) => setParamsArte({ ...paramsArte, [k]: Number(e.target.value) })} />}
              </label>
            ))}
          </div>
          <p className="dica" style={{ margin: 0 }}>{d.arteAlternativa}: {arte.alternativa}</p>
          <div className="linha">
            <button className="primario" disabled={!!job || !(arteMudou || coresMudaram)} onClick={() => void aplicarArte()} title={d.arteAplicarDica}>🎨 {d.arteAplicar}</button>
            {job && <span className="dica">{job.mensagem} {Math.round(job.progresso * 100)}%</span>}
          </div>
        </section>
      )}
      {!desenho && !arte && (
        <section>
          <h5>{temRoteiro ? 3 : 2} · {d.cenasDoClip}</h5>
          <ul className="ideias">{info.cenas.map((c, k) => <li key={k}>{c.inicio.toFixed(1)}–{c.fim.toFixed(1)} s · <b>{c.cena}</b> {c.texto}</li>)}</ul>
        </section>
      )}

      <section>
        <h5>{!desenho && temRoteiro ? 4 : 3} · {d.coresTitulo}</h5>
        <div className="linha" style={{ flexWrap: 'wrap', gap: 10 }}>
          {CORES.map((k) => (
            <label key={k} className="cor-da">
              <input type="color" value={cores[k] ?? '#000000'} onChange={(e) => setCores({ ...cores, [k]: e.target.value.toUpperCase() })} />
              {d.cores[k]}
            </label>
          ))}
        </div>
      </section>

      <div className="linha">
        <button className="primario" disabled={!temIA || !!job || (temRoteiro && roteiro.length === 0)} onClick={() => void refazer(false)}
          title={temRoteiro ? d.refazerDica : d.refazerCenasDica}>
          🎨 {d.refazer}{roteiroMudou || coresMudaram ? ' •' : ''}
        </button>
        {temRoteiro && <button disabled={!temIA || !!job} onClick={() => void refazer(true)} title={d.refazerTudoDica}>{d.refazerTudo}</button>}
        {(roteiroMudou || coresMudaram) && <button className="link" onClick={() => { setRoteiro(info.roteiro ?? []); setCores(info.cores) }}>{d.desfazer}</button>}
        {job && <span className="dica">{job.mensagem} {Math.round(job.progresso * 100)}%</span>}
      </div>
      {ultimoJob && jobs[ultimoJob] && <RelatoJob api={api} job={jobs[ultimoJob]} aberto={!!job} />}
      {msg && <p className="erro-txt" style={{ margin: 0 }}>{msg}</p>}
    </details>
  )
}

function resumoCamadas(cs: Camada[], nomes: Record<string, string>): string {
  return cs.map((c) => (c.peca ? (nomes[c.peca] ?? c.peca).split(' (')[0].split(',')[0] : c.tipo === 'dado' ? `${c.grafico} ${c.valor ?? ''}`.trim() : c.rotulo ?? c.tipo)).join(', ')
}

// A direção de vídeo que a IA escreveu antes das cenas: a história, o elenco fixo, os cenários e a conferência.
function PainelDirecaoVideo(props: { dv: DirecaoVideo }): React.JSX.Element {
  const { dv } = props
  const d = useT().dir
  const corrigidos = (dv.rodadas?.[0]?.problemas ?? []).filter((p) => !p.startsWith('aviso:')).length
  const h = dv.historia
  return (
    <section className="direcao-video">
      <h5>2 · {d.direcaoVideo}</h5>
      <p style={{ margin: 0 }}><b>{d.historia}:</b> {h.logline || '—'}</p>
      {h.metafora && <p style={{ margin: 0 }}><b>{d.metafora}:</b> {h.metafora}</p>}
      {(h.comeco || h.meio || h.fim) && <p className="dica" style={{ margin: 0 }}>{d.arco}: {[h.comeco, h.meio, h.fim].filter(Boolean).join(' → ')}</p>}
      <p style={{ margin: 0 }}><b>{d.elenco}:</b>{' '}
        {dv.elenco.length ? dv.elenco.map((e) => <span key={e.id} className="chip" title={e.visual}>{e.nome || e.papel} · {e.tipo}{e.visual ? ` · ${e.visual}` : ''}</span>) : <span className="dica">{d.semElenco}</span>}
      </p>
      {dv.cenarios.length > 0 && (
        <p style={{ margin: 0 }}><b>{d.cenarios}:</b> {dv.cenarios.map((c) => <span key={c.id} className="chip" title={c.descricao}>{c.lugar}</span>)}</p>
      )}
      <p className="dica" style={{ margin: 0 }}>{d.conferencia}: {corrigidos ? d.conferidaCorrigida.replace('{n}', String(corrigidos)) : d.conferidaOk}</p>
    </section>
  )
}
