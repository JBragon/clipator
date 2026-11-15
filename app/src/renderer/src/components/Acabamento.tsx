import { useEffect, useMemo, useRef, useState } from 'react'
import type { Api, Clip, Job } from '../api'
import { useT } from '../i18n'

// Acabamento do passo 5: música de fundo e ajustes de imagem em cima do clip já gerado.
// O motor aplica tudo com FFmpeg numa versão nova do clip (edicoes/<data>-acabamento/); a prévia aqui é
// feita no navegador (filtros CSS e um <audio> sincronizado com o vídeo) e por isso é aproximada.

export type Musica = { arquivo: string; volume: number; inicio: number; entrada: number; saida: number; abaixar_na_fala: boolean; repetir: boolean }
export type Imagem = { brilho: number; contraste: number; saturacao: number; temperatura: number; nitidez: number }
export type Ajustes = { musica: Musica | null; imagem: Imagem; manter_som_original: number }
type ItemMusica = { arquivo: string; nome: string; bytes?: number }
type Estado = { base: string; base_caminho: string; ajustes: Ajustes; em_uso: boolean; musicas: ItemMusica[]; pasta_musicas: string }

export const IMAGEM_NEUTRA: Imagem = { brilho: 0, contraste: 1, saturacao: 1, temperatura: 0, nitidez: 0 }
const MUSICA_PADRAO: Omit<Musica, 'arquivo'> = { volume: 0.2, inicio: 0, entrada: 1, saida: 1.5, abaixar_na_fala: true, repetir: true }
const VAZIO: Ajustes = { musica: null, imagem: IMAGEM_NEUTRA, manter_som_original: 1 }

// filtro CSS que imita o eq/unsharp do FFmpeg (o brilho do eq soma; o do CSS multiplica: fica perto o bastante)
export function filtroCss(i: Imagem, idSvg: string): string {
  const partes = [`brightness(${(1 + i.brilho * 1.4).toFixed(3)})`, `contrast(${i.contraste.toFixed(3)})`, `saturate(${i.saturacao.toFixed(3)})`]
  if (i.nitidez > 0.001) partes.push(`url(#${idSvg})`)
  return partes.join(' ')
}

// a temperatura vira uma camada laranja (quente) ou azul (frio) em "soft-light" por cima do vídeo
export function camadaTemperatura(t: number): React.CSSProperties {
  return { background: t >= 0 ? '#ff8a1f' : '#2f7bff', opacity: Math.min(0.55, Math.abs(t) * 0.55), mixBlendMode: 'soft-light' }
}

export function igual(a: Ajustes, b: Ajustes): boolean {
  return JSON.stringify(a) === JSON.stringify(b)
}

