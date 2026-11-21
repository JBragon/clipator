import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { hms, proj, type Api, type Candidato, type Clip, type Estilo, type Job, type Transcricao } from '../api'
import { useT } from '../i18n'
import { ponte } from '../ponte'
import { Thumbs } from './Thumbs'
import { ProgressoJob } from './BarraProgresso'
import { GradeCandidatos, type Capitulo } from './GradeCandidatos'
import { NotaDetalhe } from './NotaDetalhe'
import { Glossario } from './Glossario'
import { PassoPublicacao } from './PassoPublicacao'
import { MelhorarIA } from './MelhorarIA'
import { RelatoJob } from './RelatoJob'
import { DirecaoDoClip } from './DirecaoDoClip'
import { PassoEstilo, escolhaInicial, type EscolhaEstilo } from './PassoEstilo'
import { PASSO_CHECAGEM, PASSO_CLIPS, PASSO_ESTILO, PASSO_PUBLICACAO, chavePasso, lerPasso, passoLiberado, passoPadrao, passoPermitido, type EstadoPassos, type Passo } from '../passos'
import { confirmar } from './Confirmar'
import { SonsPrevia } from './SonsPrevia'
import { EditarComIA } from './EditarComIA'
import { AvisoCookies, ehErroDeCookies } from './AvisoCookies'
import { abrirConversa, PainelConversa, type PedidoConversa } from './ConversaIA'
import { EditorVideo } from './EditorVideo'
import { EditarDuracao, type AlvoDuracao } from './EditarDuracao'
import { Acabamento } from './Acabamento'
import { EditarLegenda } from './EditarLegenda'
import { Checagem, type ResumoChecagem } from './Checagem'

type Detalhe = {
  meta: { titulo: string; etapas: Record<string, { status: string; erro?: string }>; origem?: { tipo: string; valor: string } }
  metadados: { titulo?: string; url?: string; midia?: { duracao: number }; capitulos?: Capitulo[] }
  video: string | null
  clips: Clip[]
}


type Sinais = { passo: number; energia_db: number[]; media_db: number; desvio_db: number }

type Props = {
  api: Api
  canal: string
  projeto: string
  versao: number
  selecionados: Set<string>
  setSelecionados(s: Set<string>): void
  jobs: Record<string, Job>
  aposCriar(): void
}

