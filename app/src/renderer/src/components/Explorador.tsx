import { useCallback, useEffect, useRef, useState } from 'react'
import { hms, type Api, type Job } from '../api'
import { useT } from '../i18n'
import { ponte } from '../ponte'

type CanalItem = { slug: string; nome: string; idioma: string; projetos: number }
type VideoItem = { id: string; titulo: string; criado_em: string; fase: string; clips: number; cortes: number; thumb: string | null }
type ArquivoTexto = { nome: string; caminho: string }
type Menu = { x: number; y: number; canal: CanalItem; video?: VideoItem }
type Dialogo =
  | { tipo: 'renomear'; canal: CanalItem; video?: VideoItem }
  | { tipo: 'detalhes'; canal: CanalItem; video?: VideoItem }
  | { tipo: 'apagar'; canal: CanalItem; video?: VideoItem }
  | { tipo: 'mover'; canal: CanalItem; video: VideoItem }

type Props = {
  api: Api
  versao: number
  ativo: string // "canal/projeto" aberto
  jobs: Record<string, Job>
  abrirArquivo(caminho: string): void
  abrirProjeto(canal: string, projeto: string, titulo?: string): void
  novoCanal(): void
  novoVideo(canal?: string): void
  fecharAbas(prefixo: string): void // fecha as abas (e os players) antes de mover ou apagar
  aoMudar(): void
}

const bytes = (n: number): string => (n > 1e9 ? `${(n / 1e9).toFixed(1)} GB` : n > 1e6 ? `${(n / 1e6).toFixed(0)} MB` : `${Math.round(n / 1e3)} KB`)

