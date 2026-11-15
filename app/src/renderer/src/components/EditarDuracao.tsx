import { useEffect, useMemo, useRef, useState } from 'react'
import type { Api, Transcricao } from '../api'
import { useT } from '../i18n'
import {
  arrastar, arrastarEncaixado, bordasDasPalavras, janelaDePerto, lerTempo, marcas, mmss, type Modo, type Trecho
} from '../trecho'

// Tela "Editar duração" de um corte sugerido (passo 2) ou de um clip (passo 5), short ou longo: o vídeo pai em cima, tocando só o
// trecho escolhido, e embaixo a trilha do vídeo pai inteiro e a trilha de perto, com a faixa do corte.
// Arrastar as alças muda o início ou o fim; arrastar a faixa move o corte inteiro. Salvar grava o trecho
// no motor (PUT .../trecho). No clip, o motor leva junto os itens do editor e renderiza de novo se já tinha vídeo.

type Sinais = { passo: number; energia_db: number[] }
type Resposta = { job?: string | null; itens_removidos?: number; candidato?: unknown }
// O que está sendo editado: um corte sugerido (candidato) ou um clip já criado
export type AlvoDuracao = { id: string; titulo: string; inicio: number; fim: number; rotulo: string; url: string; temVideo: boolean }
type Marca = { id: string; titulo?: string; inicio: number; fim: number }

type Props = {
  api: Api
  alvo: AlvoDuracao
  video: string | null
  duracao: number // do vídeo pai
  trans: Transcricao | null
  sinais: Sinais | null
  outros: Marca[]
  voltar(): void
  aoSalvar(msg: string): void
}

const PASSO_TECLA = 0.1
const TOLERANCIA_PX = 8 // o encaixe nas palavras puxa a até 8 px da alça

