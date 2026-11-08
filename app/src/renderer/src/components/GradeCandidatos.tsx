import { useEffect, useRef, useState } from 'react'
import { hms, type Api, type Candidato, type Job } from '../api'
import { useT } from '../i18n'
import { NotaDetalhe } from './NotaDetalhe'

type Quadro = { rotulo: string; tempo: number; imagem: string; frase: string }
type Quadros = { quadros: Quadro[]; rosto_x?: number }
export type Capitulo = { inicio?: number | null; fim?: number | null; titulo?: string | null }

type Props = {
  api: Api
  base: string
  video: string | null
  cands: Candidato[]
  capitulos: Capitulo[]
  selecionados: Set<string>
  setSelecionados(s: Set<string>): void
  focado: string | null
  aoFocar(c: Candidato): void
  verNoPrincipal(c: Candidato): void
  escolherEstilo(): void
  editarDuracao(c: Candidato): void
  jobAtivo?: Job
}

const cor = (n: number): string => (n >= 65 ? 'var(--nota-alta)' : n >= 45 ? 'var(--nota-media)' : 'var(--nota-baixa)')

// Só uma prévia toca por vez: dar play numa pausa a anterior.
let tocandoAgora: HTMLVideoElement | null = null

// Candidatos em duas prateleiras: cortes 16:9 (modo longo) grandes e com contexto, e shorts verticais.
export function GradeCandidatos(props: Props): React.JSX.Element {
  const { api, base, video, cands, capitulos, selecionados, setSelecionados, focado, aoFocar, verNoPrincipal, escolherEstilo, editarDuracao, jobAtivo } = props
  const t = useT()
  const [msg, setMsg] = useState('')
  const ordem = [...cands].sort((a, b) => b.nota - a.nota)
  const longos = ordem.filter((c) => c.modo === 'longo')
  const shorts = ordem.filter((c) => c.modo !== 'longo')
  const [aba, setAba] = useState<'shorts' | 'longos' | null>(null)
  const abaAtual = aba ?? (shorts.length || !longos.length ? 'shorts' : 'longos')

  const alternar = (id: string): void => {
    const n = new Set(selecionados)
    if (n.has(id)) n.delete(id)
    else n.add(id)
    setSelecionados(n)
  }

  const card = (c: Candidato, tipo: 'longo' | 'short'): React.JSX.Element => (
    <CardCandidato
      key={c.id}
      tipo={tipo}
      api={api}
      base={base}
      video={video}
      cand={c}
      capitulo={tipo === 'longo' ? capituloDe(capitulos, c.inicio) : undefined}
      selecionado={selecionados.has(c.id)}
      focado={focado === c.id}
      alternar={() => alternar(c.id)}
      focar={() => aoFocar(c)}
      verNoPrincipal={() => verNoPrincipal(c)}
      editarDuracao={() => editarDuracao(c)}
    />
  )

  return (
    <section className="grade-area">
      <div className="barra-grade">
        <strong>{t.candidatos}</strong>
        {cands.length > 0 && <span className="dica">{cands.length}</span>}
        <span className="dica">{t.selecionados(selecionados.size)}</span>
        <span className="espaco" />
        {selecionados.size > 0 && <button className="link" onClick={() => setSelecionados(new Set())}>{t.gal.limparSelecao}</button>}
        <button className="primario" disabled={!selecionados.size} onClick={escolherEstilo}>{t.gal.escolherEstilo}</button>
      </div>
      {msg && <p className="erro-txt" style={{ margin: '0 12px' }}>{msg}</p>}
      {!cands.length && (
        <p className="dica" style={{ padding: '12px' }}>
          {jobAtivo ? `${jobAtivo.mensagem || t.status[jobAtivo.status]} ${Math.round(jobAtivo.progresso * 100)}%` : t.aguardandoAnalise}
        </p>
      )}
      {cands.length > 0 && (
        <>
          <div className="abas-cortes" role="tablist">
            <button role="tab" aria-selected={abaAtual === 'shorts'} className={abaAtual === 'shorts' ? 'ativa' : ''} onClick={() => setAba('shorts')}>
              {t.shorts} <span className="contador">{shorts.length}</span>
            </button>
            <button role="tab" aria-selected={abaAtual === 'longos'} className={abaAtual === 'longos' ? 'ativa' : ''} onClick={() => setAba('longos')}>
              {t.cortes169} <span className="contador">{longos.length}</span>
            </button>
          </div>
          {abaAtual === 'longos' && (longos.length > 0 ? (
            <div className="grade-longos">{longos.map((c) => card(c, 'longo'))}</div>
          ) : (
            // análises antigas (ou sem a opção marcada) não têm cortes 16:9: dá para gerar sem refazer nada
            <div className="sem-longos">
              <span className="dica">{t.semLongos}</span>
              <button disabled={!!jobAtivo} onClick={() => void api.post(`${base}/candidatos`, {}, { modo: 'longo' }).catch((e) => setMsg(e instanceof Error ? e.message : String(e)))}>
                {t.gerarLongos}
              </button>
            </div>
          ))}
          {abaAtual === 'shorts' && (shorts.length > 0
            ? <div className="grade-shorts">{shorts.map((c) => card(c, 'short'))}</div>
            : <p className="dica sem-longos">{t.semShorts}</p>)}
        </>
      )}
    </section>
  )
}

