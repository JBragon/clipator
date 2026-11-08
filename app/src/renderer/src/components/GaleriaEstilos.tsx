import { useEffect, useMemo, useRef, useState } from 'react'
import type { Api, Estilo, Job } from '../api'
import { useT } from '../i18n'
import { abrirConfiguracoes } from './MelhorarIA'
import { useAgentesIA } from './PedidoIA'
import { RelatoJob } from './RelatoJob'

// Ajustes que o usuário mexe antes do render (vão para clip.ajustes_estilo)
export type AjustesEstilo = {
  legenda?: { cor?: string; destaque?: string; fonte?: string; posicao?: string; caixa_alta?: boolean }
  zoom?: { enfase?: boolean; intensidade?: number }
  volume_sons?: number
  reenquadramento?: string
  dividido?: { em_cima?: string; tamanho_rosto?: number }
  direcao?: { layout?: string; janela_canto?: string; proporcao?: number }
}

const FONTES = ['Montserrat ExtraBold', 'Anton', 'Bebas Neue', 'Bangers', 'Special Elite']
const POSICOES = ['topo', 'centro', 'centro-baixo', 'terco-inferior', 'baixo'] as const
const ENQUADRAMENTOS = ['seguir-rosto', 'dividido', 'centro', 'fundo-desfocado'] as const
// a última lista de cada canal: voltar ao passo 3 mostra a galeria na hora, enquanto o motor confere se mudou algo
const ultimaLista = new Map<string, Estilo[]>()
const amostrasDe = (l: Estilo[]): Record<string, string> => Object.fromEntries(l.filter((e) => e.amostra).map((e) => [e.id, e.amostra as string]))
const vazio = (a: AjustesEstilo): boolean => !Object.values(a).some((v) => v !== undefined && (typeof v !== 'object' || Object.keys(v).length))