export function ProjetoView(props: Props): React.JSX.Element {
  const { api, canal, projeto, versao, selecionados, setSelecionados, jobs, aposCriar } = props
  const t = useT()
  const base = proj(canal, projeto)
  const alvoDoClip = (c: Clip): AlvoDuracao => ({
    id: c.id, titulo: c.titulo, inicio: c.inicio, fim: c.fim, temVideo: !!(c.saida || c.preview || c.versao),
    rotulo: `${c.formato === '9:16' ? t.dur.short : t.dur.longo} · ${c.formato}`, url: `${base}/clips/${encodeURIComponent(c.id)}/trecho`
  })
  const alvoDoCandidato = (c: Candidato): AlvoDuracao => ({
    id: c.id, titulo: (c.titulos ?? [])[0] ?? '', inicio: c.inicio, fim: c.fim, temVideo: false,
    rotulo: `${t.dur.sugerido} · ${c.modo === 'longo' ? t.dur.longo : t.dur.short}`, url: `${base}/candidatos/${encodeURIComponent(c.id)}/trecho`
  })
  const [det, setDet] = useState<Detalhe | null>(null)
  const [trans, setTrans] = useState<Transcricao | null>(null)
  const [sinais, setSinais] = useState<Sinais | null>(null)
  const [cands, setCands] = useState<Candidato[]>([])
  const [estilos, setEstilos] = useState<Estilo[]>([])
  const [tempo, setTempo] = useState(0)
  const [conversaAtiva, setConversaAtiva] = useState<string | null>(null)
  const [versaoConversa, setVersaoConversa] = useState(0)
  const [avisoConversa, setAvisoConversa] = useState('')
  const [editando, setEditando] = useState<string | null>(null) // clip aberto no editor de vídeo
  const [duracaoDe, setDuracaoDe] = useState<string | null>(null) // clip aberto na tela "Editar duração"
  const [avisoDuracao, setAvisoDuracao] = useState('')
  const [duracaoCand, setDuracaoCand] = useState<string | null>(null) // corte sugerido (passo 2) na tela "Editar duração"
  const [alvoConversa, setAlvoConversa] = useState<{ clip: string; n: number } | null>(null)
  const [erro, setErro] = useState('')
  const [raiz, setRaiz] = useState('')
  const [temHF, setTemHF] = useState(true)
  const [focado, setFocado] = useState<string | null>(null)
  // passo da tela: 1 vídeo e status, 2 cortes sugeridos, 3 estilo, 4 checagem de fatos, 5 clips gerados, 6 publicação
  // (lembrado por projeto)
  const [passo, setPassoEstado] = useState<Passo | null>(() => {
    try {
      return lerPasso(localStorage, canal, projeto)
    } catch {
      return null
    }
  })
  const [escolha, setEscolha] = useState<EscolhaEstilo>(escolhaInicial)
  const [avisoClips, setAvisoClips] = useState(0)
  const [filtroClips, setFiltroClips] = useState<'todos' | 'shorts' | 'outros'>('todos')
  const [resumoFatos, setResumoFatos] = useState<{ resumo: ResumoChecagem; candidatos: string[] } | null>(null)
  const video = useRef<HTMLVideoElement>(null)

  useEffect(() => {
    api.get<{ workspace: string; hyperframes?: boolean }>('/api/saude').then((s) => {
      setRaiz(s.workspace)
      setTemHF(s.hyperframes !== false)
    }, () => undefined)
  }, [api])

  const carregarFatos = (): void => {
    api.get<{ resumo: ResumoChecagem; candidatos: string[] }>(`${base}/checagem`).then(setResumoFatos, () => setResumoFatos(null))
  }
  const carregar = useCallback(() => {
    api.get<Detalhe>(base).then(setDet, (e) => setErro((e instanceof Error ? e.message : String(e))))
    api.get<Transcricao>(`${base}/transcricao`).then(setTrans, () => setTrans(null))
    api.get<Sinais>(`${base}/sinais`).then((s) => setSinais(s.energia_db ? s : null), () => setSinais(null))
    api.get<Candidato[]>(`${base}/candidatos`).then(setCands, () => setCands([]))
    carregarFatos()
  }, [api, base]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(carregar, [carregar, versao])
  useEffect(() => {
    api.get<Estilo[]>('/api/estilos', { canal }).then(setEstilos, () => setEstilos([]))
  }, [api, canal])

  const duracao = det?.metadados?.midia?.duracao ?? trans?.duracao ?? 0
  const jobsDoProjeto = Object.values(jobs)
    .filter((j) => j.params.canal === canal && j.params.projeto === projeto)
    .sort((a, b) => b.criado - a.criado)
  const jobAtivo = jobsDoProjeto.find((j) => j.status === 'rodando' || j.status === 'na_fila')
  // sem nada rodando, o painel ainda mostra a última falha (até a próxima execução)
  const jobPainel = jobAtivo ?? (jobsDoProjeto[0]?.status === 'erro' ? jobsDoProjeto[0] : undefined)

  const seek = (s: number): void => {
    if (video.current) video.current.currentTime = s
  }

  const setPasso = (p: Passo): void => {
    setPassoEstado(p)
    setAvisoClips(0)
    try {
      localStorage.setItem(chavePasso(canal, projeto), String(p))
    } catch {
      /* sem armazenamento: vale só nesta sessão */
    }
  }

  // "Ver no vídeo principal": leva ao passo 1 e toca o trecho lá. O pedido fica guardado uma vez só
  // e é consumido quando o player do passo 1 monta; nada mais muda o passo sozinho.
  const tocarNoPrincipal = useRef<Candidato | null>(null)
  const verNoPrincipal = (c: Candidato): void => {
    setFocado(c.id)
    tocarNoPrincipal.current = c
    setPasso(1)
  }
  useEffect(() => {
    const c = tocarNoPrincipal.current
    const v = video.current
    if (passo !== 1 || !c || !v) return
    tocarNoPrincipal.current = null
    const tocar = (): void => {
      v.currentTime = c.inicio
      void v.play().catch(() => undefined)
    }
    if (v.readyState >= 1) tocar()
    else v.addEventListener('loadedmetadata', tocar, { once: true })
  }, [passo, det?.video])

  // abre a conversa com a IA no painel do passo 5 (ou num terminal externo, fora do Electron)
  const conversar = async (p: PedidoConversa): Promise<string> => {
    const s = await abrirConversa(api, base, canal, projeto, p, det?.clips ?? [], { cols: 100, rows: 30 })
    if (!s) return t.conversaExterna
    setConversaAtiva(s)
    setVersaoConversa((n) => n + 1)
    return t.conversaAberta
  }

  // render do lote com "Pedido para a IA": o motor deixa o pedido pronto e o app abre a conversa;
  // o passo só muda se o usuário clicar no aviso
  const jobsVistos = useRef<Set<string> | null>(null)
  useEffect(() => {
    const prontos = Object.values(jobs).filter((j) => j.tipo === 'renderizar' && j.status === 'ok' && j.params.canal === canal && j.params.projeto === projeto)
    if (jobsVistos.current === null) {
      jobsVistos.current = new Set(prontos.map((j) => j.id)) // o que já tinha terminado antes de abrir a tela
      return
    }
    for (const j of prontos) {
      if (jobsVistos.current.has(j.id)) continue
      jobsVistos.current.add(j.id)
      const conversas = (j.resultado?.conversas_ia ?? []) as { agente: 'claude' | 'codex'; lote: string; clips: string[] }[]
      for (const c of conversas) {
        conversar({ alvo: { tipo: 'lote', clips: c.clips, lote: c.lote }, agente: c.agente, modo: 'abrir', externo: !ponte.ia })
          .then(() => setAvisoConversa(t.conversaPronta(c.clips.length)), (e) => setAvisoConversa(e instanceof Error ? e.message : String(e)))
      }
    }
  }, [jobs]) // eslint-disable-line react-hooks/exhaustive-deps

  // "Rodar de novo" refaz tudo: a tela já some com a análise antiga e mostra o progresso da nova
  const refazer = async (): Promise<void> => {
    // a transcrição fica (o motor também a mantém); o resto da análise some até a nova chegar
    setCands([])
    setSinais(null)
    setFocado(null)
    setSelecionados(new Set())
    setDet((d) => d && {
      ...d,
      meta: {
        ...d.meta,
        etapas: Object.fromEntries(Object.entries(d.meta.etapas).map(([k, v]) =>
          [k, k === 'ingestao' || k === 'render' || (k === 'transcricao' && trans) ? { ...v, erro: undefined } : { status: 'pendente' }]))
      }
    })
    await api.post(`${base}/analisar`, {}, { refazer: 'true' })
  }

  const salvarSegmento = async (idx: number, texto: string): Promise<void> => {
    await api.put(`${base}/transcricao`, { correcoes: { [idx]: texto } })
  }

  if (erro) return <div className="vazio erro-txt">{erro}</div>
  if (!det) return <div className="vazio">…</div>

  const etapas = det.meta.etapas
  const analiseFeita = etapas.candidatos?.status === 'ok'
  const analisando = jobAtivo?.tipo === 'analisar'
  const longos = cands.filter((c) => c.modo === 'longo').length
  const shorts = cands.length - longos
  // cada passo só abre com o anterior concluído (a checagem de fatos é opcional); um passo guardado que ainda
  // não abriu mostra o último liberado antes dele, e volta sozinho quando a condição se cumprir
  const estadoPassos: EstadoPassos = {
    analiseFeita: analiseFeita && !analisando,
    temCortes: cands.length > 0,
    temSelecao: selecionados.size > 0,
    temClips: det.clips.length > 0,
    temVideoGerado: det.clips.some((c) => !!c.saida)
  }
  const liberado = (p: Passo): boolean => passoLiberado(p, estadoPassos)
  // passo padrão: 1 sem análise, 2 com cortes e sem clips, 5 com clips
  const passoAtual: Passo = passoPermitido(passo ?? passoPadrao(analiseFeita && !analisando, det.clips.length > 0, cands.length > 0), estadoPassos)
  const estadoPasso = (p: Passo): 'feito' | 'andamento' | 'vazio' | 'erro' => {
    if (p === 1) {
      if (analisando) return 'andamento'
      if (Object.values(etapas).some((v) => v.status === 'erro')) return 'erro'
      return analiseFeita ? 'feito' : 'vazio'
    }
    if (p === 2) return cands.length ? 'feito' : analisando ? 'andamento' : 'vazio'
    if (p === PASSO_ESTILO) return det.clips.length ? 'feito' : 'vazio'
    if (p === PASSO_CHECAGEM) {
      if (jobsDoProjeto.some((j) => j.tipo === 'checagem' && (j.status === 'rodando' || j.status === 'na_fila'))) return 'andamento'
      return resumoFatos && resumoFatos.candidatos.length && !resumoFatos.resumo.pendente ? 'feito' : 'vazio'
    }
    if (p === PASSO_PUBLICACAO) return jobsDoProjeto.some((j) => j.tipo === 'postagem' && (j.status === 'rodando' || j.status === 'na_fila')) ? 'andamento' : 'vazio'
    const renderizando = jobsDoProjeto.some((j) => j.tipo === 'renderizar' && (j.status === 'rodando' || j.status === 'na_fila'))
    return renderizando ? 'andamento' : det.clips.length ? 'feito' : 'vazio'
  }
  const passos: { n: Passo; nome: string; detalhe: string }[] = [
    { n: 1, nome: t.passoVideo, detalhe: analisando ? `${Math.round((jobAtivo?.progresso ?? 0) * 100)}%` : analiseFeita ? t.analiseFeita : t.analisePendente },
    { n: 2, nome: t.passoCortes, detalhe: t.contagemCortes(shorts, longos) },
    { n: PASSO_ESTILO, nome: t.passoEstilo, detalhe: escolha.estilo || (selecionados.size ? t.selecionados(selecionados.size) : t.gal.escolher) },
    { n: PASSO_CHECAGEM, nome: t.passoChecagem, detalhe: !resumoFatos?.candidatos.length ? t.fatos.naoChecado
      : resumoFatos.resumo.pendente ? t.fatos.paraConferir(resumoFatos.resumo.pendente) : t.fatos.conferidos(resumoFatos.resumo.total) },
    { n: PASSO_CLIPS, nome: t.passoClips, detalhe: t.contagemClips(det.clips.length) },
    { n: PASSO_PUBLICACAO, nome: t.passoPublicacao, detalhe: t.contagemProntos(det.clips.filter((c) => c.saida).length) }
  ]
  const clipsFiltrados = det.clips.filter((c) =>
    filtroClips === 'todos' ? true : filtroClips === 'shorts' ? c.formato === '9:16' : c.formato !== '9:16')
  const statusEtapas: [string, { status: string; erro?: string }][] = [
    ...Object.entries(etapas).filter(([k]) => k !== 'render'),
    ['longos', { status: longos ? 'ok' : 'pendente' }]
  ]

  // o vídeo principal aparece grande no passo 1
  const player = (classe: string): React.JSX.Element => det.video ? (
    <video ref={video} className={classe} src={api.midia(det.video)} controls preload="metadata" onTimeUpdate={(e) => setTempo(e.currentTarget.currentTime)} />
  ) : (
    <div className="vazio" style={{ minWidth: 320 }}>{jobAtivo ? `${jobAtivo.mensagem} ${Math.round(jobAtivo.progresso * 100)}%` : t.aguardandoAnalise}</div>
  )

  return (
    <div className="projeto">
      <nav className="passos-projeto" aria-label={t.passosProjeto}>
        {passos.map((p) => {
          // travado: continua focável e com a dica no mouse (um botão disabled some do teclado e não explica o porquê)
          const travado = !liberado(p.n)
          return (
          <button key={p.n} className={`passo ${travado ? 'travado' : estadoPasso(p.n)} ${passoAtual === p.n ? 'ativo' : ''}`}
            onClick={() => !travado && setPasso(p.n)} aria-disabled={travado || undefined} title={travado ? t.passoTravado[p.n] : undefined}
            aria-current={passoAtual === p.n ? 'step' : undefined}>
            <span className="num">{travado ? '🔒' : estadoPasso(p.n) === 'feito' ? '✓' : estadoPasso(p.n) === 'erro' ? '!' : p.n}</span>
            <span className="textos">
              <span className="nome">{p.nome}</span>
              <span className="detalhe">{travado ? t.passoTravadoCurto : p.detalhe}</span>
            </span>
          </button>
          )
        })}
        {avisoConversa && (
          <span className="aviso-conversa">
            <button className="link" onClick={() => {
              setPasso(PASSO_CLIPS)
              setAvisoConversa('')
            }}>✨ {avisoConversa}</button>
            <button className="link" aria-label={t.fechar} onClick={() => setAvisoConversa('')}>×</button>
          </span>
        )}
        {jobPainel && passoAtual !== 1 && (
          <button className={`progresso-mini ${jobPainel.status}`} onClick={() => setPasso(1)} title={jobPainel.mensagem}>
            <span>{t.tiposJob[jobPainel.tipo] ?? jobPainel.tipo}</span>
            <span className="barra"><span style={{ width: `${Math.round(jobPainel.progresso * 100)}%` }} /></span>
            <span className="pct">{jobPainel.status === 'erro' ? t.status.erro : `${Math.round(jobPainel.progresso * 100)}%`}</span>
          </button>
        )}
      </nav>

      {passoAtual === 1 && (
        <div className="passo-conteudo passo-video">
          {jobPainel && <ProgressoJob api={api} job={jobPainel} />}
          {!jobAtivo && etapas.ingestao?.status === 'erro' && ehErroDeCookies(etapas.ingestao.erro) && (
            <AvisoCookies api={api} base={base} erro={etapas.ingestao.erro ?? ''} jobs={jobs} aoTentar={carregar} />
          )}
          <div className="player-area">
            {player('player-grande')}
            <div className="player-lado">
              <h3 style={{ margin: 0 }}>{det.meta.titulo}</h3>
              {det.metadados.url && <span className="dica">{det.metadados.url}</span>}
              <ol className="status-etapas">
                {statusEtapas.map(([k, v]) => (
                  <li key={k} className={`etapa ${v.status}`} title={v.erro ?? ''}>
                    <span className="bolinha">{v.status === 'ok' ? '✓' : v.status === 'erro' ? '!' : v.status === 'rodando' ? '…' : ''}</span>
                    <span>{k === 'longos' ? t.cortes169 : t.etapas[k] ?? k}</span>
                    <span className="dica">{k === 'longos' && longos ? String(longos) : t.status[v.status] ?? v.status}</span>
                  </li>
                ))}
              </ol>
              {Object.values(etapas).find((v) => v.erro) && (
                <p className="erro-txt" style={{ margin: 0 }}>{Object.values(etapas).find((v) => v.erro)?.erro}</p>
              )}
              <div className="linha">
                <button disabled={!!jobAtivo} onClick={() => void refazer()}>{t.rodarDeNovo}</button>
                <button disabled={!!jobAtivo || !cands.length} onClick={() => void api.post(`${base}/ranquear`, { modo_ia: 'completo' })}>
                  {t.ranquearIA}
                </button>
                {analiseFeita && !longos && (
                  <button disabled={!!jobAtivo} onClick={() => void api.post(`${base}/candidatos`, {}, { modo: 'longo' })}>
                    {t.gerarLongos}
                  </button>
                )}
              </div>
              <Glossario api={api} canal={canal} base={base} aoCorrigir={carregar} />
              {cands.length > 0 && (
                <button className="primario" onClick={() => setPasso(2)}>{t.irParaCortes(cands.length)}</button>
              )}
            </div>
          </div>
          <Timeline duracao={duracao} sinais={sinais} cands={cands} clips={det.clips} selecionados={selecionados} focado={focado} tempo={tempo} seek={seek} />
          <AreaTranscricao trans={trans} tempo={tempo} seek={seek} salvar={salvarSegmento} />
        </div>
      )}

      {passoAtual === 2 && duracaoCand && cands.some((c) => c.id === duracaoCand) && (
        <div className="passo-conteudo editor-coluna">
          <EditarDuracao key={duracaoCand} api={api} alvo={alvoDoCandidato(cands.find((c) => c.id === duracaoCand)!)} video={det.video}
            duracao={duracao} trans={trans} sinais={sinais}
            outros={cands.filter((c) => c.id !== duracaoCand).map((c) => ({ id: c.id, titulo: (c.titulos ?? [])[0], inicio: c.inicio, fim: c.fim }))}
            voltar={() => setDuracaoCand(null)}
            aoSalvar={(m) => {
              setFocado(duracaoCand)
              setDuracaoCand(null)
              setAvisoDuracao(m)
              carregar()
            }} />
        </div>
      )}

      {passoAtual === 2 && !(duracaoCand && cands.some((c) => c.id === duracaoCand)) && (
        <>
        {avisoDuracao && (
          <div className="aviso-clips">
            <span>✂ {avisoDuracao}</span>
            <button className="link" onClick={() => setAvisoDuracao('')}>{t.fechar}</button>
          </div>
        )}
        <GradeCandidatos
          api={api}
          base={base}
          video={det.video}
          cands={cands}
          capitulos={det.metadados.capitulos ?? []}
          selecionados={selecionados}
          setSelecionados={setSelecionados}
          focado={focado}
          aoFocar={(c) => setFocado(c.id)}
          verNoPrincipal={verNoPrincipal}
          escolherEstilo={() => setPasso(PASSO_ESTILO)}
          editarDuracao={(c) => setDuracaoCand(c.id)}
          jobAtivo={jobAtivo}
        />
        </>
      )}

      {passoAtual === PASSO_ESTILO && (
        <>
          {avisoClips > 0 && (
            <div className="aviso-clips">
              <span>{t.clipsCriados(avisoClips)}</span>
              <button className="primario" onClick={() => setPasso(PASSO_CLIPS)}>{t.verClips}</button>
              <button className="link" onClick={() => setAvisoClips(0)}>{t.fechar}</button>
            </div>
          )}
          <PassoEstilo api={api} base={base} canal={canal} cands={cands} selecionados={selecionados} setSelecionados={setSelecionados}
            jobs={jobs} escolha={escolha} setEscolha={setEscolha} voltarCortes={() => setPasso(2)}
            checarFatos={() => setPasso(PASSO_CHECAGEM)}
            aposCriar={(n) => {
              aposCriar()
              setPasso(PASSO_CLIPS)
              setAvisoClips(n)
            }} />
        </>
      )}

      {passoAtual === PASSO_CHECAGEM && (
        <Checagem api={api} base={base} canal={canal} projeto={projeto} cands={cands} jobs={jobs}
          idsCortes={selecionados.size ? [...selecionados] : [...new Set(det.clips.map((c) => c.candidato).filter((x): x is string => !!x))]}
          deClipsExistentes={!selecionados.size}
          escolha={escolha} setEscolha={setEscolha} setSelecionados={setSelecionados}
          voltarEstilo={() => setPasso(PASSO_ESTILO)} irParaClips={() => setPasso(PASSO_CLIPS)} aoMudar={carregarFatos}
          aposCriar={(n) => {
            aposCriar()
            setPasso(PASSO_CLIPS)
            setAvisoClips(n)
          }} />
      )}

      {passoAtual === PASSO_CLIPS && (
        <div className="passo-conteudo passo-clips">
          {duracaoDe && det.clips.some((c) => c.id === duracaoDe) ? (
            <div className="clips-coluna editor-coluna">
              <EditarDuracao key={duracaoDe} api={api} alvo={alvoDoClip(det.clips.find((c) => c.id === duracaoDe)!)} video={det.video}
                duracao={duracao} trans={trans} sinais={sinais} outros={det.clips.filter((c) => c.id !== duracaoDe)}
                voltar={() => setDuracaoDe(null)}
                aoSalvar={(m) => {
                  setDuracaoDe(null)
                  setAvisoDuracao(m)
                  carregar()
                }} />
            </div>
          ) : editando && det.clips.some((c) => c.id === editando && c.status === 'renderizado') ? (
            <div className="clips-coluna editor-coluna">
              <EditorVideo key={editando} api={api} base={base} clip={det.clips.find((c) => c.id === editando)!} video={det.video}
                trans={trans} sinais={sinais} jobs={jobs} voltar={() => setEditando(null)} aoMudar={carregar}
                conversar={() => setAlvoConversa({ clip: editando, n: Date.now() })} />
            </div>
          ) : (
          <div className="clips-coluna">
            <div className="barra-grade">
              <strong>{t.clips}</strong>
              <span className="dica">{det.clips.length}</span>
              <span className="espaco" />
              {(['todos', 'shorts', 'outros'] as const).map((f) => (
                <button key={f} className={`chip-filtro ${filtroClips === f ? 'ativo' : ''}`} onClick={() => setFiltroClips(f)}>
                  {t.filtroClips[f]}
                </button>
              ))}
            </div>
            {!det.clips.length && (
              <div className="sem-longos">
                <span className="dica">{t.semClips}</span>
                <button onClick={() => setPasso(2)}>{t.irParaCortes(cands.length)}</button>
              </div>
            )}
            {avisoDuracao && (
              <div className="aviso-clips">
                <span>✂ {avisoDuracao}</span>
                <button className="link" onClick={() => setAvisoDuracao('')}>{t.fechar}</button>
              </div>
            )}
            <div className="clips-lista">
              {clipsFiltrados.map((c) => (
                <EditorClip key={c.id} api={api} base={base} clip={c} estilos={estilos} aoMudar={carregar} jobs={jobs} raiz={raiz} temHF={temHF}
                  cand={cands.find((x) => x.id === c.candidato)} conversar={conversar} abrirEditor={() => setEditando(c.id)}
                  editarDuracao={() => setDuracaoDe(c.id)} />
              ))}
            </div>
          </div>
          )}
          <PainelConversa api={api} base={base} canal={canal} projeto={projeto} clips={det.clips}
            ativa={conversaAtiva} setAtiva={setConversaAtiva} versao={versaoConversa} alvoPreferido={alvoConversa}
            editorAberto={!!editando} />
        </div>
      )}

      {passoAtual === PASSO_CLIPS && avisoClips > 0 && (
        <div className="aviso-clips">
          <span>{t.clipsCriados(avisoClips)}</span>
          <button className="link" onClick={() => setAvisoClips(0)}>{t.fechar}</button>
        </div>
      )}

      {passoAtual === PASSO_PUBLICACAO && (
        <div className="passo-conteudo">
          <PassoPublicacao api={api} base={base} clips={det.clips} jobs={jobs} raiz={raiz} irParaClips={() => setPasso(PASSO_CLIPS)} />
        </div>
      )}

    </div>
  )
}

function Timeline(props: {
  duracao: number
  sinais: Sinais | null
  cands: Candidato[]
  clips: Clip[]
  selecionados: Set<string>
  focado: string | null
  tempo: number
  seek(t: number): void
}): React.JSX.Element {
  const { duracao, sinais, cands, clips, selecionados, focado, tempo, seek } = props
  const canvas = useRef<HTMLCanvasElement>(null)

  // forma de "onda" a partir da energia do áudio
  useEffect(() => {
    const c = canvas.current
    if (!c || !sinais || !duracao) return
    const w = (c.width = c.clientWidth * devicePixelRatio)
    const h = (c.height = c.clientHeight * devicePixelRatio)
    const ctx = c.getContext('2d')!
    ctx.clearRect(0, 0, w, h)
    ctx.fillStyle = getComputedStyle(c).getPropertyValue('--texto-2') || '#888'
    const n = sinais.energia_db.length
    for (let x = 0; x < w; x++) {
      const i0 = Math.floor((x / w) * n)
      const i1 = Math.max(i0 + 1, Math.floor(((x + 1) / w) * n))
      let m = -90
      for (let i = i0; i < i1 && i < n; i++) m = Math.max(m, sinais.energia_db[i])
      const v = Math.max(0, Math.min(1, (m + 60) / 60))
      const bh = v * h * 0.9
      ctx.globalAlpha = 0.55
      ctx.fillRect(x, (h - bh) / 2, 1, bh)
    }
  }, [sinais, duracao])

  const pct = (s: number): string => `${duracao ? (s / duracao) * 100 : 0}%`
  return (
    <div
      className="timeline"
      onClick={(e) => {
        const r = e.currentTarget.getBoundingClientRect()
        seek(((e.clientX - r.left) / r.width) * duracao)
      }}
    >
      <canvas ref={canvas} />
      {cands.map((c) => (
        <div
          key={c.id}
          className={`marca-cand ${selecionados.has(c.id) ? 'sel' : ''} ${focado === c.id ? 'focado' : ''}`}
          style={{ left: pct(c.inicio), width: pct(c.fim - c.inicio), top: c.modo === 'longo' ? '70%' : 0 }}
          title={`${c.id} · ${c.nota.toFixed(0)} · ${(c.titulos ?? [''])[0]}`}
        />
      ))}
      {clips.map((c) => (
        <div key={c.id} className="marca-cand sel" style={{ left: pct(c.inicio), width: pct(c.fim - c.inicio), top: '85%' }} title={c.titulo} />
      ))}
      <div className="cursor" style={{ left: pct(tempo) }} />
    </div>
  )
}

const corNota = (n: number): string => (n >= 65 ? 'var(--nota-alta)' : n >= 45 ? 'var(--nota-media)' : 'var(--nota-baixa)')

function EditorClip(props: {
  api: Api
  base: string
  clip: Clip
  estilos: Estilo[]
  aoMudar(): void
  jobs: Record<string, Job>
  raiz: string
  temHF: boolean
  cand?: Candidato
  conversar(p: PedidoConversa): Promise<string>
  abrirEditor(): void
  editarDuracao(): void
}): React.JSX.Element {
  const { api, base, clip, estilos, aoMudar, jobs, raiz, temHF, cand, conversar, abrirEditor, editarDuracao } = props
  const t = useT()
  const [c, setC] = useState<Clip>(clip)
  const [aberto, setAberto] = useState(false)
  const [titulos, setTitulos] = useState<string[]>(clip.titulos_sugeridos)
  const [msg, setMsg] = useState('')
  useEffect(() => setC(clip), [clip])

  const legenda = (c.ajustes_estilo?.legenda as { altura_relativa?: number } | undefined) ?? {}
  const sujo = useMemo(() => JSON.stringify(c) !== JSON.stringify(clip), [c, clip])
  const renderizando = Object.values(jobs).find(
    (j) => j.tipo === 'renderizar' && (j.status === 'rodando' || j.status === 'na_fila') && (j.params.clips as string[] | undefined)?.includes(clip.id)
  )

  const salvar = async (): Promise<boolean> => {
    try {
      const { pasta: _p, saida: _s, preview: _v, ...dados } = c
      await api.put(`${base}/clips/${encodeURIComponent(c.id)}`, dados)
      setMsg(t.salvo)
      aoMudar()
      return true
    } catch (e) {
      setMsg((e instanceof Error ? e.message : String(e)))
      return false
    }
  }

  const renderizar = async (preview: boolean): Promise<void> => {
    if (sujo && !(await salvar())) return
    await api.post(`${base}/renderizar`, { clips: [c.id], preview })
  }

  const outrosTitulos = async (): Promise<void> => {
    setMsg('…')
    try {
      const r = await api.post<{ titulos: string[] }>(`${base}/clips/${encodeURIComponent(c.id)}/titulos`)
      setTitulos((ts) => [...new Set([...r.titulos, ...ts])])
      setMsg('')
    } catch (e) {
      setMsg((e instanceof Error ? e.message : String(e)))
    }
  }

  // apagar: tira o player da tela antes (no Windows o vídeo aberto segura a pasta) e mostra o erro do motor
  const [apagando, setApagando] = useState(false)
  const apagar = async (): Promise<void> => {
    const sim = await confirmar({
      titulo: t.apagarClipPergunta(c.titulo || c.id),
      mensagem: (
        <>
          <p style={{ margin: 0 }}>{t.apagarClipItens}</p>
          <p className="erro-txt" style={{ margin: 0 }}>{t.apagarClipDeVez}</p>
        </>
      ),
      ok: t.apagarClip,
      cancelar: t.cancelar,
      perigo: true
    })
    if (!sim) return
    setApagando(true)
    await new Promise((ok) => setTimeout(ok, 300))
    try {
      await api.del(`${base}/clips/${encodeURIComponent(c.id)}`, { confirmar: 'true' })
      aoMudar()
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e))
      setAberto(true)
      setApagando(false)
    }
  }


  // a versão editada pela IA, quando escolhida, é a saída do clip (o saida.mp4 original continua na pasta)
  const saida = clip.versao ? `${clip.pasta}/${clip.versao}` : clip.saida ? `${clip.pasta}/saida.mp4` : clip.preview ? `${clip.pasta}/preview.mp4` : null
  const gerado = clip.status === 'renderizado' // depois de gerado, o clip não muda de formato nem de estilo
  const estiloAtual = estilos.find((e) => e.id === c.estilo)

  return (
    <div className="clip-editor">
      <div className="linha" style={{ cursor: 'pointer' }} onClick={() => setAberto(!aberto)}>
        <strong>{aberto ? '▾' : '▸'} {c.titulo || c.id}</strong>
        <span className="chip">{c.formato}</span>
        <span className="chip">{c.estilo}</span>
        {estiloAtual?.requer_ia && <span className="chip usa-ia" title={t.usaIADica}>🤖 {t.usaIA}</span>}
        <span className="chip">{hms(c.fim - c.inicio)}</span>
        {clip.status === 'renderizado' && <span className="chip" style={{ color: 'var(--ok)' }}>MP4</span>}
        {renderizando && <span className="chip">{Math.round(renderizando.progresso * 100)}%</span>}
        {renderizando && (
          <button className="link" onClick={(e) => (e.stopPropagation(), void api.post(`/api/jobs/${renderizando.id}/cancelar`))}>
            {t.cancelarJob}
          </button>
        )}
        {cand && <NotaDetalhe cand={cand} className="chip-nota" style={{ background: corNota(cand.nota) }} />}
        <span className="espaco" style={{ flex: 1 }} />
        <button className="abrir-duracao" disabled={!!renderizando} title={t.dur.abrirDica}
          onClick={(ev) => (ev.stopPropagation(), editarDuracao())}>✂ {t.dur.abrir}</button>
        {/* o editor de vídeo trabalha em cima do vídeo gerado: fica travado até o clip ser renderizado */}
        <button className={`abrir-editor ${gerado ? 'primario' : 'travado'}`} disabled={!gerado || !!renderizando}
          title={gerado ? t.ed.abrirEditorDica : t.ed.editorTravado}
          onClick={(ev) => (ev.stopPropagation(), abrirEditor())}>{gerado ? '🎬' : '🔒'} {t.ed.abrirEditor}</button>
        <button className="perigo-contorno apagar-clip" disabled={apagando || !!renderizando}
          title={renderizando ? t.apagarClipRenderizando : t.apagarClip} aria-label={t.apagarClip}
          onClick={(e) => (e.stopPropagation(), void apagar())}>
          <span aria-hidden>🗑</span> {apagando ? t.apagando : t.apagarClipCurto}
        </button>
      </div>
      {renderizando && (
        <div className="render-andamento">
          <div className="linha">
            <strong>{t.renderizandoVideo}</strong>
            <span className="espaco" style={{ flex: 1 }} />
            <span>{Math.round(renderizando.progresso * 100)}%</span>
            <button className="link" onClick={() => void api.post(`/api/jobs/${renderizando.id}/cancelar`)}>{t.cancelarJob}</button>
          </div>
          <div className="barra-render"><span style={{ width: `${Math.round(renderizando.progresso * 100)}%` }} /></div>
          {renderizando.mensagem && <span className="dica">{renderizando.mensagem.replace(`${clip.id}: `, '')}</span>}
          <RelatoJob api={api} job={renderizando} />
        </div>
      )}
      {aberto && !renderizando && gerado && (
        // clip já gerado: formato e estilo ficam fixos; só thumb, outros títulos e a edição com IA (que mantém o estilo)
        <>
          {saida && (
            <div className="linha">
              {apagando ? <span className="dica">…</span>
                : <video src={api.midia(saida, String(Date.now() >> 14))} controls style={{ maxHeight: 300, borderRadius: 6 }} />}
              <button className="link" onClick={() => void ponte.mostrarNaPasta(`${raiz}/${saida}`)}>{t.mostrarNaPasta}</button>
            </div>
          )}
          <p className="dica" style={{ margin: 0 }}>{t.clipTravado}</p>
          <div className="campo">
            <label>{t.titulo}</label>
            <input value={c.titulo} onChange={(e) => setC({ ...c, titulo: e.target.value })} list={`tit-${c.id}`} />
            <datalist id={`tit-${c.id}`}>{titulos.map((x) => <option key={x} value={x} />)}</datalist>
            <div className="linha">
              {titulos.slice(0, 5).map((x) => (
                <button key={x} className="link" onClick={() => setC({ ...c, titulo: x })}>{x}</button>
              ))}
            </div>
            <div className="linha">
              <button onClick={() => void outrosTitulos()}>{t.outrosTitulos}</button>
              <button disabled={!sujo} onClick={() => void salvar()}>{t.salvar}</button>
              <span className="dica">{msg}</span>
            </div>
          </div>
          <EditarLegenda api={api} base={base} clip={clip} video={saida} aoMudar={aoMudar} />
          <Acabamento api={api} base={base} clip={clip} jobs={jobs} aoMudar={aoMudar} />
          <Thumbs api={api} base={base} clipId={c.id} jobs={jobs} raiz={raiz} />
          <section className="edicao-com-ia">
            <h4 style={{ margin: 0 }}>✨ {t.edicaoComIA}</h4>
            <MelhorarIA api={api} base={base} clip={clip.id} jobs={jobs} aoMudar={aoMudar} />
            <DirecaoDoClip api={api} base={base} clip={clip.id} jobs={jobs} aoMudar={aoMudar} />
            <EditarComIA api={api} base={base} clip={clip} aoMudar={aoMudar} conversar={conversar} />
            <div className="linha">
              <button className="primario" disabled={!!renderizando} onClick={() => void renderizar(false)} title={t.renderizarVersaoDica}>
                {t.renderizarVersao}
              </button>
            </div>
          </section>
        </>
      )}
      {aberto && !renderizando && !gerado && (
        <>
          <MelhorarIA api={api} base={base} clip={clip.id} jobs={jobs} aoMudar={aoMudar} />
          <div className="campo">
            <label>{t.titulo}</label>
            <input value={c.titulo} onChange={(e) => setC({ ...c, titulo: e.target.value })} list={`tit-${c.id}`} />
            <datalist id={`tit-${c.id}`}>{titulos.map((x) => <option key={x} value={x} />)}</datalist>
            <div className="linha">
              {titulos.slice(0, 5).map((x) => (
                <button key={x} className="link" onClick={() => setC({ ...c, titulo: x })}>{x}</button>
              ))}
            </div>
            <button onClick={() => void outrosTitulos()}>{t.outrosTitulos}</button>
          </div>
          <div className="linha">
            <label>{t.formato}</label>
            <select value={c.formato} onChange={(e) => setC({ ...c, formato: e.target.value })}>
              {['9:16', '1:1', '4:5', '16:9'].map((f) => <option key={f}>{f}</option>)}
            </select>
            <label title={t.plataformaDica}>{t.plataforma}</label>
            <select value={c.plataforma ?? ''} title={t.plataformaDica} onChange={(e) => setC({ ...c, plataforma: e.target.value || null })}>
              <option value="">{t.plataformaAuto}</option>
              {(c.formato === '9:16' ? ['youtube-shorts', 'instagram-reels', 'tiktok'] : ['youtube']).map((p) => (
                <option key={p} value={p}>{t.plataformas[p]}</option>
              ))}
            </select>
            <label>{t.estilo}</label>
            <select value={c.estilo} onChange={(e) => setC({ ...c, estilo: e.target.value })}>
              {estilos.map((e) => <option key={e.id} value={e.id}>{e.nome}</option>)}
            </select>
          </div>
          {estiloAtual?.motor === 'hyperframes' && !temHF && <span className="dica">{t.hyperframesAviso}</span>}
          <label className="linha">
            <input type="checkbox" checked={c.cartela} onChange={(e) => setC({ ...c, cartela: e.target.checked })} /> {t.cartela}
          </label>
          <div className="linha">
            <label>{t.posicaoLegenda}</label>
            <input
              type="range"
              min={0.1}
              max={0.92}
              step={0.01}
              value={legenda.altura_relativa ?? 0.68}
              onChange={(e) =>
                setC({ ...c, ajustes_estilo: { ...c.ajustes_estilo, legenda: { ...legenda, altura_relativa: Number(e.target.value) } } })
              }
            />
          </div>
          <div className="linha">
            <button disabled={!sujo} onClick={() => void salvar()}>{t.salvar}</button>
            <button disabled={!!renderizando} onClick={() => void renderizar(true)}>{t.previa}</button>
            <button className="primario" disabled={!!renderizando} onClick={() => void renderizar(false)}>{t.renderizar}</button>
            <span className="dica">{msg}</span>
          </div>
          <SonsPrevia api={api} />
          <Thumbs api={api} base={base} clipId={c.id} jobs={jobs} raiz={raiz} />
          <EditarComIA api={api} base={base} clip={clip} aoMudar={aoMudar} conversar={conversar} />
          {saida && (
            <div className="linha">
              {/* durante o render o player sai da tela: no Windows o arquivo aberto impede trocar o vídeo */}
              {renderizando || apagando
                ? <span className="dica">{apagando ? '…' : t.renderizandoVideo}</span>
                : <video src={api.midia(saida, String(Date.now() >> 14))} controls style={{ maxHeight: 260, borderRadius: 6 }} />}
              <button className="link" onClick={() => void ponte.mostrarNaPasta(`${raiz}/${saida}`)}>{t.mostrarNaPasta}</button>
            </div>
          )}
        </>
      )}
    </div>
  )
}