function capituloDe(capitulos: Capitulo[], t: number): string | undefined {
  const c = capitulos.find((c) => (c.inicio ?? 0) <= t && (c.fim == null || t < c.fim))
  return c?.titulo ?? undefined
}

function CardCandidato(props: {
  tipo: 'longo' | 'short'
  api: Api
  base: string
  video: string | null
  cand: Candidato
  capitulo?: string
  selecionado: boolean
  focado: boolean
  alternar(): void
  focar(): void
  verNoPrincipal(): void
  editarDuracao(): void
}): React.JSX.Element {
  const { tipo, api, base, video, cand, capitulo, selecionado, focado, alternar, focar, verNoPrincipal, editarDuracao } = props
  const t = useT()
  const caixa = useRef<HTMLDivElement>(null)
  const [visivel, setVisivel] = useState(false)
  const [pedidoPlay, setPedidoPlay] = useState(0)
  const [dados, setDados] = useState<Quadros | null>(null)

  // só gera a miniatura quando o card aparece na tela
  useEffect(() => {
    const el = caixa.current
    if (!el || visivel) return
    const obs = new IntersectionObserver((es) => {
      if (es.some((e) => e.isIntersecting)) {
        setVisivel(true)
        obs.disconnect()
      }
    }, { rootMargin: '300px' })
    obs.observe(el)
    return () => obs.disconnect()
  }, [visivel])

  useEffect(() => {
    if (!visivel) return
    api.get<Quadros>(`${base}/candidatos/${cand.id}/quadros`).then(setDados, () => setDados({ quadros: [] }))
  }, [api, base, cand.id, cand.inicio, cand.fim, visivel])

  const q = dados?.quadros
  const poster = q?.[1] ?? q?.[0]
  const titulo = (cand.titulos ?? [])[0] ?? cand.id
  const motivo = cand.ia?.motivo || cand.motivos[0] || ''
  const enquadre = tipo === 'short' ? `${Math.round((dados?.rosto_x ?? 0.5) * 100)}% 50%` : 'center'

  return (
    <div ref={caixa} className={`card-cand ${tipo} ${focado ? 'focado' : ''} ${selecionado ? 'sel' : ''}`}>
      <div className="mini">
        {video && (
          <PlayerCorte
            src={api.midia(video)}
            poster={poster ? api.midia(poster.imagem, `${cand.inicio}-${cand.fim}`) : undefined}
            inicio={cand.inicio}
            fim={cand.fim}
            enquadre={enquadre}
            pedidoPlay={pedidoPlay}
          />
        )}
        <NotaDetalhe cand={cand} className="selo-nota" style={{ background: cor(cand.nota) }} />
        <input type="checkbox" className="sel-cand" checked={selecionado} onChange={alternar} aria-label={cand.id} />
      </div>
      <div className="titulo" onClick={() => {
        focar()
        setPedidoPlay((n) => n + 1)
      }} title={t.tocarNoCard}>{titulo}</div>
      {video && (
        <div className="acoes-card">
          <button className="link ver-principal" onClick={verNoPrincipal}>{t.verNoPrincipal}</button>
          <button className="link editar-duracao-card" onClick={editarDuracao} title={t.dur.abrirDica}>✂ {t.dur.abrir}</button>
        </div>
      )}
      {tipo === 'longo' ? (
        <>
          <div className="meta">
            {hms(cand.inicio)}–{hms(cand.fim)} · {hms(cand.duracao)}
            {capitulo ? ` · ${t.capitulo}: ${capitulo}` : ''}
            {cand.ia ? ` · ${cand.ia.agente}` : ''}
          </div>
          {motivo && <div className="meta motivo">{motivo}</div>}
          <p className="fala">{q?.[0]?.frase ?? cand.texto.slice(0, 260)}</p>
        </>
      ) : (
        <div className="meta">{hms(cand.duracao)}{cand.ia ? ` · ${cand.ia.agente}` : ''}</div>
      )}
    </div>
  )
}