// Galeria dos estilos (embutidos, do workspace, do canal e das skills) com a amostra de cada um renderizada
// de verdade pelo motor. A mesma galeria serve o passo 3 (escolher) e o botão "Estilos" (abrir o arquivo).
export function GaleriaEstilos(props: {
  api: Api
  canal?: string
  jobs: Record<string, Job>
  escolhido?: string
  aoEscolher?(id: string): void
  ajustes?: AjustesEstilo
  setAjustes?(a: AjustesEstilo): void
  abrirArquivo?(caminho: string): void
  // passo 3: prévia exata com o primeiro corte escolhido
  base?: string
  candidato?: string
  formato?: string
}): React.JSX.Element {
  const { api, canal, jobs, escolhido, aoEscolher, ajustes = {}, setAjustes, abrirArquivo, base, candidato, formato } = props
  const t = useT()
  const g = t.gal
  const [estilos, setEstilos] = useState<Estilo[]>(() => ultimaLista.get(canal ?? '') ?? [])
  const [filtro, setFiltro] = useState('')
  const [busca, setBusca] = useState('')
  const [raiz, setRaiz] = useState('')
  const [amostras, setAmostras] = useState<Record<string, string>>(() => amostrasDe(ultimaLista.get(canal ?? '') ?? []))
  const [jobAmostras, setJobAmostras] = useState<string | null>(null)
  const [aberto, setAberto] = useState<string | null>(null)
  const [n, setN] = useState(0)
  const { agentes } = useAgentesIA(api, true)
  const temIA = Object.values(agentes).length === 0 || Object.values(agentes).some((a) => a.instalado)

  useEffect(() => {
    api.get<Estilo[]>('/api/estilos', canal ? { canal } : {}).then((l) => {
      ultimaLista.set(canal ?? '', l)
      setEstilos(l)
      setAmostras(amostrasDe(l))
    }, () => setEstilos([]))
    api.get<{ workspace: string }>('/api/saude').then((s) => setRaiz(s.workspace), () => undefined)
  }, [api, canal, n])

  // pede as amostras que faltam (o motor gera uma por vez, num job, e guarda em cache)
  useEffect(() => {
    if (!estilos.length || jobAmostras) return
    const faltam = estilos.filter((e) => !e.erro && !amostras[e.id]).map((e) => e.id)
    if (!faltam.length) return
    api.post<{ prontas: Record<string, string>; job: string | null }>('/api/estilos/amostras', { canal: canal ?? null, estilos: faltam })
      .then((r) => {
        setAmostras((a) => ({ ...a, ...r.prontas }))
        setJobAmostras(r.job)
      }, () => undefined)
  }, [estilos]) // eslint-disable-line react-hooks/exhaustive-deps
  const job = jobAmostras ? jobs[jobAmostras] : undefined
  useEffect(() => {
    if (!job) return
    const r = job.resultado as { prontas?: Record<string, string> } | null | undefined
    if (job.status === 'ok' || job.status === 'erro' || job.status === 'cancelado') {
      if (r?.prontas) setAmostras((a) => ({ ...a, ...r.prontas }))
      setJobAmostras(null)
      setN((x) => x + 1)
    }
  }, [job?.status]) // eslint-disable-line react-hooks/exhaustive-deps

  const objetivos = [...new Set(estilos.flatMap((e) => e.objetivo ?? []))]
  const q = busca.trim().toLowerCase()
  const lista = useMemo(() => [...estilos]
    .filter((e) => (!filtro || e.objetivo?.includes(filtro)) && (!q || `${e.nome} ${e.descricao ?? ''} ${e.id}`.toLowerCase().includes(q)))
    .sort((a, b) => Number(!!b.padrao) - Number(!!a.padrao)), [estilos, filtro, q])

  // estilos embutidos não ficam no workspace: para editar, copia para estilos/ e abre a cópia
  const abrir = async (e: Estilo): Promise<void> => {
    if (!abrirArquivo) return
    const norm = e.caminho.replace(/\\/g, '/')
    const rel = raiz && norm.startsWith(raiz.replace(/\\/g, '/')) ? norm.slice(raiz.length + 1) : null
    if (rel) return abrirArquivo(rel)
    const conteudo = await fetch(api.url('/api/arquivo', { caminho: `estilos/${e.id}.md` }), { headers: { 'x-clipator-token': api.token } })
    if (conteudo.ok) return abrirArquivo(`estilos/${e.id}.md`)
    const texto = await fetch(api.url('/api/estilos/embutido', { id: e.id }), { headers: { 'x-clipator-token': api.token } }).then((r) => r.json())
    await api.put('/api/arquivo', { caminho: `estilos/${e.id}.md`, conteudo: texto.conteudo })
    abrirArquivo(`estilos/${e.id}.md`)
  }

  const definirPadrao = async (id: string): Promise<void> => {
    if (!canal) return
    await api.put(`/api/canais/${encodeURIComponent(canal)}/estilo-padrao`, { estilo: id })
    setN((x) => x + 1)
  }

  const urlAmostra = (nome: string): string => api.url('/api/estilos/amostra/arquivo', { nome, token: api.token })
  const est = aberto ? estilos.find((e) => e.id === aberto) : undefined

  return (
    <div className="galeria-estilos">
      <div className="linha filtros-galeria">
        <input type="search" placeholder={g.buscar} value={busca} onChange={(ev) => setBusca(ev.target.value)} />
        <button className={`chip-filtro ${filtro === '' ? 'ativo' : ''}`} onClick={() => setFiltro('')}>{t.todos}</button>
        {objetivos.map((o) => (
          <button key={o} className={`chip-filtro ${filtro === o ? 'ativo' : ''}`} onClick={() => setFiltro(o)}>{t.objetivos[o] ?? o}</button>
        ))}
        <span className="espaco" />
        {job && <span className="dica">{g.gerandoAmostras(Math.round(job.progresso * 100))}</span>}
      </div>
      <div className="grade-estilos">
        {lista.map((e) => (
          <CardEstilo key={e.id} e={e} amostra={amostras[e.id] ? urlAmostra(amostras[e.id]) : null}
            capa={amostras[e.id] ? urlAmostra(amostras[e.id].replace(/\.mp4$/, '.jpg')) : null}
            escolhido={escolhido === e.id} abrirDetalhes={() => setAberto(e.id)} semIA={!!e.requer_ia && !temIA}
            escolher={aoEscolher ? () => aoEscolher(e.id) : undefined} />
        ))}
      </div>
      {est && (
        <DetalheEstilo api={api} e={est} amostra={amostras[est.id] ? urlAmostra(amostras[est.id]) : null} jobs={jobs}
          canal={canal} base={base} candidato={candidato} formato={formato}
          ajustes={escolhido === est.id ? ajustes : {}} setAjustes={setAjustes && escolhido === est.id ? setAjustes : undefined}
          escolhido={escolhido === est.id} fechar={() => setAberto(null)} semIA={!!est.requer_ia && !temIA}
          escolher={aoEscolher ? () => aoEscolher(est.id) : undefined}
          definirPadrao={canal && !est.padrao ? () => void definirPadrao(est.id) : undefined}
          editar={abrirArquivo ? () => void abrir(est) : undefined} />
      )}
    </div>
  )
}