// Explorador: a lista de canais e, dentro de cada um, os vídeos. Botão direito abre as opções.
export function Explorador(props: Props): React.JSX.Element {
  const { api, versao, ativo, jobs, abrirArquivo, abrirProjeto, novoCanal, novoVideo, fecharAbas, aoMudar } = props
  const t = useT()
  const e = t.exp
  const [canais, setCanais] = useState<CanalItem[]>([])
  const [videos, setVideos] = useState<Record<string, VideoItem[]>>({})
  const [abertos, setAbertos] = useState<Set<string>>(() => {
    try {
      return new Set(JSON.parse(localStorage.getItem('clipator.explorador.abertos') ?? '[]') as string[])
    } catch {
      return new Set()
    }
  })
  // pasta "Regras e textos" de cada canal: aberta ou não, e os arquivos dela
  const [textosAbertos, setTextosAbertos] = useState<Set<string>>(() => {
    try {
      return new Set(JSON.parse(localStorage.getItem('clipator.explorador.textos') ?? '[]') as string[])
    } catch {
      return new Set()
    }
  })
  const [textos, setTextos] = useState<Record<string, ArquivoTexto[]>>({})
  const carregarTextos = useCallback((slug: string) => {
    api.get<ArquivoTexto[]>(`/api/canais/${encodeURIComponent(slug)}/textos`).then((l) => setTextos((v) => ({ ...v, [slug]: l })), () => undefined)
  }, [api])
  const alternarTextos = (slug: string): void => {
    setTextosAbertos((s) => {
      const n = new Set(s)
      if (n.has(slug)) n.delete(slug)
      else n.add(slug)
      try {
        localStorage.setItem('clipator.explorador.textos', JSON.stringify([...n]))
      } catch {
        /* sem armazenamento */
      }
      return n
    })
    carregarTextos(slug)
  }
  useEffect(() => {
    for (const slug of textosAbertos) carregarTextos(slug)
  }, [versao]) // eslint-disable-line react-hooks/exhaustive-deps
  const [menu, setMenu] = useState<Menu | null>(null)
  const [dialogo, setDialogo] = useState<Dialogo | null>(null)
  const [erro, setErro] = useState('')

  const carregarVideos = useCallback((slug: string) => {
    api.get<VideoItem[]>(`/api/canais/${encodeURIComponent(slug)}/projetos`).then((l) => setVideos((v) => ({ ...v, [slug]: l })), () => undefined)
  }, [api])
  const carregar = useCallback(() => {
    api.get<CanalItem[]>('/api/canais').then((cs) => {
      setCanais(cs)
      setErro('')
      for (const c of cs) if (abertos.has(c.slug) || ativo.startsWith(`${c.slug}/`)) carregarVideos(c.slug)
    }, (err) => setErro(err instanceof Error ? err.message : String(err)))
  }, [api, abertos, ativo, carregarVideos])
  useEffect(carregar, [api, versao]) // eslint-disable-line react-hooks/exhaustive-deps

  // um job terminou: o status dos vídeos muda
  const fim = Object.values(jobs).filter((j) => j.status === 'ok' || j.status === 'erro').length
  useEffect(() => {
    for (const slug of Object.keys(videos)) carregarVideos(slug)
  }, [fim]) // eslint-disable-line react-hooks/exhaustive-deps

  const alternar = (slug: string): void => {
    setAbertos((s) => {
      const n = new Set(s)
      if (n.has(slug)) n.delete(slug)
      else {
        n.add(slug)
        carregarVideos(slug)
      }
      try {
        localStorage.setItem('clipator.explorador.abertos', JSON.stringify([...n]))
      } catch {
        /* sem armazenamento */
      }
      return n
    })
  }

  useEffect(() => {
    if (!menu) return
    const fechar = (): void => setMenu(null)
    window.addEventListener('click', fechar)
    window.addEventListener('keydown', fechar)
    return () => {
      window.removeEventListener('click', fechar)
      window.removeEventListener('keydown', fechar)
    }
  }, [menu])

  const ativoJob = (canal: string, video?: string): Job | undefined => Object.values(jobs).find((j) =>
    (j.status === 'rodando' || j.status === 'na_fila') && j.params.canal === canal && (!video || j.params.projeto === video))

  const fase = (v: VideoItem): string => e.fases[v.fase as keyof typeof e.fases] ?? v.fase


  const acoes = (m: Menu): { rotulo: string; fazer(): void; perigo?: boolean; separar?: boolean }[] => {
    const c = m.canal
    const v = m.video
    if (v) {
      return [
        { rotulo: e.abrir, fazer: () => abrirProjeto(c.slug, v.id, v.titulo) },
        { rotulo: e.renomear, fazer: () => setDialogo({ tipo: 'renomear', canal: c, video: v }) },
        { rotulo: e.detalhesVideo, fazer: () => setDialogo({ tipo: 'detalhes', canal: c, video: v }) },
        { rotulo: e.refazerAnalise, separar: true, fazer: () => void api.post(`/api/canais/${encodeURIComponent(c.slug)}/projetos/${encodeURIComponent(v.id)}/analisar`, {}, { refazer: 'true' }) },
        { rotulo: e.moverPara, fazer: () => setDialogo({ tipo: 'mover', canal: c, video: v }) },
        { rotulo: e.abrirPasta, separar: true, fazer: () => void abrirPasta(c, v) },
        { rotulo: e.copiarCaminho, fazer: () => void copiarCaminho(c, v) },
        { rotulo: e.apagarVideo, perigo: true, separar: true, fazer: () => setDialogo({ tipo: 'apagar', canal: c, video: v }) }
      ]
    }
    return [
      { rotulo: alvoAberto(c) ? e.recolher : e.abrir, fazer: () => alternar(c.slug) },
      { rotulo: e.novoVideo, fazer: () => novoVideo(c.slug) },
      { rotulo: e.regrasETextos, fazer: () => {
        if (!abertos.has(c.slug)) alternar(c.slug)
        if (!textosAbertos.has(c.slug)) alternarTextos(c.slug)
      } },
      { rotulo: e.renomear, fazer: () => setDialogo({ tipo: 'renomear', canal: c }) },
      { rotulo: e.detalhesCanal, fazer: () => setDialogo({ tipo: 'detalhes', canal: c }) },
      { rotulo: e.abrirPasta, separar: true, fazer: () => void abrirPasta(c) },
      { rotulo: e.copiarCaminho, fazer: () => void copiarCaminho(c) },
      { rotulo: e.apagarCanal, perigo: true, separar: true, fazer: () => setDialogo({ tipo: 'apagar', canal: c }) }
    ]
  }
  const alvoAberto = (c: CanalItem): boolean => abertos.has(c.slug)

  const pastaAbs = async (c: CanalItem, v?: VideoItem): Promise<string> => {
    const d = await api.get<{ pasta: string }>(v ? `/api/canais/${encodeURIComponent(c.slug)}/projetos/${encodeURIComponent(v.id)}/detalhes` : `/api/canais/${encodeURIComponent(c.slug)}/detalhes`)
    return d.pasta
  }
  const abrirPasta = async (c: CanalItem, v?: VideoItem): Promise<void> => {
    const p = await pastaAbs(c, v)
    await ponte.abrir(p)
  }
  const copiarCaminho = async (c: CanalItem, v?: VideoItem): Promise<void> => {
    await navigator.clipboard.writeText(await pastaAbs(c, v))
  }

  return (
    <aside className="painel explorador">
      <h2>
        {e.canais}
        <span className="espaco" />
        <button className="link" onClick={novoCanal} title={t.novoCanal}>＋ {e.canal}</button>
        <button className="link" onClick={() => novoVideo()} title={e.novoVideo}>＋ {e.video}</button>
        <button className="link" onClick={carregar} title={e.atualizar}>↻</button>
      </h2>
      <div className="rolagem">
        {erro && <p className="erro-txt">{erro}</p>}
        {!canais.length && !erro && <p className="dica" style={{ padding: 10 }}>{e.semCanais}</p>}
        <ul className="lista-canais" role="tree">
          {canais.map((c) => (
            <li key={c.slug} role="treeitem" aria-expanded={abertos.has(c.slug)} title={c.slug}>
              <div className={`canal-item ${ativo.startsWith(`${c.slug}/`) ? 'ativo' : ''}`} onClick={() => alternar(c.slug)}
                onContextMenu={(ev) => {
                  ev.preventDefault()
                  setMenu({ x: ev.clientX, y: ev.clientY, canal: c })
                }}>
                <span className="seta">{abertos.has(c.slug) ? '▾' : '▸'}</span>
                <span className="avatar">{c.nome.slice(0, 1).toUpperCase()}</span>
                <span className="nome">{c.nome}</span>
                {ativoJob(c.slug) && <span className="ponto-ativo" title={e.trabalhando} />}
                <span className="contagem">{c.projetos}</span>
              </div>
              {abertos.has(c.slug) && (
                <ul className="lista-videos">
                  <li role="treeitem" aria-expanded={textosAbertos.has(c.slug)} title={e.regrasETextosDica}>
                    <div className="video-item pasta-textos" onClick={() => alternarTextos(c.slug)}>
                      <span className="seta">{textosAbertos.has(c.slug) ? '▾' : '▸'}</span>
                      <span className="miniatura vazia">📁</span>
                      <span className="textos"><span className="titulo">{e.regrasETextos}</span></span>
                    </div>
                    {textosAbertos.has(c.slug) && (
                      <ul className="lista-textos">
                        {(textos[c.slug] ?? []).map((a) => (
                          <li key={a.caminho} role="treeitem" title={a.caminho}>
                            <div className="video-item arquivo-texto" onClick={() => abrirArquivo(a.caminho)}>
                              <span className="miniatura vazia">📝</span>
                              <span className="textos">
                                <span className="titulo">{e.nomesTextos[a.nome] ?? a.nome}</span>
                                <span className="fase-video">{a.nome}</span>
                              </span>
                            </div>
                          </li>
                        ))}
                      </ul>
                    )}
                  </li>
                  {(videos[c.slug] ?? []).map((v) => {
                    const j = ativoJob(c.slug, v.id)
                    return (
                      <li key={v.id} role="treeitem" title={`${v.titulo}\n${v.id}`}>
                        <div className={`video-item ${ativo === `${c.slug}/${v.id}` ? 'ativo' : ''}`} onClick={() => abrirProjeto(c.slug, v.id, v.titulo)}
                          onContextMenu={(ev) => {
                            ev.preventDefault()
                            ev.stopPropagation()
                            setMenu({ x: ev.clientX, y: ev.clientY, canal: c, video: v })
                          }}>
                          {v.thumb ? <img className="miniatura" src={api.midia(v.thumb)} alt="" /> : <span className="miniatura vazia">🎬</span>}
                          <span className="textos">
                            <span className="titulo">{v.titulo}</span>
                            <span className={`fase-video fase-${v.fase}`}>
                              {j ? `${t.tiposJob[j.tipo] ?? j.tipo} ${Math.round(j.progresso * 100)}%` : v.fase === 'clips' ? e.nClips(v.clips) : v.fase === 'cortes' ? e.nCortes(v.cortes) : fase(v)}
                            </span>
                          </span>
                        </div>
                      </li>
                    )
                  })}
                  {videos[c.slug]?.length === 0 && <li className="dica" style={{ padding: '2px 30px' }}>{e.semVideos}</li>}
                </ul>
              )}
            </li>
          ))}
        </ul>
      </div>

      {menu && (
        <div className="menu-contexto" style={{ left: Math.min(menu.x, window.innerWidth - 230), top: Math.min(menu.y, window.innerHeight - 300) }}
          role="menu" onClick={(ev) => ev.stopPropagation()}>
          {acoes(menu).map((a, k) => (
            <button key={k} role="menuitem" className={`${a.perigo ? 'perigo' : ''} ${a.separar ? 'separar' : ''}`} onClick={() => {
              setMenu(null)
              a.fazer()
            }}>{a.rotulo}</button>
          ))}
        </div>
      )}
      {dialogo && (
        <DialogoExplorador api={api} d={dialogo} canais={canais} fechar={() => setDialogo(null)} abrirArquivo={props.abrirArquivo}
          fecharAbas={fecharAbas} ocupado={!!ativoJob(dialogo.canal.slug, dialogo.video?.id)}
          aoMudar={(slug) => {
            setDialogo(null)
            carregar()
            if (slug) carregarVideos(slug)
            aoMudar()
          }} />
      )}
    </aside>
  )
}