export function Acabamento(props: { api: Api; base: string; clip: Clip; jobs: Record<string, Job>; aoMudar(): void }): React.JSX.Element {
  const { api, base, clip, jobs, aoMudar } = props
  const t = useT()
  const ta = t.acab
  const url = `${base}/clips/${encodeURIComponent(clip.id)}/acabamento`
  const urlMusicas = `${base.split('/projetos/')[0]}/musicas`
  const [aberto, setAberto] = useState(false)
  const [estado, setEstado] = useState<Estado | null>(null)
  const [aj, setAj] = useState<Ajustes>(VAZIO)
  const [msg, setMsg] = useState('')
  const [jobId, setJobId] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)
  const video = useRef<HTMLVideoElement>(null)
  const audio = useRef<HTMLAudioElement>(null)
  const arquivo = useRef<HTMLInputElement>(null)
  const idSvg = `nitidez-${clip.id.replace(/[^a-zA-Z0-9_-]/g, '')}`

  const carregar = async (): Promise<void> => {
    try {
      const e = await api.get<Estado>(url)
      setEstado(e)
      setAj(e.ajustes)
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e))
    }
  }
  useEffect(() => {
    void carregar()
  }, [clip.versao]) // eslint-disable-line react-hooks/exhaustive-deps

  const job = jobId ? jobs[jobId] : undefined
  const rodando = !!job && (job.status === 'rodando' || job.status === 'na_fila')
  useEffect(() => {
    if (!job || rodando) return
    setMsg(job.status === 'erro' ? job.erro ?? t.status.erro : job.status === 'ok' ? ta.pronto : '')
    setJobId(null)
    aoMudar()
  }, [job?.status]) // eslint-disable-line react-hooks/exhaustive-deps

  const mudou = !!estado && !igual(aj, estado.ajustes)
  const temAlgo = !igual(aj, VAZIO)

  // ---- prévia: música acompanha o vídeo -------------------------------------------------
  const musica = aj.musica
  const srcMusica = useMemo(
    () => (musica && estado ? api.midia(`${estado.pasta_musicas}/${musica.arquivo}`) : ''),
    [api, estado, musica?.arquivo] // eslint-disable-line react-hooks/exhaustive-deps
  )
  const sincronizar = (): void => {
    const v = video.current
    const a = audio.current
    if (!v) return
    v.volume = Math.min(1, aj.manter_som_original)
    if (!a || !musica) return
    const d = Number.isFinite(a.duration) && a.duration > 0 ? a.duration : 0
    let alvo = v.currentTime + musica.inicio
    if (d && alvo >= d) alvo = musica.repetir ? musica.inicio + ((alvo - musica.inicio) % Math.max(0.1, d - musica.inicio)) : d
    if (Math.abs(a.currentTime - alvo) > 0.25) a.currentTime = alvo
    // fades e o "abaixar na fala" (aproximado: a música fica mais baixa o tempo todo na prévia)
    const fim = Number.isFinite(v.duration) ? v.duration : 0
    let g = musica.volume * (musica.abaixar_na_fala ? 0.6 : 1)
    if (musica.entrada > 0) g *= Math.min(1, v.currentTime / musica.entrada)
    if (musica.saida > 0 && fim) g *= Math.min(1, Math.max(0, (fim - v.currentTime) / musica.saida))
    a.volume = Math.max(0, Math.min(1, g))
    if (v.paused !== a.paused) void (v.paused ? a.pause() : a.play().catch(() => undefined))
  }
  useEffect(sincronizar) // a cada ajuste, volume e posição seguem o vídeo

  const mudarMusica = (arquivo: string): void =>
    setAj({ ...aj, musica: arquivo ? { ...(aj.musica ?? { ...MUSICA_PADRAO, arquivo }), arquivo } : null })
  const mudarM = (m: Partial<Musica>): void => setAj({ ...aj, musica: aj.musica ? { ...aj.musica, ...m } : null })
  const mudarI = (i: Partial<Imagem>): void => setAj({ ...aj, imagem: { ...aj.imagem, ...i } })

  const enviarMusica = (arq: File | undefined): void => {
    if (!arq) return
    setEnviando(true)
    setMsg(ta.enviando)
    const leitor = new FileReader()
    leitor.onload = async () => {
      try {
        const r = await api.post<ItemMusica>(urlMusicas, { nome: arq.name, arquivo: String(leitor.result) })
        const lista = await api.get<ItemMusica[]>(urlMusicas)
        setEstado((e) => (e ? { ...e, musicas: lista } : e))
        mudarMusica(r.arquivo)
        setMsg('')
      } catch (e) {
        setMsg(e instanceof Error ? e.message : String(e))
      }
      setEnviando(false)
    }
    leitor.onerror = () => (setMsg(ta.falhaLeitura), setEnviando(false))
    leitor.readAsDataURL(arq)
  }

  const aplicar = async (ajustes: Ajustes): Promise<void> => {
    try {
      video.current?.pause()
      const r = await api.post<{ job: string }>(url, ajustes)
      setJobId(r.job)
      setMsg('')
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e))
    }
  }

  const deslizante = (rotulo: string, valor: number, min: number, max: number, passo: number, mudar: (v: number) => void,
    mostrar: (v: number) => string, neutro?: number): React.JSX.Element => (
    <label className="acab-deslizante">
      <span>{rotulo}</span>
      <span className="dica">{mostrar(valor)}</span>
      <input type="range" min={min} max={max} step={passo} value={valor} onChange={(e) => mudar(Number(e.target.value))}
        onDoubleClick={() => neutro !== undefined && mudar(neutro)} />
    </label>
  )
  const pct = (v: number): string => `${Math.round(v * 100)}%`
  const sinal = (v: number): string => (v > 0 ? `+${v.toFixed(2)}` : v.toFixed(2))
  const seg = (v: number): string => `${v.toFixed(1)} s`

  return (
    <section className="acabamento">
      <div className="linha">
        <h4 style={{ margin: 0 }}>🎚 {ta.titulo}</h4>
        {estado?.em_uso && !aberto && <span className="chip" style={{ color: 'var(--ok)' }}>✓ {ta.emUso}</span>}
        <span className="espaco" style={{ flex: 1 }} />
        <button onClick={() => setAberto(!aberto)}>{aberto ? t.fechar : ta.abrir}</button>
      </div>
      {!aberto && <p className="dica" style={{ margin: 0 }}>{ta.dica}</p>}
      {aberto && estado && (
        <div className="acab-corpo">
          <div className="acab-previa">
            <svg width="0" height="0" style={{ position: 'absolute' }} aria-hidden="true">
              <filter id={idSvg}>
                <feConvolveMatrix order="3" preserveAlpha="true"
                  kernelMatrix={(() => { const k = aj.imagem.nitidez * 0.7; return `0 ${-k} 0 ${-k} ${1 + 4 * k} ${-k} 0 ${-k} 0` })()} />
              </filter>
            </svg>
            <div className="acab-quadro">
              <video ref={video} src={api.midia(estado.base_caminho)} controls playsInline
                style={{ filter: filtroCss(aj.imagem, idSvg) }}
                onPlay={sincronizar} onPause={sincronizar} onSeeked={sincronizar} onTimeUpdate={sincronizar} />
              {Math.abs(aj.imagem.temperatura) > 0.001 && <div className="acab-temperatura" style={camadaTemperatura(aj.imagem.temperatura)} />}
            </div>
            {srcMusica && <audio ref={audio} src={srcMusica} preload="auto" loop={!!musica?.repetir} />}
            <span className="dica">{ta.previaAproximada}</span>
          </div>

          <div className="acab-controles">
            <fieldset>
              <legend>🎵 {ta.musica}</legend>
              <div className="linha">
                <select value={musica?.arquivo ?? ''} onChange={(e) => mudarMusica(e.target.value)}>
                  <option value="">{ta.semMusica}</option>
                  {estado.musicas.map((m) => <option key={m.arquivo} value={m.arquivo}>{m.nome}</option>)}
                </select>
                <button disabled={enviando} onClick={() => arquivo.current?.click()}>{ta.enviarMusica}</button>
                <input ref={arquivo} type="file" accept="audio/*,.mp3,.m4a,.aac,.wav,.ogg,.opus,.flac" hidden
                  onChange={(e) => (enviarMusica(e.target.files?.[0]), (e.target.value = ''))} />
              </div>
              {!estado.musicas.length && !musica && <span className="dica">{ta.semMusicasNoCanal}</span>}
              {musica && (
                <>
                  {deslizante(ta.volume, musica.volume, 0, 1, 0.01, (v) => mudarM({ volume: v }), pct)}
                  {deslizante(ta.inicioMusica, musica.inicio, 0, 180, 0.5, (v) => mudarM({ inicio: v }), seg, 0)}
                  {deslizante(ta.entrada, musica.entrada, 0, 5, 0.1, (v) => mudarM({ entrada: v }), seg)}
                  {deslizante(ta.saida, musica.saida, 0, 5, 0.1, (v) => mudarM({ saida: v }), seg)}
                  <label className="acab-check"><input type="checkbox" checked={musica.abaixar_na_fala}
                    onChange={(e) => mudarM({ abaixar_na_fala: e.target.checked })} /> {ta.abaixarNaFala}</label>
                  <label className="acab-check"><input type="checkbox" checked={musica.repetir}
                    onChange={(e) => mudarM({ repetir: e.target.checked })} /> {ta.repetir}</label>
                </>
              )}
              {deslizante(ta.somDoClip, aj.manter_som_original, 0, 1.5, 0.05, (v) => setAj({ ...aj, manter_som_original: v }), pct, 1)}
            </fieldset>

            <fieldset>
              <legend>🎨 {ta.imagem}</legend>
              {deslizante(ta.brilho, aj.imagem.brilho, -0.3, 0.3, 0.01, (v) => mudarI({ brilho: v }), sinal, 0)}
              {deslizante(ta.contraste, aj.imagem.contraste, 0.5, 1.8, 0.01, (v) => mudarI({ contraste: v }), pct, 1)}
              {deslizante(ta.saturacao, aj.imagem.saturacao, 0, 2, 0.01, (v) => mudarI({ saturacao: v }), pct, 1)}
              {deslizante(ta.temperatura, aj.imagem.temperatura, -1, 1, 0.05, (v) => mudarI({ temperatura: v }),
                (v) => (Math.abs(v) < 0.001 ? ta.neutra : v > 0 ? `${ta.quente} ${sinal(v)}` : `${ta.frio} ${sinal(v)}`), 0)}
              {deslizante(ta.nitidez, aj.imagem.nitidez, 0, 1.5, 0.05, (v) => mudarI({ nitidez: v }), (v) => v.toFixed(2), 0)}
              <button className="link" disabled={igual({ ...aj, imagem: IMAGEM_NEUTRA }, aj)} onClick={() => mudarI(IMAGEM_NEUTRA)}>{ta.restaurarImagem}</button>
            </fieldset>

            {rodando && job && (
              <div className="render-andamento">
                <div className="linha">
                  <strong>{ta.aplicando}</strong>
                  <span className="espaco" style={{ flex: 1 }} />
                  <span>{Math.round(job.progresso * 100)}%</span>
                  <button className="link" onClick={() => void api.post(`/api/jobs/${job.id}/cancelar`)}>{t.cancelarJob}</button>
                </div>
                <div className="barra-render"><span style={{ width: `${Math.round(job.progresso * 100)}%` }} /></div>
              </div>
            )}
            <div className="linha">
              <button className="primario" disabled={rodando || !temAlgo || (!mudou && estado.em_uso)} onClick={() => void aplicar(aj)}>
                {ta.aplicar}
              </button>
              {mudou && <button className="link" disabled={rodando} onClick={() => setAj(estado.ajustes)}>{ta.descartar}</button>}
              {estado.em_uso && <button className="link" disabled={rodando} onClick={() => void aplicar(VAZIO)}>{ta.remover}</button>}
              <span className="dica">{msg}</span>
            </div>
            <span className="dica">{ta.comoFica}</span>
          </div>
        </div>
      )}
      {aberto && !estado && msg && <p className="erro-txt" style={{ margin: 0 }}>{msg}</p>}
    </section>
  )
}