function Etiquetas({ e }: { e: Estilo }): React.JSX.Element {
  const t = useT()
  const g = t.gal
  const d = e.detalhes
  return (
    <div className="etiquetas">
      {e.requer_ia && <span className="chip usa-ia" title={t.usaIADica}>🤖 {t.usaIA}</span>}
      {e.formato && <span className="chip">{e.formato}</span>}
      <span className="chip">{e.motor === 'hyperframes' ? 'HyperFrames' : 'ASS'}</span>
      {e.nivel_ia && <span className="chip">IA: {g.niveisIA[e.nivel_ia] ?? e.nivel_ia}</span>}
      {d?.direcao && d.direcao !== 'nenhum' && <span className="chip destaque">🎬 {g.layouts[d.direcao] ?? d.direcao}</span>}
      {d && Object.keys(d.sons ?? {}).length > 0 && <span className="chip">🔊 {g.sons}</span>}
      {d?.cartela && <span className="chip">{g.cartela}</span>}
      {d?.zoom && <span className="chip">{g.zoom}</span>}
      {e.origem && e.origem !== 'embutido' && <span className="chip origem">{g.origens[e.origem] ?? e.origem}</span>}
    </div>
  )
}

function CardEstilo(props: { e: Estilo; amostra: string | null; capa: string | null; escolhido: boolean; abrirDetalhes(): void; escolher?(): void; semIA?: boolean }): React.JSX.Element {
  const { e, amostra, capa, escolhido, abrirDetalhes, escolher, semIA } = props
  const t = useT()
  const g = t.gal
  const v = useRef<HTMLVideoElement>(null)
  return (
    <div className={`cartao cartao-estilo${escolhido ? ' escolhido' : ''}${e.erro ? ' com-erro' : ''}${semIA ? ' sem-ia' : ''}`}
      onMouseEnter={() => void v.current?.play().catch(() => undefined)}
      onMouseLeave={() => { if (v.current) { v.current.pause(); v.current.currentTime = 0 } }}>
      <button className="amostra" onClick={abrirDetalhes} title={g.verDetalhes}
        style={{ aspectRatio: (e.formato ?? '9:16').replace(':', ' / ') }}>
        {amostra ? <video ref={v} src={amostra} poster={capa ?? undefined} muted loop playsInline preload="none" />
          : <span className="dica">{e.erro ? '⚠' : g.gerando}</span>}
        {e.padrao && <span className="selo-padrao">{g.padraoCanal}</span>}
        {escolhido && <span className="selo-escolhido">✓</span>}
      </button>
      <div className="corpo">
        <h4>{e.nome}</h4>
        {e.descricao && <span className="dica descricao">{e.descricao}</span>}
        {e.erro && <span className="erro-txt">{e.erro}</span>}
        <Etiquetas e={e} />
        {semIA && <span className="dica">{t.precisaIA} <button className="link" onClick={abrirConfiguracoes}>{t.abrirConfiguracoes}</button></span>}
        <div className="linha">
          {escolher && <button className={escolhido ? 'primario' : ''} disabled={!!e.erro || semIA} onClick={escolher}>{escolhido ? g.escolhido : g.usarEste}</button>}
          <button className="link" onClick={abrirDetalhes}>{g.detalhes}</button>
        </div>
      </div>
    </div>
  )
}