// Transcrição no passo 1, embaixo do vídeo: clicar no tempo leva o player até lá, a linha que está
// tocando fica marcada (e a lista acompanha), dá para buscar e corrigir o texto (Enter salva).
function AreaTranscricao(props: { trans: Transcricao | null; tempo: number; seek(t: number): void; salvar(i: number, texto: string): Promise<void> }): React.JSX.Element {
  const { trans, tempo, seek, salvar } = props
  const t = useT()
  const [busca, setBusca] = useState('')
  const [seguir, setSeguir] = useState(true)
  const lista = useRef<HTMLDivElement>(null)
  const q = busca.trim().toLowerCase()
  const segs = (trans?.segmentos ?? []).map((s, i) => ({ ...s, i })).filter((s) => !q || s.texto.toLowerCase().includes(q))
  const atual = (trans?.segmentos ?? []).findIndex((s) => tempo >= s.inicio && tempo < s.fim)

  useEffect(() => {
    if (!seguir || q || atual < 0 || !lista.current) return
    const el = lista.current.querySelector<HTMLElement>(`[data-i="${atual}"]`)
    if (el && !el.contains(document.activeElement)) el.scrollIntoView({ block: 'nearest' })
  }, [atual, seguir, q])

  const copiar = (): void => {
    void navigator.clipboard.writeText((trans?.segmentos ?? []).map((s) => `[${hms(s.inicio)}] ${s.texto}`).join('\n'))
  }

  return (
    <section className="area-transcricao">
      <div className="linha">
        <h4 style={{ margin: 0 }}>{t.transcricao}</h4>
        <span className="dica">{trans ? t.editarTranscricaoDica : t.aguardandoAnalise}</span>
        <span className="espaco" style={{ flex: 1 }} />
        {trans && (
          <>
            <input type="search" placeholder={t.buscarNaTranscricao} value={busca} onChange={(e) => setBusca(e.target.value)} />
            {q && <span className="dica">{t.nTrechos(segs.length)}</span>}
            <label className="linha dica"><input type="checkbox" checked={seguir} onChange={(e) => setSeguir(e.target.checked)} /> {t.seguirVideo}</label>
            <button className="link" onClick={copiar}>{t.copiarTranscricao}</button>
          </>
        )}
      </div>
      {trans && (
        <div className="transcricao" ref={lista}>
          {segs.map((s) => (
            <div key={s.i} data-i={s.i} className={`seg ${s.i === atual ? 'atual' : ''}`}>
              <span className="t" onClick={() => seek(s.inicio)}>{hms(s.inicio)}</span>
              <span
                contentEditable
                suppressContentEditableWarning
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    e.currentTarget.blur()
                  }
                }}
                onBlur={(e) => {
                  const novo = e.currentTarget.textContent ?? ''
                  if (novo !== s.texto) void salvar(s.i, novo)
                }}
              >
                {s.texto}
              </span>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