export function EditarDuracao(props: Props): React.JSX.Element {
  const { api, alvo, video, duracao, trans, sinais, outros, voltar, aoSalvar } = props
  const t = useT()
  const original = useMemo<Trecho>(() => ({ inicio: alvo.inicio, fim: alvo.fim }), [alvo])
  const [sel, setSel] = useState<Trecho>(original)
  const [janela, setJanela] = useState<[number, number]>(() => janelaDePerto(original, duracao || alvo.fim))
  const [encaixe, setEncaixe] = useState(true)
  const [tempo, setTempo] = useState(alvo.inicio)
  const [tocando, setTocando] = useState(false)
  const [salvando, setSalvando] = useState(false)
  const [msg, setMsg] = useState('')
  const player = useRef<HTMLVideoElement>(null)
  const pararEm = useRef<number | null>(null) // "ouvir o começo/fim" para antes do fim do corte
  const total = duracao || Math.max(alvo.fim, trans?.duracao ?? 0)
  const bordas = useMemo(() => (trans ? bordasDasPalavras(trans.segmentos as never) : null), [trans])
  const mudou = Math.abs(sel.inicio - original.inicio) > 0.001 || Math.abs(sel.fim - original.fim) > 0.001
  const dur = sel.fim - sel.inicio
  const temVideo = alvo.temVideo

  useEffect(() => {
    if (!duracao) return
    setJanela(janelaDePerto(sel, duracao))
    // a janela só acompanha quando a duração do vídeo chega; durante o arrasto ela fica parada
  }, [duracao]) // eslint-disable-line react-hooks/exhaustive-deps

  // o player fica preso ao trecho: tocar fora dele volta para o início, chegar no fim para
  const aoTempo = (): void => {
    const v = player.current
    if (!v) return
    setTempo(v.currentTime)
    const limite = pararEm.current ?? sel.fim
    if (!v.paused && v.currentTime >= limite) {
      v.pause()
      pararEm.current = null
      if (limite >= sel.fim - 0.05) v.currentTime = sel.inicio
    }
  }
  const tocar = (de: number, ate: number | null = null): void => {
    const v = player.current
    if (!v) return
    v.currentTime = de
    pararEm.current = ate
    void v.play()
  }
  const alternar = (): void => {
    const v = player.current
    if (!v) return
    if (!v.paused) return v.pause()
    tocar(v.currentTime < sel.inicio || v.currentTime >= sel.fim - 0.05 ? sel.inicio : v.currentTime)
  }
  const mostrar = (s: number): void => {
    const v = player.current
    if (v && v.paused) v.currentTime = s
    setTempo(s)
  }

  const mudar = (novo: Trecho, modo: Modo | 'campo'): void => {
    setSel(novo)
    setMsg('')
    // mostra no vídeo o quadro da borda que está sendo arrastada
    mostrar(modo === 'fim' ? Math.max(novo.inicio, novo.fim - 0.05) : novo.inicio)
  }
  const soltar = (novo: Trecho): void => {
    // a trilha de perto se reajusta quando a faixa sai dela
    if (novo.inicio < janela[0] || novo.fim > janela[1]) setJanela(janelaDePerto(novo, total))
  }

  useEffect(() => {
    const tecla = (e: KeyboardEvent): void => {
      const alvo = e.target as HTMLElement
      if (alvo.closest('input, textarea, select, [role="slider"]')) return
      if (e.key === ' ') {
        e.preventDefault()
        alternar()
      }
    }
    window.addEventListener('keydown', tecla)
    return () => window.removeEventListener('keydown', tecla)
  })

  const salvar = async (): Promise<void> => {
    setSalvando(true)
    setMsg('…')
    try {
      const r = await api.put<Resposta>(alvo.url, { ...sel, renderizar: true })
      const partes = [r.job ? t.dur.salvoGerando : r.candidato ? t.dur.salvoCorte : t.dur.salvo]
      if (r.itens_removidos) partes.push(t.dur.itensFora(r.itens_removidos))
      aoSalvar(partes.join(' '))
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e))
      setSalvando(false)
    }
  }

  const ajustarCampo = (qual: 'inicio' | 'fim', valor: number): void => {
    const delta = valor - sel[qual]
    const novo = arrastar(qual, sel, delta, total)
    mudar(novo, qual)
    soltar(novo)
  }

  const textoDaBorda = (qual: 'inicio' | 'fim'): { antes: string; dentro: string } => {
    const pals = (trans?.segmentos ?? []).flatMap((s) => (s as { palavras?: { inicio: number; fim: number; texto: string }[] }).palavras ?? [])
    if (!pals.length) return { antes: '', dentro: '' }
    const b = qual === 'inicio' ? sel.inicio : sel.fim
    const fora = pals.filter((p) => (qual === 'inicio' ? p.fim <= b + 0.02 : p.inicio >= b - 0.02))
    const dentro = pals.filter((p) => p.inicio < sel.fim && p.fim > sel.inicio)
    if (qual === 'inicio') return { antes: fora.slice(-8).map((p) => p.texto).join(' '), dentro: dentro.slice(0, 12).map((p) => p.texto).join(' ') }
    return { antes: fora.slice(0, 8).map((p) => p.texto).join(' '), dentro: dentro.slice(-12).map((p) => p.texto).join(' ') }
  }
  const bIni = textoDaBorda('inicio')
  const bFim = textoDaBorda('fim')

  return (
    <div className="editar-duracao">
      <div className="barra-grade">
        <button onClick={voltar}>← {t.dur.voltar}</button>
        <strong className="ed-dur-titulo">✂ {t.dur.titulo}: {alvo.titulo || alvo.id}</strong>
        <span className="chip">{alvo.rotulo}</span>
        <span className="espaco" style={{ flex: 1 }} />
        <span className={`ed-dur-total ${mudou ? 'mudou' : ''}`}>
          {mmss(dur)}
          {mudou && <span className="dica"> ({t.dur.antes} {mmss(original.fim - original.inicio)}, {dur >= original.fim - original.inicio ? '+' : '−'}{mmss(Math.abs(dur - (original.fim - original.inicio)))})</span>}
        </span>
      </div>

      <div className="ed-dur-palco">
        {video ? (
          <video ref={player} className="ed-dur-video" src={api.midia(video)} preload="auto"
            onLoadedMetadata={(e) => (e.currentTarget.currentTime = sel.inicio)}
            onTimeUpdate={aoTempo} onPlay={() => setTocando(true)} onPause={() => setTocando(false)} onClick={alternar} />
        ) : (
          <div className="vazio">{t.dur.semVideo}</div>
        )}
        <div className="ed-dur-tocar">
          <button className="primario" onClick={alternar} disabled={!video}>{tocando ? `⏸ ${t.dur.pausar}` : `▶ ${t.dur.tocarCorte}`}</button>
          <button onClick={() => tocar(sel.inicio, Math.min(sel.fim, sel.inicio + 4))} disabled={!video}>{t.dur.ouvirInicio}</button>
          <button onClick={() => tocar(Math.max(sel.inicio, sel.fim - 4))} disabled={!video}>{t.dur.ouvirFim}</button>
          <span className="dica">{mmss(tempo)} / {mmss(total)}</span>
        </div>
      </div>

      <div className="ed-dur-trilhas">
        <Trilha rotulo={t.dur.videoInteiro} a={0} b={total} total={total} sel={sel} original={original} tempo={tempo} sinais={sinais}
          outros={outros} bordas={encaixe ? bordas : null} mudar={mudar} soltar={soltar} mostrar={mostrar} t={t} />
        <Trilha rotulo={t.dur.dePerto} a={janela[0]} b={janela[1]} total={total} sel={sel} original={original} tempo={tempo} sinais={sinais}
          outros={outros} bordas={encaixe ? bordas : null} mudar={mudar} soltar={soltar} mostrar={mostrar} t={t} perto />
      </div>

      <div className="ed-dur-campos">
        <CampoTempo rotulo={t.dur.inicio} valor={sel.inicio} mudar={(v) => ajustarCampo('inicio', v)} />
        <div className="ed-dur-fala">
          <span className="dica">{t.dur.comeca}</span>
          <p>{bIni.antes && <span className="fora">…{bIni.antes} </span>}<span className="dentro">{bIni.dentro}…</span></p>
        </div>
        <CampoTempo rotulo={t.dur.fim} valor={sel.fim} mudar={(v) => ajustarCampo('fim', v)} />
        <div className="ed-dur-fala">
          <span className="dica">{t.dur.termina}</span>
          <p><span className="dentro">…{bFim.dentro}</span>{bFim.antes && <span className="fora"> {bFim.antes}…</span>}</p>
        </div>
      </div>

      <div className="linha ed-dur-acoes">
        <label className="linha" title={t.dur.encaixeDica}>
          <input type="checkbox" checked={encaixe} onChange={(e) => setEncaixe(e.target.checked)} disabled={!bordas} /> {t.dur.encaixe}
        </label>
        <span className="dica">{t.dur.atalhos}</span>
        <span className="espaco" style={{ flex: 1 }} />
        <span className="dica erro-ou-msg">{msg}</span>
        <button disabled={!mudou || salvando} onClick={() => {
          setSel(original)
          soltar(original)
          mostrar(original.inicio)
        }}>{t.dur.desfazer}</button>
        <button onClick={voltar} disabled={salvando}>{t.cancelar}</button>
        <button className="primario" disabled={!mudou || salvando} onClick={() => void salvar()}
          title={temVideo ? t.dur.salvarGerarDica : undefined}>
          {temVideo ? t.dur.salvarGerar : t.salvar}
        </button>
      </div>
    </div>
  )
}