type Detalhes = Record<string, unknown> & { pasta: string; bytes: number }

function DialogoExplorador(props: {
  api: Api
  d: Dialogo
  canais: CanalItem[]
  ocupado: boolean
  fechar(): void
  abrirArquivo(caminho: string): void
  fecharAbas(prefixo: string): void
  aoMudar(slugAfetado?: string): void
}): React.JSX.Element {
  const { api, d, canais, ocupado, fechar, abrirArquivo, fecharAbas, aoMudar } = props
  const t = useT()
  const e = t.exp
  const c = d.canal
  const v = d.video
  const baseC = `/api/canais/${encodeURIComponent(c.slug)}`
  const baseV = v ? `${baseC}/projetos/${encodeURIComponent(v.id)}` : ''
  const [det, setDet] = useState<Detalhes | null>(null)
  const [texto, setTexto] = useState(d.tipo === 'renomear' ? (v ? v.titulo : c.nome) : '')
  const [destino, setDestino] = useState(canais.find((x) => x.slug !== c.slug)?.slug ?? '')
  const [msg, setMsg] = useState('')
  const [indo, setIndo] = useState(false)
  const entrada = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (d.tipo === 'detalhes' || d.tipo === 'apagar') {
      const url = d.tipo === 'apagar' ? (v ? baseV : baseC) : `${v ? baseV : baseC}/detalhes`
      const pedido = d.tipo === 'apagar' ? api.del<Detalhes>(url, { so_conferir: 'true' }) : api.get<Detalhes>(url)
      pedido.then(setDet, (err) => setMsg(err instanceof Error ? err.message : String(err)))
    }
    entrada.current?.focus()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const fazer = async (f: () => Promise<void>): Promise<void> => {
    setIndo(true)
    setMsg('')
    try {
      await f()
    } catch (err) {
      setMsg(err instanceof Error ? err.message : String(err))
      setIndo(false)
    }
  }

  const renomear = (): Promise<void> => fazer(async () => {
    if (v) await api.put(baseV, { titulo: texto })
    else await api.put(baseC, { nome: texto })
    aoMudar(c.slug)
  })
  const mover = (): Promise<void> => fazer(async () => {
    if (!v) return
    fecharAbas(`p:${c.slug}/${v.id}`)
    await new Promise((ok) => setTimeout(ok, 400)) // o Windows solta os arquivos do player
    await api.post(`${baseV}/mover`, { destino })
    aoMudar(destino)
  })
  const apagar = (): Promise<void> => fazer(async () => {
    if (!det) return
    fecharAbas(v ? `p:${c.slug}/${v.id}` : `p:${c.slug}/`)
    await new Promise((ok) => setTimeout(ok, 500))
    // confere de novo (job pode ter começado) e manda para a Lixeira; sem Lixeira (modo web), apaga de vez
    await (v ? api.del(baseV, { so_conferir: 'true' }) : api.del(baseC, { so_conferir: 'true' }))
    if (ponte.lixeira) await ponte.lixeira(det.pasta)
    else await (v ? api.del(baseV, { confirmar: 'true' }) : api.del(baseC, { confirmar: c.slug }))
    aoMudar(c.slug)
  })

  const titulo = d.tipo === 'renomear' ? e.renomear : d.tipo === 'mover' ? e.moverPara : d.tipo === 'apagar' ? (v ? e.apagarVideo : e.apagarCanal) : v ? e.detalhesVideo : e.detalhesCanal
  const linha = (k: string, val: React.ReactNode): React.JSX.Element | null => (val === undefined || val === null || val === '' ? null : (
    <div className="det-linha"><span className="dica">{k}</span><span>{val}</span></div>
  ))
  const etapas = det?.etapas as Record<string, string> | undefined

  return (
    <div className="modal-fundo" onMouseDown={(ev) => ev.target === ev.currentTarget && fechar()}>
      <div className="modal dialogo-explorador" role="dialog" aria-label={titulo}>
        <h3>{titulo}: {v ? v.titulo : c.nome}</h3>
        {d.tipo === 'renomear' && (
          <>
            <input ref={entrada} value={texto} onChange={(ev) => setTexto(ev.target.value)} onKeyDown={(ev) => ev.key === 'Enter' && void renomear()} />
            <p className="dica">{e.renomearDica}</p>
          </>
        )}
        {d.tipo === 'mover' && (
          <label className="campo">{e.destino}
            <select value={destino} onChange={(ev) => setDestino(ev.target.value)}>
              {canais.filter((x) => x.slug !== c.slug).map((x) => <option key={x.slug} value={x.slug}>{x.nome}</option>)}
            </select>
          </label>
        )}
        {(d.tipo === 'detalhes' || d.tipo === 'apagar') && det && (
          <div className="detalhes">
            {v ? (
              <>
                {linha(e.origem, String(det.origem ?? ''))}
                {linha(e.tituloOriginal, String(det.titulo_original ?? ''))}
                {linha(e.duracao, typeof det.duracao === 'number' ? hms(det.duracao) : '')}
                {linha(e.criado, String(det.criado_em ?? '').slice(0, 16).replace('T', ' '))}
                {linha(e.analise, etapas ? Object.entries(etapas).map(([k, s]) => `${t.etapas[k] ?? k}: ${t.status[s] ?? s}`).join(' · ') : '')}
                {linha(e.cortesEClips, `${String(det.cortes)} / ${String(det.clips)}`)}
              </>
            ) : (
              <>
                {linha(e.nVideos, String(det.videos))}
                {linha(e.nClipsTotal, String(det.clips))}
                {linha(e.glossario, ((det.glossario as string[]) ?? []).join(', '))}
                {linha(e.palavras, ((det.palavras_chave as string[]) ?? []).map((p) => `#${p}`).join(' '))}
                {linha(e.estiloPadrao, String(det.estilo_padrao ?? ''))}
                {d.tipo === 'detalhes' && linha(e.arquivos, (
                  <span className="linha" style={{ flexWrap: 'wrap' }}>
                    {((det.arquivos as string[]) ?? []).map((a) => (
                      <button key={a} className="link" onClick={() => {
                        abrirArquivo(a)
                        fechar()
                      }}>{a.split('/').pop()}</button>
                    ))}
                  </span>
                ))}
              </>
            )}
            {linha(e.tamanho, bytes(det.bytes))}
            {linha(e.pasta, <code className="caminho">{det.pasta}</code>)}
          </div>
        )}
        {d.tipo === 'apagar' && det && (
          <>
            <p className="erro-txt" style={{ margin: 0 }}>{v ? e.apagarVideoAviso(bytes(det.bytes)) : e.apagarCanalAviso(Number(det.videos), Number(det.clips), bytes(det.bytes))}</p>
            <p className="dica" style={{ margin: 0 }}>{ponte.lixeira ? e.vaiParaLixeira : e.apagaDeVez}</p>
            {!v && (
              <label className="campo">{e.digiteONome(c.slug)}
                <input ref={entrada} value={texto} onChange={(ev) => setTexto(ev.target.value)} />
              </label>
            )}
          </>
        )}
        {ocupado && (d.tipo === 'apagar' || d.tipo === 'mover') && <p className="erro-txt">{e.ocupado}</p>}
        {msg && <p className="erro-txt">{msg}</p>}
        <div className="linha">
          <span className="espaco" style={{ flex: 1 }} />
          <button onClick={fechar}>{d.tipo === 'detalhes' ? t.fechar : e.cancelar}</button>
          {d.tipo === 'renomear' && <button className="primario" disabled={indo || !texto.trim()} onClick={() => void renomear()}>{e.salvar}</button>}
          {d.tipo === 'mover' && <button className="primario" disabled={indo || !destino || ocupado} onClick={() => void mover()}>{e.mover}</button>}
          {d.tipo === 'apagar' && (
            <button className="perigo" disabled={indo || !det || ocupado || (!v && texto !== c.slug)} onClick={() => void apagar()}>
              {v ? e.apagarVideo : e.apagarCanal}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