function DetalheEstilo(props: {
  api: Api
  e: Estilo
  amostra: string | null
  jobs: Record<string, Job>
  canal?: string
  base?: string
  candidato?: string
  formato?: string
  ajustes: AjustesEstilo
  setAjustes?(a: AjustesEstilo): void
  escolhido: boolean
  fechar(): void
  escolher?(): void
  definirPadrao?(): void
  editar?(): void
  semIA?: boolean
}): React.JSX.Element {
  const { api, e, amostra, jobs, canal, base, candidato, formato, ajustes, setAjustes, escolhido, fechar, escolher, definirPadrao, editar, semIA } = props
  const t = useT()
  const g = t.gal
  const d = e.detalhes
  const [mudo, setMudo] = useState(true)
  const [video, setVideo] = useState<string | null>(null) // prévia ajustada ou com o vídeo do projeto
  const [jobId, setJobId] = useState<string | null>(null)
  const [tipoJob, setTipoJob] = useState<'ajustes' | 'video' | null>(null)
  const [msg, setMsg] = useState('')
  const job = jobId ? jobs[jobId] : undefined

  useEffect(() => {
    const k = (ev: KeyboardEvent): void => { if (ev.key === 'Escape') fechar() }
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [fechar])

  useEffect(() => {
    if (!job || (job.status !== 'ok' && job.status !== 'erro')) return
    const r = job.resultado as { prontas?: Record<string, string>; caminho?: string; erros?: Record<string, string> } | null | undefined
    if (job.status === 'erro') setMsg(job.erro ?? t.status.erro)
    else if (r?.caminho) setVideo(api.midia(r.caminho, String(Date.now())))
    else if (r?.prontas?.[e.id]) setVideo(api.url('/api/estilos/amostra/arquivo', { nome: r.prontas[e.id], token: api.token }))
    else if (r?.erros?.[e.id]) setMsg(r.erros[e.id])
    setJobId(null)
    setTipoJob(null)
  }, [job?.status]) // eslint-disable-line react-hooks/exhaustive-deps

  const leg = { ...(d?.legenda ?? {}), ...(ajustes.legenda ?? {}) }
  const zoom = { enfase: d?.zoom ?? false, intensidade: d?.intensidade_zoom ?? 1.12, ...(ajustes.zoom ?? {}) }
  const volume = ajustes.volume_sons ?? d?.volume_sons ?? 0.5
  const temSons = Object.keys(d?.sons ?? {}).length > 0
  const reenq = ajustes.reenquadramento ?? d?.reenquadramento ?? 'seguir-rosto'
  const div = { em_cima: 'esquerda', tamanho_rosto: 0.35, ...(d?.dividido ?? {}), ...(ajustes.dividido ?? {}) }
  const composicao = (ajustes.direcao?.layout ?? d?.direcao) === 'janela' ? (ajustes.direcao?.janela_canto ?? 'inferior-direito') : 'em-cima'
  const mudar = (a: AjustesEstilo): void => setAjustes?.({ ...ajustes, ...a, legenda: { ...ajustes.legenda, ...a.legenda }, zoom: { ...ajustes.zoom, ...a.zoom }, dividido: { ...ajustes.dividido, ...a.dividido } })
  // na tela dividida a legenda vai para a emenda entre as metades, onde não cobre nenhum rosto
  const mudarEnquadramento = (v: string): void => mudar({ reenquadramento: v === d?.reenquadramento ? undefined : v,
    legenda: v === 'dividido' && !ajustes.legenda?.posicao && d?.reenquadramento !== 'dividido' ? { posicao: 'centro' } : {} })

  const atualizarAmostra = async (): Promise<void> => {
    setMsg('')
    const r = await api.post<{ prontas: Record<string, string>; job: string | null }>('/api/estilos/amostras',
      { canal: canal ?? null, estilos: [e.id], ajustes: vazio(ajustes) ? null : ajustes, formato: formato || null })
    if (r.prontas[e.id]) setVideo(api.url('/api/estilos/amostra/arquivo', { nome: r.prontas[e.id], token: api.token }))
    else if (r.job) { setJobId(r.job); setTipoJob('ajustes') }
  }
  const previaComVideo = async (): Promise<void> => {
    if (!base || !candidato) return
    setMsg('')
    const r = await api.post<{ job: string }>(`${base}/amostra-estilo`, { estilo: e.id, candidato, ajustes: vazio(ajustes) ? null : ajustes, formato: formato || null })
    setJobId(r.job)
    setTipoJob('video')
  }

  const src = video ?? amostra
  return (
    <div className="modal-fundo" onClick={fechar}>
      <div className="modal detalhe-estilo" onClick={(ev) => ev.stopPropagation()} role="dialog" aria-label={e.nome}>
        <button className="fechar-modal" aria-label={t.fechar} title={t.fechar} onClick={fechar}>✕</button>
        <div className="previa-grande">
          <div className="moldura" style={{ aspectRatio: (formato || e.formato || '9:16').replace(':', ' / ') }}>
            {src ? <video key={src} src={src} autoPlay loop playsInline muted={mudo} controls={false} />
              : <span className="dica">{g.gerando}</span>}
            {job && (
              <div className="gerando-previa">
                <span>{tipoJob === 'video' ? g.renderizandoVideo : g.renderizandoAjustes}</span>
                <span className="barra"><span style={{ width: `${Math.round(job.progresso * 100)}%` }} /></span>
              </div>
            )}
          </div>
          <div className="linha">
            <button onClick={() => setMudo(!mudo)}>{mudo ? `🔇 ${g.ligarSom}` : `🔊 ${g.desligarSom}`}</button>
            {video && <button className="link" onClick={() => setVideo(null)}>{g.voltarAmostra}</button>}
          </div>
        </div>
        <div className="info-estilo">
          <div className="linha">
            <h3 style={{ margin: 0 }}>{e.nome}</h3>
            {e.padrao && <span className="chip destaque">{g.padraoCanal}</span>}
          </div>
          {e.descricao && <p className="dica" style={{ margin: 0 }}>{e.descricao}</p>}
          <Etiquetas e={e} />
          {d && (
            <dl className="ficha-estilo">
              <dt>{g.legenda}</dt><dd>{d.legenda.fonte} · {g.modos[d.legenda.modo] ?? d.legenda.modo} · {g.animacoes[d.legenda.animacao] ?? d.legenda.animacao}</dd>
              <dt>{g.reenquadramento}</dt><dd>{g.reenq[d.reenquadramento] ?? d.reenquadramento}</dd>
              {temSons && <><dt>{g.sons}</dt><dd>{Object.entries(d.sons).map(([k, v]) => `${g.momentos[k] ?? k}: ${v.split('/').pop()?.replace(/\.\w+$/, '')}`).join(' · ')}</dd></>}
              {d.jump_cuts && <><dt>{g.cortes}</dt><dd>{g.jumpCuts}</dd></>}
              {(d.musica || d.logo) && <><dt>{g.extras}</dt><dd>{[d.musica && g.musica, d.logo && g.logo].filter(Boolean).join(' · ')}</dd></>}
            </dl>
          )}
          {setAjustes ? (
            <fieldset className="ajustes-estilo">
              <legend>{g.ajustes}</legend>
              <div className="linha">
                <label className="campo">{g.corTexto}<input type="color" value={String(leg.cor ?? '#ffffff').slice(0, 7).toLowerCase()} onChange={(ev) => mudar({ legenda: { cor: ev.target.value.toUpperCase() } })} /></label>
                <label className="campo">{g.corDestaque}<input type="color" value={String(leg.destaque ?? '#ffe600').slice(0, 7).toLowerCase()} onChange={(ev) => mudar({ legenda: { destaque: ev.target.value.toUpperCase() } })} /></label>
                <label className="campo">{g.fonte}
                  <select value={leg.fonte ?? ''} onChange={(ev) => mudar({ legenda: { fonte: ev.target.value } })}>
                    {[...new Set([leg.fonte ?? '', ...FONTES])].filter(Boolean).map((f) => <option key={f}>{f}</option>)}
                  </select>
                </label>
              </div>
              <div className="linha">
                <label className="campo">{g.posicaoLegenda}
                  <select value={leg.posicao ?? 'centro-baixo'} onChange={(ev) => mudar({ legenda: { posicao: ev.target.value } })}>
                    {POSICOES.map((p) => <option key={p} value={p}>{g.posicoes[p]}</option>)}
                  </select>
                </label>
                <label className="linha"><input type="checkbox" checked={!!leg.caixa_alta} onChange={(ev) => mudar({ legenda: { caixa_alta: ev.target.checked } })} /> {g.caixaAlta}</label>
              </div>
              <div className="linha">
                <label className="campo">{g.reenquadramento}
                  <select value={reenq} onChange={(ev) => mudarEnquadramento(ev.target.value)}>
                    {[...new Set([reenq, ...ENQUADRAMENTOS])].map((r) => <option key={r} value={r}>{g.reenq[r] ?? r}</option>)}
                  </select>
                </label>
              </div>
              {(d?.direcao === 'em-cima' || d?.direcao === 'janela') && (
                <div className="linha">
                  <label className="campo">{t.dir.composicao}
                    <select value={composicao} onChange={(ev) => mudar({ direcao: ev.target.value === 'em-cima' ? { layout: 'em-cima', proporcao: 0.5 } : { layout: 'janela', janela_canto: ev.target.value } })}>
                      {Object.entries(t.dir.composicoes).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                    </select>
                  </label>
                </div>
              )}
              {reenq === 'dividido' && (
                <>
                  <p className="dica" style={{ margin: 0 }}>{g.reenqDica}</p>
                  <div className="linha">
                    <label className="campo">{g.emCima}
                      <select value={div.em_cima} onChange={(ev) => mudar({ dividido: { em_cima: ev.target.value } })}>
                        {['esquerda', 'direita'].map((l) => <option key={l} value={l}>{g.lados[l]}</option>)}
                      </select>
                    </label>
                    <label className="campo">{g.zoomRosto}: {Math.round(Number(div.tamanho_rosto) * 100)}%
                      <input type="range" min={0.2} max={0.6} step={0.05} value={Number(div.tamanho_rosto)}
                        onChange={(ev) => mudar({ dividido: { tamanho_rosto: Number(ev.target.value) } })} />
                    </label>
                  </div>
                </>
              )}
              <div className="linha">
                <label className="linha"><input type="checkbox" checked={!!zoom.enfase} onChange={(ev) => mudar({ zoom: { enfase: ev.target.checked } })} /> {g.zoomEnfase}</label>
                <label className="campo">{g.intensidade}: {Number(zoom.intensidade).toFixed(2)}
                  <input type="range" min={1} max={1.4} step={0.02} value={Number(zoom.intensidade)} disabled={!zoom.enfase}
                    onChange={(ev) => mudar({ zoom: { intensidade: Number(ev.target.value) } })} />
                </label>
              </div>
              {temSons && (
                <label className="campo">{g.volumeSons}: {Math.round(volume * 100)}%
                  <input type="range" min={0} max={1.5} step={0.05} value={volume} onChange={(ev) => mudar({ volume_sons: Number(ev.target.value) })} />
                </label>
              )}
              <div className="linha">
                <button disabled={!!job} onClick={() => void atualizarAmostra()}>↻ {g.atualizarAmostra}</button>
                {!vazio(ajustes) && <button className="link" onClick={() => setAjustes({})}>{g.desfazerAjustes}</button>}
              </div>
            </fieldset>
          ) : escolher && <p className="dica" style={{ margin: 0 }}>{g.escolhaParaAjustar}</p>}
          <div className="linha" style={{ flexWrap: 'wrap' }}>
            {escolher && <button className="primario" disabled={!!e.erro || semIA} onClick={() => { escolher(); if (escolhido) fechar() }}>{escolhido ? g.usarEFechar : g.usarEste}</button>}
            {base && candidato && <button disabled={!!job || semIA} onClick={() => void previaComVideo()} title={g.previaVideoDica}>🎬 {g.previaVideo}</button>}
            {definirPadrao && <button onClick={definirPadrao}>★ {g.definirPadrao}</button>}
            {editar && <button className="link" onClick={editar}>{g.editarArquivo}</button>}
          </div>
          {job && <RelatoJob api={api} job={job} />}
          {semIA && <p className="dica" style={{ margin: 0 }}>{t.precisaIA} <button className="link" onClick={abrirConfiguracoes}>{t.abrirConfiguracoes}</button></p>}
          {msg && <p className="erro-txt" style={{ margin: 0 }}>{msg}</p>}
        </div>
      </div>
    </div>
  )
}