function CampoTempo(props: { rotulo: string; valor: number; mudar(v: number): void }): React.JSX.Element {
  const { rotulo, valor, mudar } = props
  const [txt, setTxt] = useState(mmss(valor))
  const [foco, setFoco] = useState(false)
  useEffect(() => {
    if (!foco) setTxt(mmss(valor))
  }, [valor, foco])
  const aplicar = (): void => {
    const v = lerTempo(txt)
    if (v === null) setTxt(mmss(valor))
    else mudar(v)
  }
  return (
    <div className="ed-dur-campo">
      <label>{rotulo}</label>
      <div className="linha">
        <button onClick={() => mudar(valor - 1)} title="−1 s">−1</button>
        <button onClick={() => mudar(valor - 0.1)} title="−0,1 s">−.1</button>
        <input value={txt} aria-label={rotulo} onFocus={() => setFoco(true)}
          onChange={(e) => setTxt(e.target.value)}
          onBlur={() => (setFoco(false), aplicar())}
          onKeyDown={(e) => e.key === 'Enter' && (e.currentTarget as HTMLInputElement).blur()} />
        <button onClick={() => mudar(valor + 0.1)} title="+0,1 s">+.1</button>
        <button onClick={() => mudar(valor + 1)} title="+1 s">+1</button>
      </div>
    </div>
  )
}

type Textos = ReturnType<typeof useT>