// Player só do trecho: a barra vai de 0 (início do corte) à duração do corte e para sozinho no fim.
// O endereço leva #t=início,fim para o navegador já abrir no corte, e o play só começa depois do
// salto (sem tocar o começo do vídeo original por um instante).
export function PlayerCorte(props: { src: string; poster?: string; inicio: number; fim: number; enquadre: string; pedidoPlay?: number }): React.JSX.Element {
  const { src, poster, inicio, fim, enquadre, pedidoPlay = 0 } = props
  const t = useT()
  const v = useRef<HTMLVideoElement>(null)
  const barra = useRef<HTMLDivElement>(null)
  const [tocando, setTocando] = useState(false)
  const [pos, setPos] = useState(0)
  const dur = Math.max(0.1, fim - inicio)
  const srcCorte = `${src}#t=${inicio.toFixed(2)},${fim.toFixed(2)}`

  useEffect(() => () => {
    if (tocandoAgora === v.current) tocandoAgora = null
  }, [])

  // leva o vídeo para `rel` segundos depois do início do corte e espera o salto terminar
  const ir = (rel: number): Promise<void> => {
    const el = v.current
    const alvo = inicio + Math.max(0, Math.min(rel, dur - 0.05))
    setPos(alvo - inicio)
    if (!el) return Promise.resolve()
    return new Promise((ok) => {
      const saltar = (): void => {
        if (Math.abs(el.currentTime - alvo) < 0.05) return ok()
        el.addEventListener('seeked', () => ok(), { once: true })
        el.currentTime = alvo
      }
      if (el.readyState >= 1) saltar()
      else {
        el.addEventListener('loadedmetadata', saltar, { once: true })
        el.load()
      }
    })
  }

  const play = async (): Promise<void> => {
    const el = v.current
    if (!el) return
    if (tocandoAgora && tocandoAgora !== el) tocandoAgora.pause()
    tocandoAgora = el
    const atual = el.readyState >= 1 ? el.currentTime : -1
    if (atual < inicio || atual >= fim - 0.05) await ir(0)
    void el.play().catch(() => undefined)
  }

  // cada clique no título do card pede um play do começo do corte (o contador só sobe)
  useEffect(() => {
    if (!pedidoPlay) return
    void ir(0).then(play)
  }, [pedidoPlay]) // eslint-disable-line react-hooks/exhaustive-deps

  // clicar ou arrastar na barra procura só dentro do corte
  const procurar = (clientX: number): void => {
    const b = barra.current?.getBoundingClientRect()
    if (!b) return
    void ir(((clientX - b.left) / Math.max(1, b.width)) * dur)
  }
  const arrastar = (e: React.PointerEvent<HTMLDivElement>): void => {
    e.preventDefault()
    const alca = e.currentTarget
    alca.setPointerCapture(e.pointerId)
    procurar(e.clientX)
    const mover = (ev: PointerEvent): void => procurar(ev.clientX)
    const soltar = (): void => {
      alca.removeEventListener('pointermove', mover)
      alca.removeEventListener('pointerup', soltar)
    }
    alca.addEventListener('pointermove', mover)
    alca.addEventListener('pointerup', soltar)
  }

  return (
    <div className="player-corte" onClick={(e) => e.stopPropagation()}>
      <video
        ref={v}
        src={srcCorte}
        poster={poster}
        preload="none"
        playsInline
        style={{ objectPosition: enquadre }}
        onClick={() => (tocando ? v.current?.pause() : void play())}
        onPlay={() => setTocando(true)}
        onPause={() => setTocando(false)}
        onTimeUpdate={(e) => {
          const el = e.currentTarget
          if (el.currentTime >= fim) {
            el.pause()
            setPos(dur)
            return
          }
          if (el.currentTime < inicio - 0.5 && !el.seeking) {
            el.currentTime = inicio // escapou para antes do corte: volta ao começo dele
            return
          }
          setPos(Math.max(0, el.currentTime - inicio))
        }}
      />
      {!tocando && (
        <button className="play-grande" onClick={() => void play()} aria-label={t.tocar}>▶</button>
      )}
      <div className="controles">
        <div
          ref={barra}
          className="barra-corte"
          role="slider"
          aria-label={t.posicaoCorte}
          aria-valuemin={0}
          aria-valuemax={Math.round(dur)}
          aria-valuenow={Math.round(pos)}
          tabIndex={0}
          onPointerDown={arrastar}
          onKeyDown={(e) => {
            if (e.key === 'ArrowRight') void ir(pos + 5)
            if (e.key === 'ArrowLeft') void ir(pos - 5)
            if (e.key === 'Home') void ir(0)
          }}
        >
          <span className="preenchido" style={{ width: `${Math.min(100, (pos / dur) * 100)}%` }} />
        </div>
        <div className="linha-controles">
          <button onClick={() => (tocando ? v.current?.pause() : void play())} aria-label={tocando ? t.pausar : t.tocar}>
            {tocando ? '❚❚' : '▶'}
          </button>
          <span className="tempo">{hms(pos)} / {hms(dur)}</span>
        </div>
      </div>
    </div>
  )
}