function Trilha(props: {
  rotulo: string
  a: number
  b: number
  total: number // duração do vídeo pai: a faixa não passa dela nem na trilha de perto
  sel: Trecho
  original: Trecho
  tempo: number
  sinais: Sinais | null
  outros: Marca[]
  bordas: ReturnType<typeof bordasDasPalavras> | null
  perto?: boolean
  mudar(t: Trecho, modo: Modo): void
  soltar(t: Trecho): void
  mostrar(s: number): void
  t: Textos
}): React.JSX.Element {
  const { rotulo, a, b, total, sel, original, tempo, sinais, outros, bordas, perto, mudar, soltar, mostrar, t } = props
  const caixa = useRef<HTMLDivElement>(null)
  const canvas = useRef<HTMLCanvasElement>(null)
  const arraste = useRef<{ modo: Modo; x0: number; orig: Trecho; seg: number; ultimo: Trecho } | null>(null)
  const span = Math.max(0.001, b - a)
  const pct = (s: number): number => ((s - a) / span) * 100

  // forma de onda da energia do áudio dentro da janela
  useEffect(() => {
    const c = canvas.current
    if (!c || !sinais?.energia_db.length) return
    const w = (c.width = Math.max(1, c.clientWidth * devicePixelRatio))
    const h = (c.height = Math.max(1, c.clientHeight * devicePixelRatio))
    const ctx = c.getContext('2d')!
    ctx.clearRect(0, 0, w, h)
    ctx.fillStyle = getComputedStyle(c).getPropertyValue('--texto-2') || '#888'
    ctx.globalAlpha = 0.5
    const n = sinais.energia_db.length
    for (let x = 0; x < w; x++) {
      const i0 = Math.max(0, Math.floor((a + (x / w) * span) / sinais.passo))
      const i1 = Math.max(i0 + 1, Math.floor((a + ((x + 1) / w) * span) / sinais.passo))
      let m = -90
      for (let i = i0; i < i1 && i < n; i++) m = Math.max(m, sinais.energia_db[i])
      const bh = Math.max(0, Math.min(1, (m + 60) / 60)) * h * 0.85
      ctx.fillRect(x, (h - bh) / 2, 1, bh)
    }
  }, [sinais, a, span])

  const comecar = (modo: Modo) => (e: React.PointerEvent): void => {
    e.stopPropagation()
    e.preventDefault()
    const w = caixa.current?.getBoundingClientRect().width ?? 1
    ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
    arraste.current = { modo, x0: e.clientX, orig: sel, seg: span / w, ultimo: sel }
  }
  const mover = (e: React.PointerEvent): void => {
    const d = arraste.current
    if (!d) return
    const novo = arrastarEncaixado(d.modo, d.orig, (e.clientX - d.x0) * d.seg, total, bordas, TOLERANCIA_PX * d.seg)
    d.ultimo = novo
    mudar(novo, d.modo)
  }
  const fim = (): void => {
    const d = arraste.current
    arraste.current = null
    if (d) soltar(d.ultimo)
  }
  const teclado = (modo: Modo) => (e: React.KeyboardEvent): void => {
    const passo = e.shiftKey ? 1 : PASSO_TECLA
    const delta = e.key === 'ArrowLeft' ? -passo : e.key === 'ArrowRight' ? passo : 0
    if (!delta) return
    e.preventDefault()
    const novo = arrastar(modo, sel, delta, total)
    mudar(novo, modo)
    soltar(novo)
  }

  const visivel = (s: number, e: number): boolean => e > a && s < b
  return (
    <div className={`ed-dur-trilha ${perto ? 'perto' : ''}`}>
      <span className="ed-dur-rotulo">{rotulo}<span className="dica"> {mmss(a)}–{mmss(b)}</span></span>
      <div ref={caixa} className="ed-dur-caixa" onPointerMove={mover} onPointerUp={fim} onPointerCancel={fim}
        onClick={(e) => {
          const r = e.currentTarget.getBoundingClientRect()
          mostrar(a + ((e.clientX - r.left) / r.width) * span)
        }}>
        <canvas ref={canvas} />
        {marcas(a, b, perto ? 10 : 8).map((m) => (
          <span key={m} className="ed-dur-marca" style={{ left: `${pct(m)}%` }}><span>{mmss(m).replace(/\.0$/, '')}</span></span>
        ))}
        {outros.filter((c) => visivel(c.inicio, c.fim)).map((c) => (
          <div key={c.id} className="ed-dur-outro" style={{ left: `${pct(c.inicio)}%`, width: `${pct(c.fim) - pct(c.inicio)}%` }} title={c.titulo || c.id} />
        ))}
        {visivel(original.inicio, original.fim) && (
          <div className="ed-dur-original" style={{ left: `${pct(original.inicio)}%`, width: `${pct(original.fim) - pct(original.inicio)}%` }}
            title={t.dur.posicaoOriginal} />
        )}
        <div className="ed-dur-faixa" style={{ left: `${pct(sel.inicio)}%`, width: `${Math.max(0.3, pct(sel.fim) - pct(sel.inicio))}%` }}
          onPointerDown={comecar('faixa')} onClick={(e) => e.stopPropagation()} title={t.dur.arrastarFaixa}>
          <span className="ed-dur-alca inicio" role="slider" tabIndex={0} aria-label={t.dur.inicio}
            aria-valuemin={0} aria-valuemax={sel.fim} aria-valuenow={sel.inicio} aria-valuetext={mmss(sel.inicio)}
            onPointerDown={comecar('inicio')} onKeyDown={teclado('inicio')} title={t.dur.arrastarInicio} />
          <span className="ed-dur-alca fim" role="slider" tabIndex={0} aria-label={t.dur.fim}
            aria-valuemin={sel.inicio} aria-valuemax={total} aria-valuenow={sel.fim} aria-valuetext={mmss(sel.fim)}
            onPointerDown={comecar('fim')} onKeyDown={teclado('fim')} title={t.dur.arrastarFim} />
        </div>
        {tempo >= a && tempo <= b && <div className="cursor" style={{ left: `${pct(tempo)}%` }} />}
      </div>
    </div>
  )
}
