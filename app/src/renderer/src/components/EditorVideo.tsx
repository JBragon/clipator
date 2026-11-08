import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { hms, type Api, type Clip, type Job, type Transcricao } from '../api'
import { useT } from '../i18n'
import { BibliotecaStickers, PRESETS_CHAMADA, urlSticker, type Chamada, type Sticker } from './BibliotecaStickers'

// Editor de vídeo do passo 3: prévia, biblioteca de efeitos, propriedades e linha do tempo em faixas.
// O documento (edicao.json) fica no motor; aqui é editado com desfazer/refazer e salvo sozinho.
// A prévia ao vivo é uma aproximação feita no navegador (CSS); "Prévia renderizada" mostra o resultado exato.

export type ItemEd = { id: string; tipo: string; inicio: number; fim: number; params: Record<string, unknown>; origem?: string; motivo?: string }
type DocEd = { revisao: number; itens: ItemEd[]; duracao: number; tipos: Record<string, Faixa>; padrao: Record<string, [number, Record<string, unknown>]>; sons: string[] }
type Faixa = 'efeito' | 'texto' | 'sticker' | 'som' | 'cena'
type Palavra = { inicio: number; fim: number; texto: string }
type Sinais = { passo: number; energia_db: number[] }
type Quadro = { tempo: number; imagem: string }

const FAIXAS: Faixa[] = ['cena', 'efeito', 'texto', 'sticker', 'som']
// cenas da direção de arte (direcao.py): o tipo de cena e os campos que cada uma usa
const CENAS: Record<string, string[]> = {
  titulo: ['texto', 'sobre'], numero: ['valor', 'rotulo'], citacao: ['texto', 'autor'], lista: ['texto', 'itens'],
  comparacao: ['a', 'b'], linha_do_tempo: ['texto', 'itens'], local: ['texto'], nome: ['texto', 'rotulo'],
  palavra: ['texto'], alerta: ['texto']
}
const ICONES_CENA: Record<string, string> = {
  titulo: '🅣', numero: '🔢', citacao: '❝', lista: '☰', comparacao: '⚖', linha_do_tempo: '⏱', local: '📍', nome: '👤', palavra: '🅰', alerta: '⚠'
}
const resumoCena = (p: Record<string, unknown>): string =>
  String(p.texto || p.valor || (Array.isArray(p.itens) ? p.itens.join(' · ') : '') || [p.a, p.b].filter(Boolean).join(' × ') || '')
const EMOJIS = ['🔥', '😱', '😂', '💰', '🤫', '⚠️', '👀', '💥', '❤️', '✅', '❌', '🤯']
const CATEGORIAS: { id: string; tipos: string[] }[] = [
  { id: 'movimento', tipos: ['zoom', 'zoom-lento', 'tremor'] },
  { id: 'luz', tipos: ['flash', 'pb', 'sepia', 'contraste', 'saturacao', 'vinheta', 'desfoque'] },
  { id: 'transicao', tipos: ['transicao'] },
  { id: 'texto', tipos: ['texto'] },
  { id: 'stickers', tipos: ['emoji'] },
  { id: 'sons', tipos: ['som'] },
  { id: 'cenas', tipos: ['cena'] }
]
const ICONES: Record<string, string> = {
  zoom: '🔍', 'zoom-lento': '🎞', tremor: '〰', flash: '⚡', pb: '◐', sepia: '🟤', contraste: '◑', saturacao: '🎨',
  vinheta: '◎', desfoque: '💧', transicao: '⬛', texto: 'T', emoji: '😀', sticker: '🌟', som: '🔊', cena: '🎬'
}
const nomeDoRef = (ref: unknown): string => String(ref ?? '').split(/[:/]/).pop()?.replace(/\.\w+$/, '').replace(/-/g, ' ') ?? ''

// ---- tempo do clip <-> tempo do vídeo original (igual ao timeline.py do motor) ----
function trechosDo(clip: Clip): [number, number][] {
  let tr: [number, number][] = [[clip.inicio, clip.fim]]
  for (const [a0, b0] of [...clip.cortes_internos].sort((x, y) => x[0] - y[0])) {
    const a = Math.max(a0, clip.inicio)
    const b = Math.min(b0, clip.fim)
    if (b <= a) continue
    const novos: [number, number][] = []
    for (const [s, e] of tr) {
      if (b <= s || a >= e) novos.push([s, e])
      else {
        if (a > s) novos.push([s, a])
        if (b < e) novos.push([b, e])
      }
    }
    tr = novos
  }
  return tr.filter(([s, e]) => e - s >= 0.05)
}
const paraOriginal = (tr: [number, number][], t: number): number => {
  let acc = 0
  for (const [s, e] of tr) {
    if (t <= acc + (e - s)) return s + (t - acc)
    acc += e - s
  }
  return tr.length ? tr[tr.length - 1][1] : 0
}
// null quando cai num trecho cortado; aí devolve onde o próximo trecho começa (em `proximo`)
function paraClip(tr: [number, number][], t: number): { t: number | null; proximo?: number } {
  let acc = 0
  for (const [s, e] of tr) {
    if (t >= s - 0.01 && t <= e) return { t: acc + Math.max(0, t - s) }
    if (t < s) return { t: null, proximo: s }
    acc += e - s
  }
  return { t: null }
}

// efeitos ativos num instante, para a prévia ao vivo
function estadoPrevia(itens: ItemEd[], t: number): { transform: string; filter: string; flash: number; corFlash: string; vinheta: boolean; textos: ItemEd[]; emojis: ItemEd[]; stickers: ItemEd[]; cenas: ItemEd[] } {
  let z = 1
  let sx = 0
  let sy = 0
  const filtros: string[] = []
  let flash = 0
  let corFlash = 'white'
  let vinheta = false
  const textos: ItemEd[] = []
  const emojis: ItemEd[] = []
  const stickers: ItemEd[] = []
  const cenas: ItemEd[] = []
  for (const i of itens) {
    if (t < i.inicio || t > i.fim) continue
    const p = i.params as Record<string, number & string & boolean>
    const fr = (t - i.inicio) / Math.max(0.05, i.fim - i.inicio)
    switch (i.tipo) {
      case 'zoom': z += (Number(p.escala) || 1.25) - 1; break
      case 'zoom-lento': z += ((Number(p.escala) || 1.15) - 1) * fr; break
      case 'tremor': {
        const f = Number(p.forca) || 12
        z += 0.04
        sx += f * Math.sin(t * 63)
        sy += f * 0.7 * Math.cos(t * 51)
        break
      }
      case 'pb': filtros.push('grayscale(1)'); break
      case 'sepia': filtros.push('sepia(1)'); break
      case 'contraste': filtros.push(`contrast(${Number(p.valor) || 1.35})`); break
      case 'saturacao': filtros.push(`saturate(${Number(p.valor) || 1.6})`); break
      case 'desfoque': filtros.push(`blur(${(Number(p.forca) || 8) / 3}px)`); break
      case 'vinheta': vinheta = true; break
      case 'flash':
      case 'transicao':
        flash = Math.max(flash, (i.tipo === 'flash' ? 0.85 : 1) * (1 - Math.abs(fr - 0.5) * 2 * 0.45))
        corFlash = String(p.cor || (i.tipo === 'flash' ? 'white' : 'black'))
        break
      case 'texto': textos.push(i); break
      case 'emoji': emojis.push(i); break
      case 'sticker': stickers.push(i); break
      case 'cena': cenas.push(i); break
    }
  }
  return { transform: `translate(${sx.toFixed(1)}px, ${sy.toFixed(1)}px) scale(${z.toFixed(3)})`, filter: filtros.join(' ') || 'none', flash, corFlash, vinheta, textos, emojis, stickers, cenas }
}

const posicaoCss = (pos: string): React.CSSProperties => {
  const s: React.CSSProperties = { position: 'absolute' }
  if (pos.startsWith('topo')) s.top = '12%'
  else if (pos.startsWith('baixo')) s.bottom = '28%'
  else s.top = '50%'
  if (pos.endsWith('esquerda')) s.left = '5%'
  else if (pos.endsWith('direita')) s.right = '5%'
  else {
    s.left = '50%'
    s.transform = pos === 'centro' ? 'translate(-50%, -50%)' : 'translateX(-50%)'
  }
  if (pos === 'centro' && !s.transform) s.transform = 'translateY(-50%)'
  return s
}

export function EditorVideo(props: {
  api: Api
  base: string
  clip: Clip
  video: string | null
  trans: Transcricao | null
  sinais: Sinais | null
  jobs: Record<string, Job>
  voltar(): void
  aoMudar(): void
  conversar(): void
}): React.JSX.Element {
  const { api, base, clip, video, trans, sinais, jobs, voltar, aoMudar, conversar } = props
  const t = useT()
  const e = t.ed
  const url = `${base}/clips/${encodeURIComponent(clip.id)}`
  const canal = decodeURIComponent(base.split('/')[3] ?? '')
  const tr = useMemo(() => trechosDo(clip), [clip])
  const [doc, setDoc] = useState<DocEd | null>(null)
  const [itens, setItensBruto] = useState<ItemEd[]>([])
  const historico = useRef<{ antes: ItemEd[][]; depois: ItemEd[][] }>({ antes: [], depois: [] })
  const [sujo, setSujo] = useState(false)
  const [salvo, setSalvo] = useState<'ok' | 'salvando' | 'erro' | ''>('')
  const revisao = useRef(0)
  const [aviso, setAviso] = useState('')
  const [sel, setSel] = useState<string | null>(null)
  const [tempo, setTempo] = useState(0)
  const [tocando, setTocando] = useState(false)
  const [pps, setPps] = useState(40) // pixels por segundo na linha do tempo
  const [previa, setPrevia] = useState<ItemEd | null>(null) // efeito sob o mouse na biblioteca/proposta
  const [chamadas, setChamadas] = useState<Record<string, Sticker>>({}) // ref "cta:…" -> modelo (duração, textos)
  const [usaIA, setUsaIA] = useState(false) // o estilo do clip só funciona com a IA integrada
  useEffect(() => {
    api.get<{ id: string; requer_ia?: boolean }[]>('/api/estilos', { canal }).then((l) => setUsaIA(!!l.find((x) => x.id === clip.estilo)?.requer_ia), () => undefined)
  }, [api, canal, clip.estilo])
  const [zonaSegura, setZonaSegura] = useState(() => { try { return localStorage.getItem('clipator.zonaSegura') === '1' } catch { return false } })
  useEffect(() => { try { localStorage.setItem('clipator.zonaSegura', zonaSegura ? '1' : '0') } catch { /* sem armazenamento */ } }, [zonaSegura])
  const [guias, setGuias] = useState<Guia[]>([])
  useEffect(() => {
    api.get<{ stickers: Sticker[] }>('/api/stickers', { canal }).then(
      (l) => setChamadas(Object.fromEntries(l.stickers.filter((s) => s.chamada).map((s) => [s.ref, s]))), () => undefined)
  }, [api, canal])
  const [propostas, setPropostas] = useState<(ItemEd & { marcado: boolean })[] | null>(null)
  const [jobSug, setJobSug] = useState<string | null>(null)
  const [verRender, setVerRender] = useState(false)
  const [quadros, setQuadros] = useState<Quadro[]>([])
  const v = useRef<HTMLVideoElement>(null)
  const dur = doc?.duracao ?? tr.reduce((a, [s, e2]) => a + e2 - s, 0)

  // palavras no tempo do clip (para a legenda da prévia e para o encaixe na linha do tempo)
  const palavras = useMemo<Palavra[]>(() => {
    const out: Palavra[] = []
    for (const s of trans?.segmentos ?? []) {
      for (const w of (s as { palavras?: Palavra[] }).palavras ?? []) {
        const a = paraClip(tr, w.inicio).t
        if (a === null) continue
        out.push({ inicio: a, fim: a + Math.max(0.05, w.fim - w.inicio), texto: w.texto })
      }
    }
    return out
  }, [trans, tr])
  const emendas = useMemo(() => {
    const out: number[] = []
    let acc = 0
    for (const [s, e2] of tr.slice(0, -1)) {
      acc += e2 - s
      out.push(acc)
    }
    return out
  }, [tr])

  // ---- documento: carregar, salvar sozinho, recarregar quando a IA muda ----
  const carregar = useCallback(async () => {
    const d = await api.get<DocEd>(`${url}/edicao`)
    setDoc(d)
    setItensBruto(d.itens)
    revisao.current = d.revisao
    setSujo(false)
    historico.current = { antes: [], depois: [] }
  }, [api, url])
  useEffect(() => {
    void carregar()
    api.get<{ quadros: Quadro[] }>(`${url}/quadros`, { n: '16' }).then((r) => setQuadros(r.quadros), () => setQuadros([]))
  }, [carregar, api, url])

  const setItens = (novo: ItemEd[], registrar = true): void => {
    if (registrar) {
      historico.current.antes.push(itens)
      if (historico.current.antes.length > 100) historico.current.antes.shift()
      historico.current.depois = []
    }
    setItensBruto(novo)
    setSujo(true)
  }
  const desfazer = (): void => {
    const a = historico.current.antes.pop()
    if (!a) return
    historico.current.depois.push(itens)
    setItensBruto(a)
    setSujo(true)
  }
  const refazer = (): void => {
    const d = historico.current.depois.pop()
    if (!d) return
    historico.current.antes.push(itens)
    setItensBruto(d)
    setSujo(true)
  }

  useEffect(() => {
    if (!sujo) return
    const id = setTimeout(() => {
      setSalvo('salvando')
      api.put<DocEd>(`${url}/edicao`, { revisao: revisao.current, itens })
        .then((d) => {
          revisao.current = d.revisao
          setSujo(false)
          setSalvo('ok')
        }, (err) => {
          setSalvo('erro')
          setAviso(err instanceof Error ? err.message : String(err))
        })
    }, 700)
    return () => clearTimeout(id)
  }, [itens, sujo, api, url])

  useEffect(() => {
    const id = setInterval(() => {
      api.get<DocEd>(`${url}/edicao`).then((d) => {
        if (d.revisao <= revisao.current) return
        if (sujo) setAviso(e.mudouFora)
        else {
          setItensBruto(d.itens)
          revisao.current = d.revisao
          setAviso(e.recarregado)
        }
      }, () => undefined)
    }, 2500)
    return () => clearInterval(id)
  }, [api, url, sujo, e])

  // ---- reprodução: o vídeo original, pulando os cortes internos ----
  const ir = (tc: number): void => {
    const c = Math.max(0, Math.min(dur, tc))
    setTempo(c)
    if (v.current) v.current.currentTime = paraOriginal(tr, c)
  }
  useEffect(() => {
    let raf = 0
    const passo = (): void => {
      const el = v.current
      if (el && !el.paused) {
        const r = paraClip(tr, el.currentTime)
        if (r.t === null) {
          if (r.proximo !== undefined) el.currentTime = r.proximo
          else {
            el.pause()
            setTempo(dur)
          }
        } else if (r.t >= dur) {
          el.pause()
          setTempo(dur)
        } else setTempo(r.t)
      }
      raf = requestAnimationFrame(passo)
    }
    raf = requestAnimationFrame(passo)
    return () => cancelAnimationFrame(raf)
  }, [tr, dur])
  const tocar = (): void => {
    const el = v.current
    if (!el) return
    if (el.paused) {
      if (tempo >= dur - 0.05) ir(0)
      void el.play().catch(() => undefined)
    } else el.pause()
  }

  // ---- itens ----
  const selecionado = itens.find((i) => i.id === sel) ?? null
  const novoItem = (tipo: string, inicio = tempo, extra: Record<string, unknown> = {}): ItemEd => {
    let [d, p] = doc?.padrao[tipo] ?? [1, {}]
    const ch = tipo === 'sticker' ? chamadas[String(extra.ref ?? '')] : undefined
    if (ch?.chamada?.fixo) {
      // texto sem fundo (o @ do canal): entra com pop e fica parado até o fim do item
      d = ch.duracao ?? d
      p = { ...p, posicao: 'baixo', tamanho: 0.45, entrada: 'nenhuma', repetir: false, som: false }
    } else if (ch) {
      // chamada: dura a animação inteira, embaixo, grande e sem repetir
      d = ch.duracao ?? d
      p = { ...p, posicao: 'baixo', tamanho: 0.55, entrada: 'nenhuma', repetir: false, som: true }
    }
    const ini = Math.max(0, Math.min(inicio, dur - 0.1))
    return { id: Math.random().toString(36).slice(2, 10), tipo, inicio: +ini.toFixed(2), fim: +Math.min(dur, ini + d).toFixed(2), params: { ...p, ...extra }, origem: 'usuario' }
  }
  const adicionar = (tipo: string, inicio?: number, extra?: Record<string, unknown>): void => {
    const it = novoItem(tipo, inicio, extra)
    setItens([...itens, it])
    setSel(it.id)
  }
  const mudar = (id: string, m: Partial<ItemEd>, registrar = true): void =>
    setItens(itens.map((i) => (i.id === id ? { ...i, ...m, params: m.params ? { ...i.params, ...m.params } : i.params } : i)), registrar)
  const remover = (id: string): void => {
    setItens(itens.filter((i) => i.id !== id))
    setSel(null)
  }
  const dividir = (): void => {
    if (!selecionado || tempo <= selecionado.inicio + 0.05 || tempo >= selecionado.fim - 0.05) return
    const b = { ...selecionado, id: Math.random().toString(36).slice(2, 10), inicio: +tempo.toFixed(2) }
    setItens([...itens.map((i) => (i.id === selecionado.id ? { ...i, fim: +tempo.toFixed(2) } : i)), b])
  }

  // objetos que se arrastam na prévia (texto, emoji, sticker)
  const movelProps = {
    sel, zona: zonaSegura ? zonaDoFormato(...((clip.formato || '9:16').split(':').map(Number) as [number, number])) : null, setGuias,
    selecionar: (id: string) => setSel(id),
    mudar: (id: string, params: Record<string, unknown>, registrar: boolean) => mudar(id, { params }, registrar)
  }
  const empurrar = (dx: number, dy: number): boolean => {
    const it = itens.find((i) => i.id === sel)
    if (!it || !MOVEIS.includes(it.tipo) || tempo < it.inicio || tempo >= it.fim) return false
    const c = centroNaTela(it.id)
    if (!c) return false
    mudar(it.id, { params: { x: +Math.min(1, Math.max(0, c.x + dx)).toFixed(4), y: +Math.min(1, Math.max(0, c.y + dy)).toFixed(4) } })
    return true
  }

  // ---- atalhos ----
  useEffect(() => {
    const tecla = (ev: KeyboardEvent): void => {
      const alvo = ev.target as HTMLElement | null
      if (alvo?.closest?.('input, textarea, select, [contenteditable=true], .conversa-ia')) return
      const k = ev.key.toLowerCase()
      if (ev.ctrlKey || ev.metaKey) {
        if (k === 'z' && !ev.shiftKey) desfazer()
        else if (k === 'y' || (k === 'z' && ev.shiftKey)) refazer()
        else return
        ev.preventDefault()
        return
      }
      if (k === ' ' || k === 'k') {
        if (k === 'k') v.current?.pause()
        else tocar()
      } else if (k === 'j') ir(tempo - 2)
      else if (k === 'l') {
        if (v.current?.paused) tocar()
        else ir(tempo + 2)
      } else if (k === 's') dividir()
      else if ((k === 'delete' || k === 'backspace') && sel) remover(sel)
      else if (k.startsWith('arrow') && empurrar(...(({ arrowleft: [-1, 0], arrowright: [1, 0], arrowup: [0, -1], arrowdown: [0, 1] } as Record<string, [number, number]>)[k] ?? [0, 0]).map((d) => d * (ev.shiftKey ? 0.05 : 0.005)) as [number, number])) { /* objeto selecionado andou */ }
      else if (k === 'arrowleft') ir(tempo - (ev.shiftKey ? 1 : 1 / 30))
      else if (k === 'arrowright') ir(tempo + (ev.shiftKey ? 1 : 1 / 30))
      else if (k === 'escape') setSel(null)
      else return
      ev.preventDefault()
    }
    window.addEventListener('keydown', tecla)
    return () => window.removeEventListener('keydown', tecla)
  })

  // ---- sugestões (IA pelo adaptador, ou regras simples) ----
  const sugerir = async (usarIa: boolean): Promise<void> => {
    setAviso('')
    const r = await api.post<{ job: string }>(`${url}/edicao/sugerir`, {}, { usar_ia: String(usarIa) })
    setJobSug(r.job)
  }
  useEffect(() => {
    if (!jobSug) return
    const j = jobs[jobSug]
    if (!j || (j.status !== 'ok' && j.status !== 'erro' && j.status !== 'cancelado')) return
    setJobSug(null)
    if (j.status !== 'ok') return setAviso(j.erro || e.sugestaoFalhou)
    const r = (j.resultado ?? {}) as { propostas?: ItemEd[]; aviso?: string; fonte?: string }
    setPropostas((r.propostas ?? []).map((p) => ({ ...p, marcado: true })))
    if (r.aviso) setAviso(r.aviso.length > 220 ? `${r.aviso.slice(0, 220)}…` : r.aviso)
  }, [jobs, jobSug, e])
  const aceitar = (todas: boolean): void => {
    if (!propostas) return
    const novos = propostas.filter((p) => todas || p.marcado).map(({ marcado: _m, ...p }) => ({ ...p, id: Math.random().toString(36).slice(2, 10) }))
    setItens([...itens, ...novos])
    setPropostas(null)
    setPrevia(null)
  }

  // ---- render ----
  const renderJob = Object.values(jobs).find((j) => j.tipo === 'renderizar' && (j.status === 'rodando' || j.status === 'na_fila') && (j.params.clips as string[] | undefined)?.includes(clip.id))
  const renderizar = async (preview: boolean): Promise<void> => {
    if (sujo) {
      const d = await api.put<DocEd>(`${url}/edicao`, { revisao: revisao.current, itens })
      revisao.current = d.revisao
      setSujo(false)
    }
    await api.post(`${base}/renderizar`, { clips: [clip.id], preview })
    if (preview) setVerRender(true)
  }
  const ultimoRender = useRef('')
  useEffect(() => {
    const fim = Object.values(jobs).filter((j) => j.tipo === 'renderizar' && j.status === 'ok' && (j.params.clips as string[] | undefined)?.includes(clip.id))
      .sort((a, b) => (b.terminado ?? 0) - (a.terminado ?? 0))[0]
    if (fim && fim.id !== ultimoRender.current) {
      if (ultimoRender.current) aoMudar()
      ultimoRender.current = fim.id
    }
  }, [jobs, clip.id, aoMudar])

  const itensPrevia = previa ? [...itens, previa] : propostas ? [...itens, ...propostas.filter((p) => p.marcado)] : itens
  const est = estadoPrevia(itensPrevia, tempo)
  const legenda = palavras.filter((w) => w.inicio <= tempo + 0.6 && w.fim >= tempo - 0.6).map((w) => w.texto).join(' ')
  const [fw, fh] = (clip.formato || '9:16').split(':').map(Number)
  const renderPrevia = clip.preview ? `${clip.pasta}/preview.mp4` : null
  const renderFinal = clip.versao ? `${clip.pasta}/${clip.versao}` : clip.saida ? `${clip.pasta}/saida.mp4` : null

  return (
    <div className="editor-video">
      <div className="editor-barra">
        <button onClick={voltar}>← {e.voltar}</button>
        <strong className="editor-titulo" title={clip.titulo}>{clip.titulo || clip.id}</strong>
        <span className="dica">{clip.formato} · {hms(dur)}</span>
        <span className="espaco" style={{ flex: 1 }} />
        <button onClick={desfazer} disabled={!historico.current.antes.length} title={`${e.desfazer} (Ctrl+Z)`}>↶</button>
        <button onClick={refazer} disabled={!historico.current.depois.length} title={`${e.refazer} (Ctrl+Y)`}>↷</button>
        <span className="dica salvo">{salvo === 'salvando' ? e.salvando : salvo === 'erro' ? e.naoSalvou : sujo ? '•' : salvo === 'ok' ? e.salvo : ''}</span>
        {usaIA && <span className="chip usa-ia" title={t.usaIADica}>🤖 {t.usaIA}</span>}
        <button onClick={() => void sugerir(true)} disabled={!!jobSug} className="primario">✨ {jobSug ? e.pensando : e.efeitosIA}</button>
        <button onClick={() => void sugerir(false)} disabled={!!jobSug} title={e.semIADica}>{e.semIA}</button>
        <button onClick={conversar} title={e.conversarDica}>💬 {e.conversar}</button>
        <button onClick={() => void renderizar(true)} disabled={!!renderJob}>{e.previaRenderizada}</button>
        <button onClick={() => void renderizar(false)} disabled={!!renderJob} className="primario">{renderJob ? `${Math.round(renderJob.progresso * 100)}%` : e.renderizar}</button>
      </div>
      {aviso && <div className="editor-aviso">{aviso}{aviso === e.mudouFora && <button className="link" onClick={() => void carregar()}>{e.recarregar}</button>}</div>}

      <div className="editor-meio">
        <aside className="editor-biblioteca">
          <h4>{e.efeitos}</h4>
          {CATEGORIAS.map((c) => (
            <div key={c.id} className="categoria">
              <div className="dica">{e.categorias[c.id as keyof typeof e.categorias]}</div>
              <div className="grade-efeitos">
                {c.id === 'stickers' ? (
                  <BibliotecaStickers api={api} canal={canal} jobs={jobs} adicionar={(ref) => adicionar('sticker', undefined, { ref })}
                    previa={(ref) => setPrevia(ref ? novoItem('sticker', tempo, { ref }) : null)} />
                ) : null}
                {c.id === 'stickers' && <div className="dica" style={{ flexBasis: '100%' }}>{e.emojiSimples}</div>}
                {c.id === 'stickers' ? EMOJIS.map((em) => (
                  <button key={em} className="efeito-btn" draggable title={e.adicionarNoPlayhead}
                    onDragStart={(ev) => ev.dataTransfer.setData('text/x-efeito', JSON.stringify({ tipo: 'emoji', extra: { emoji: em } }))}
                    onMouseEnter={() => setPrevia(novoItem('emoji', tempo, { emoji: em }))} onMouseLeave={() => setPrevia(null)}
                    onClick={() => adicionar('emoji', undefined, { emoji: em })}>{em}</button>
                )) : c.id === 'cenas' ? Object.keys(CENAS).map((cn) => (
                  <button key={cn} className="efeito-btn largo" draggable title={e.adicionarNoPlayhead}
                    onDragStart={(ev) => ev.dataTransfer.setData('text/x-efeito', JSON.stringify({ tipo: 'cena', extra: { cena: cn, texto: e.cenas[cn as keyof typeof e.cenas] } }))}
                    onClick={() => adicionar('cena', undefined, { cena: cn, texto: e.cenas[cn as keyof typeof e.cenas] })}>
                    {ICONES_CENA[cn]} {e.cenas[cn as keyof typeof e.cenas]}
                  </button>
                )) : c.id === 'sons' ? (doc?.sons ?? []).map((s) => (
                  <button key={s} className="efeito-btn largo" draggable title={e.adicionarNoPlayhead}
                    onDragStart={(ev) => ev.dataTransfer.setData('text/x-efeito', JSON.stringify({ tipo: 'som', extra: { nome: s } }))}
                    onClick={() => adicionar('som', undefined, { nome: s })}>🔊 {s}</button>
                )) : c.tipos.map((tp) => (
                  <button key={tp} className="efeito-btn largo" draggable title={e.adicionarNoPlayhead}
                    onDragStart={(ev) => ev.dataTransfer.setData('text/x-efeito', JSON.stringify({ tipo: tp }))}
                    onMouseEnter={() => setPrevia(novoItem(tp))} onMouseLeave={() => setPrevia(null)}
                    onClick={() => adicionar(tp)}>{ICONES[tp]} {e.tipos[tp as keyof typeof e.tipos] ?? tp}</button>
                ))}
              </div>
            </div>
          ))}
        </aside>

        <div className="editor-previa">
          <div className="tela" style={{ aspectRatio: `${fw} / ${fh}` }}>
            {verRender && (renderPrevia || renderFinal) ? (
              <video key="render" src={api.midia(renderPrevia || renderFinal || '', String(Date.now() >> 14))} controls autoPlay className="render" />
            ) : (
              <>
                <div className="camada-video" style={{ transform: est.transform, filter: est.filter }}>
                  {video && <video ref={v} src={api.midia(video)} preload="auto" playsInline onClick={tocar}
                    onLoadedMetadata={() => ir(tempo)} onPlay={() => setTocando(true)} onPause={() => setTocando(false)} />}
                </div>
                {est.vinheta && <div className="vinheta" />}
                {est.flash > 0 && <div className="flash" style={{ opacity: est.flash, background: est.corFlash }} />}
                {zonaSegura && <div className="zona-segura" style={zonaCss(zonaDoFormato(fw, fh))} />}
                {est.cenas.map((i) => (
                  <div key={i.id} className={`cena-previa${sel === i.id ? ' sel' : ''}`} onClick={() => setSel(i.id)} title={e.cenaPreviaDica}>
                    <span className="tipo">{ICONES_CENA[String(i.params.cena)] ?? '🎬'} {e.cenas[String(i.params.cena) as keyof typeof e.cenas] ?? String(i.params.cena)}</span>
                    <span className="txt">{resumoCena(i.params)}</span>
                  </div>
                ))}
                {est.textos.map((i) => (
                  <Movel key={i.id} item={i} {...movelProps}>
                    <div className={`texto-previa ${i.params.fundo ? 'com-fundo' : ''}`}
                      style={{ color: String(i.params.cor), fontSize: `${(Number(i.params.tamanho) || 0.07) * 100}cqh` }}>
                      {String(i.params.texto)}
                    </div>
                  </Movel>
                ))}
                {est.emojis.map((i) => (
                  <Movel key={i.id} item={i} {...movelProps}>
                    <div className="emoji-previa" style={{ fontSize: `${(Number(i.params.tamanho) || 0.18) * 100}cqw` }}>{String(i.params.emoji)}</div>
                  </Movel>
                ))}
                {est.stickers.map((i) => {
                  const fr = Math.min(1, (tempo - i.inicio) / 0.3)
                  const ent = String(i.params.entrada)
                  const extra = ent === 'deslizar' ? ` translateX(${((1 - fr) * 60).toFixed(1)}cqw)` : ent === 'pop' ? ` translateY(${(-4 * Math.sin(Math.PI * fr)).toFixed(1)}cqh)` : ''
                  return (
                    <Movel key={i.id} item={i} {...movelProps} largura={`${(Number(i.params.tamanho) || 0.28) * 100}cqw`} extra={extra}
                      opacidade={ent === 'nenhuma' ? 1 : Math.min(1, (tempo - i.inicio) / 0.25)}>
                      <ImgSticker className="sticker-previa" src={(n) => urlSticker(api, String(i.params.ref), canal, i.params, n)}
                        t={String(i.params.ref).startsWith('cta:') ? tempo - i.inicio : undefined} repetir={!!i.params.repetir}
                        segurar={!!chamadas[String(i.params.ref)]?.chamada?.fixo}
                        esticar={Number(i.params.esticar) || 1} style={{ width: '100%' }} />
                    </Movel>
                  )
                })}
                {guias.map((g, k) => <div key={k} className={`guia guia-${g.dir}`} style={g.dir === 'v' ? { left: `${g.pos * 100}%` } : { top: `${g.pos * 100}%` }} />)}
                {legenda && <div className="legenda-previa">{legenda}</div>}
              </>
            )}
          </div>
          <div className="linha controles-previa">
            <button onClick={tocar} disabled={verRender}>{tocando ? '❚❚' : '▶'}</button>
            <span className="tempo">{hms(tempo)}.{String(Math.floor((tempo % 1) * 10))} / {hms(dur)}</span>
            <span className="espaco" style={{ flex: 1 }} />
            <label className="linha dica" title={e.zonaSeguraDica}>
              <input type="checkbox" checked={zonaSegura} onChange={(ev) => setZonaSegura(ev.target.checked)} /> {e.zonaSegura}
            </label>
            <label className="linha dica">
              <input type="checkbox" checked={verRender} disabled={!renderPrevia && !renderFinal} onChange={(ev) => setVerRender(ev.target.checked)} />
              {e.verRender}
            </label>
          </div>
          {!verRender && <p className="dica aproximado">{e.aproximado}</p>}
        </div>

        <aside className="editor-propriedades">
          {propostas ? (
            <Propostas propostas={propostas} setPropostas={setPropostas} aceitar={aceitar} setPrevia={setPrevia} ir={ir} />
          ) : selecionado ? (
            <Propriedades api={api} canal={canal} it={selecionado} dur={dur} sons={doc?.sons ?? []} chamada={chamadas[String(selecionado.params.ref ?? '')]?.chamada}
              mudar={(m, r) => mudar(selecionado.id, m, r)} remover={() => remover(selecionado.id)} dividir={dividir} ir={ir} />
          ) : (
            <div className="dica" style={{ padding: 8 }}>{e.semSelecao}</div>
          )}
        </aside>
      </div>

      <LinhaDoTempo itens={itens} sel={sel} setSel={setSel} tempo={tempo} ir={ir} dur={dur} pps={pps} setPps={setPps}
        palavras={palavras} emendas={emendas} quadros={quadros} midia={(c) => api.midia(c)} sinais={sinais} tr={tr}
        mudar={mudar} soltar={(tipo, t0, extra) => adicionar(tipo, t0, extra)} tipos={doc?.tipos ?? {}} />
    </div>
  )
}

function Propriedades(props: { api: Api; canal: string; it: ItemEd; dur: number; sons: string[]; chamada?: Chamada; mudar(m: Partial<ItemEd>, registrar?: boolean): void; remover(): void; dividir(): void; ir(t: number): void }): React.JSX.Element {
  const { api, canal, it, dur, sons, chamada, mudar, remover, dividir, ir } = props
  const t = useT()
  const e = t.ed
  const p = it.params
  const num = (k: string, min: number, max: number, passo: number): React.JSX.Element => (
    <label className="campo">
      {e.params[k as keyof typeof e.params] ?? k}: <strong>{Number(p[k] ?? 0).toFixed(passo < 1 ? 2 : 0)}</strong>
      <input type="range" min={min} max={max} step={passo} value={Number(p[k] ?? min)} onChange={(ev) => mudar({ params: { [k]: Number(ev.target.value) } })} />
    </label>
  )
  const posicao = (
    <label className="campo">{e.params.posicao}
      <select value={String(p.posicao)} onChange={(ev) => mudar({ params: { posicao: ev.target.value } })}>
        {['topo', 'centro', 'baixo', 'topo-esquerda', 'topo-direita', 'baixo-esquerda', 'baixo-direita'].map((x) => <option key={x} value={x}>{e.posicoes[x as keyof typeof e.posicoes]}</option>)}
      </select>
    </label>
  )
  return (
    <div className="props">
      <div className="linha"><strong>{ICONES[it.tipo]} {e.tipos[it.tipo as keyof typeof e.tipos] ?? it.tipo}</strong>{it.origem && it.origem !== 'usuario' && <span className="chip">{it.origem === 'ia' ? 'IA' : e.regras}</span>}</div>
      {it.motivo && <p className="dica" style={{ margin: 0 }}>{it.motivo}</p>}
      <div className="linha">
        <label className="campo">{e.inicio}<input type="number" step={0.05} min={0} max={dur} value={it.inicio} onChange={(ev) => mudar({ inicio: Math.max(0, Math.min(Number(ev.target.value), it.fim - 0.05)) })} /></label>
        <label className="campo">{e.fim}<input type="number" step={0.05} min={0} max={dur} value={it.fim} onChange={(ev) => mudar({ fim: Math.min(dur, Math.max(Number(ev.target.value), it.inicio + 0.05)) })} /></label>
      </div>
      {(it.tipo === 'zoom' || it.tipo === 'zoom-lento') && num('escala', 1.02, 1.8, 0.01)}
      {(it.tipo === 'tremor' || it.tipo === 'desfoque') && num('forca', it.tipo === 'tremor' ? 2 : 1, it.tipo === 'tremor' ? 40 : 30, 1)}
      {(it.tipo === 'contraste' || it.tipo === 'saturacao') && num('valor', 0.2, 3, 0.05)}
      {(it.tipo === 'flash' || it.tipo === 'transicao') && (
        <label className="campo">{e.params.cor}<input type="color" value={String(p.cor).startsWith('#') ? String(p.cor) : p.cor === 'black' ? '#000000' : '#ffffff'} onChange={(ev) => mudar({ params: { cor: ev.target.value } })} /></label>
      )}
      {it.tipo === 'texto' && (
        <>
          <label className="campo">{e.params.texto}<textarea rows={2} value={String(p.texto)} onChange={(ev) => mudar({ params: { texto: ev.target.value } })} /></label>
          {posicao}
          {num('tamanho', 0.02, 0.2, 0.005)}
          <div className="linha">
            <label className="campo">{e.params.cor}<input type="color" value={String(p.cor).startsWith('#') ? String(p.cor) : '#ffffff'} onChange={(ev) => mudar({ params: { cor: ev.target.value } })} /></label>
            <label className="linha"><input type="checkbox" checked={!!p.fundo} onChange={(ev) => mudar({ params: { fundo: ev.target.checked } })} /> {e.params.fundo}</label>
          </div>
        </>
      )}
      {it.tipo === 'emoji' && (
        <>
          <label className="campo">{e.params.emoji}<input value={String(p.emoji)} maxLength={8} onChange={(ev) => mudar({ params: { emoji: ev.target.value } })} /></label>
          {posicao}
          {num('tamanho', 0.05, 0.5, 0.01)}
        </>
      )}
      {it.tipo === 'sticker' && (
        <>
          <div className="linha"><span className="dica">{nomeDoRef(p.ref)}</span></div>
          {chamada && <CamposChamada p={p} chamada={chamada} mudar={mudar} />}
          {chamada?.fixo && <FormatoTexto api={api} canal={canal} p={p} mudar={mudar} />}
          {posicao}
          {num('tamanho', 0.05, 0.8, 0.01)}
          {num('rotacao', -180, 180, 1)}
          <label className="campo">{e.params.entrada}
            <select value={String(p.entrada)} onChange={(ev) => mudar({ params: { entrada: ev.target.value } })}>
              {(['nenhuma', 'pop', 'fade', 'deslizar'] as const).map((x) => <option key={x} value={x}>{e.entradas[x]}</option>)}
            </select>
          </label>
          <label className="linha"><input type="checkbox" checked={!!p.repetir} onChange={(ev) => mudar({ params: { repetir: ev.target.checked } })} /> {e.params.repetir}</label>
        </>
      )}
      {it.tipo === 'cena' && (
        <>
          <label className="campo">{e.tipoCena}
            <select value={String(p.cena)} onChange={(ev) => mudar({ params: { cena: ev.target.value } })}>
              {Object.keys(CENAS).map((cn) => <option key={cn} value={cn}>{ICONES_CENA[cn]} {e.cenas[cn as keyof typeof e.cenas]}</option>)}
            </select>
          </label>
          {(CENAS[String(p.cena)] ?? ['texto']).map((campo) => campo === 'itens' ? (
            <label key={campo} className="campo">{e.camposCena.itens}
              <textarea rows={4} value={(Array.isArray(p.itens) ? p.itens : []).join('\n')}
                onChange={(ev) => mudar({ params: { itens: ev.target.value.split('\n') } })} />
            </label>
          ) : (
            <label key={campo} className="campo">{e.camposCena[campo as keyof typeof e.camposCena] ?? campo}
              <input value={String(p[campo] ?? '')} maxLength={campo === 'texto' ? 90 : 60} onChange={(ev) => mudar({ params: { [campo]: ev.target.value } })} />
            </label>
          ))}
          {typeof p.ancora === 'string' && p.ancora && <p className="dica" style={{ margin: 0 }}>{e.ancoraCena}: “{String(p.ancora)}”</p>}
        </>
      )}
      {it.tipo === 'som' && (
        <>
          <label className="campo">{e.params.nome}
            <select value={String(p.nome)} onChange={(ev) => mudar({ params: { nome: ev.target.value } })}>
              {[...new Set([String(p.nome), ...sons])].map((s) => <option key={s}>{s}</option>)}
            </select>
          </label>
          {num('volume', 0, 2, 0.05)}
        </>
      )}
      <div className="linha" style={{ flexWrap: 'wrap' }}>
        <button onClick={() => ir(it.inicio)}>▶ {e.irPara}</button>
        <button onClick={dividir} title="S">✂ {e.dividir}</button>
        <button onClick={remover} title="Del">🗑 {e.remover}</button>
      </div>
    </div>
  )
}

function Propostas(props: {
  propostas: (ItemEd & { marcado: boolean })[]
  setPropostas(p: (ItemEd & { marcado: boolean })[] | null): void
  aceitar(todas: boolean): void
  setPrevia(i: ItemEd | null): void
  ir(t: number): void
}): React.JSX.Element {
  const { propostas, setPropostas, aceitar, setPrevia, ir } = props
  const t = useT()
  const e = t.ed
  return (
    <div className="props propostas">
      <strong>✨ {e.propostas(propostas.length)}</strong>
      {!propostas.length && <p className="dica">{e.semPropostas}</p>}
      <div className="lista-propostas">
        {propostas.map((p, k) => (
          <label key={k} className="proposta" onMouseEnter={() => {
            setPrevia(p)
            ir(p.inicio)
          }} onMouseLeave={() => setPrevia(null)}>
            <input type="checkbox" checked={p.marcado} onChange={(ev) => setPropostas(propostas.map((x, j) => (j === k ? { ...x, marcado: ev.target.checked } : x)))} />
            <span>{ICONES[p.tipo]} <strong>{e.tipos[p.tipo as keyof typeof e.tipos] ?? p.tipo}</strong> {hms(p.inicio)}
              {p.tipo === 'texto' && ` “${String(p.params.texto)}”`}{p.tipo === 'emoji' && ` ${String(p.params.emoji)}`}{p.tipo === 'sticker' && ` ${nomeDoRef(p.params.ref)}`}{p.tipo === 'som' && ` ${String(p.params.nome)}`}
              {p.motivo && <span className="dica"> — {p.motivo}</span>}
            </span>
          </label>
        ))}
      </div>
      <div className="linha" style={{ flexWrap: 'wrap' }}>
        <button className="primario" disabled={!propostas.some((p) => p.marcado)} onClick={() => aceitar(false)}>{e.aceitarMarcadas}</button>
        <button onClick={() => aceitar(true)} disabled={!propostas.length}>{e.aceitarTodas}</button>
        <button className="link" onClick={() => {
          setPropostas(null)
          setPrevia(null)
        }}>{e.descartar}</button>
      </div>
    </div>
  )
}

function LinhaDoTempo(props: {
  itens: ItemEd[]
  sel: string | null
  setSel(id: string | null): void
  tempo: number
  ir(t: number): void
  dur: number
  pps: number
  setPps(n: number): void
  palavras: Palavra[]
  emendas: number[]
  quadros: Quadro[]
  midia(c: string): string
  sinais: Sinais | null
  tr: [number, number][]
  mudar(id: string, m: Partial<ItemEd>, registrar?: boolean): void
  soltar(tipo: string, t: number, extra?: Record<string, unknown>): void
  tipos: Record<string, Faixa>
}): React.JSX.Element {
  const { itens, sel, setSel, tempo, ir, dur, pps, setPps, palavras, emendas, quadros, midia, sinais, tr, mudar, soltar, tipos } = props
  const t = useT()
  const e = t.ed
  const area = useRef<HTMLDivElement>(null)
  const largura = Math.max(1, dur * pps)
  const ROTULO = 92 // largura da coluna com o nome das faixas

  // pontos de encaixe: palavras, emendas, playhead e bordas dos outros itens
  const encaixes = useMemo(() => [0, dur, ...emendas, ...palavras.flatMap((w) => [w.inicio, w.fim])], [dur, emendas, palavras])
  const encaixar = (x: number, ignorar: string): number => {
    const pontos = [...encaixes, tempo, ...itens.filter((i) => i.id !== ignorar).flatMap((i) => [i.inicio, i.fim])]
    let melhor = x
    let dist = 7 / pps
    for (const p of pontos) {
      if (Math.abs(p - x) < dist) {
        dist = Math.abs(p - x)
        melhor = p
      }
    }
    return melhor
  }
  const tempoDoMouse = (clientX: number): number => {
    const r = area.current?.getBoundingClientRect()
    if (!r) return 0
    return Math.max(0, Math.min(dur, (clientX - r.left - ROTULO + (area.current?.scrollLeft ?? 0)) / pps))
  }

  // arrastar: mover o item inteiro ou uma das bordas (registra no desfazer só quando solta)
  const arrastar = (ev: React.PointerEvent, it: ItemEd, modo: 'mover' | 'ini' | 'fim'): void => {
    ev.stopPropagation()
    ev.preventDefault()
    setSel(it.id)
    const x0 = ev.clientX
    const orig = { ...it }
    let primeiro = true
    const mover = (e2: PointerEvent): void => {
      const d = (e2.clientX - x0) / pps
      let m: Partial<ItemEd>
      if (modo === 'mover') {
        const len = orig.fim - orig.inicio
        let ini = encaixar(Math.max(0, Math.min(dur - len, orig.inicio + d)), it.id)
        if (Math.abs(ini - (orig.inicio + d)) > 7 / pps) ini = orig.inicio + d
        const fimEnc = encaixar(ini + len, it.id)
        if (fimEnc !== ini + len) ini = fimEnc - len
        ini = Math.max(0, Math.min(dur - len, ini))
        m = { inicio: +ini.toFixed(3), fim: +(ini + len).toFixed(3) }
      } else if (modo === 'ini') m = { inicio: +Math.max(0, Math.min(orig.fim - 0.05, encaixar(orig.inicio + d, it.id))).toFixed(3) }
      else m = { fim: +Math.min(dur, Math.max(orig.inicio + 0.05, encaixar(orig.fim + d, it.id))).toFixed(3) }
      mudar(it.id, m, primeiro)
      primeiro = false
    }
    const soltarPonteiro = (): void => {
      window.removeEventListener('pointermove', mover)
      window.removeEventListener('pointerup', soltarPonteiro)
    }
    window.addEventListener('pointermove', mover)
    window.addEventListener('pointerup', soltarPonteiro)
  }
  const arrastarCabeca = (ev: React.PointerEvent): void => {
    ir(tempoDoMouse(ev.clientX))
    const mover = (e2: PointerEvent): void => ir(tempoDoMouse(e2.clientX))
    const fim = (): void => {
      window.removeEventListener('pointermove', mover)
      window.removeEventListener('pointerup', fim)
    }
    window.addEventListener('pointermove', mover)
    window.addEventListener('pointerup', fim)
  }

  // forma de onda: energia (dBFS) do áudio do original, levada para o tempo do clip
  const onda = useMemo(() => {
    if (!sinais?.energia_db?.length) return []
    const out: { x: number; h: number }[] = []
    const passo = Math.max(0.1, 2 / pps)
    for (let tc = 0; tc < dur; tc += passo) {
      const orig = paraOriginal(tr, tc)
      const db = sinais.energia_db[Math.floor(orig / sinais.passo)] ?? -60
      out.push({ x: tc * pps, h: Math.max(2, Math.min(1, (db + 50) / 45) * 30) })
    }
    return out
  }, [sinais, tr, dur, pps])

  const marcas: number[] = []
  const passoMarca = pps > 80 ? 1 : pps > 30 ? 2 : pps > 12 ? 5 : 10
  for (let s = 0; s <= dur; s += passoMarca) marcas.push(s)

  return (
    <div className="linha-tempo">
      <div className="linha lt-topo">
        <span className="dica">{e.linhaDoTempo}</span>
        <span className="espaco" style={{ flex: 1 }} />
        <span className="dica">{e.atalhos}</span>
        <label className="linha dica">🔍<input type="range" min={8} max={200} value={pps} onChange={(ev) => setPps(Number(ev.target.value))} /></label>
      </div>
      <div className="lt-area" ref={area}
        onDragOver={(ev) => ev.preventDefault()}
        onDrop={(ev) => {
          const d = ev.dataTransfer.getData('text/x-efeito')
          if (!d) return
          ev.preventDefault()
          const { tipo, extra } = JSON.parse(d) as { tipo: string; extra?: Record<string, unknown> }
          soltar(tipo, tempoDoMouse(ev.clientX), extra)
        }}>
        <div className="lt-conteudo" style={{ width: largura + ROTULO + 40 }}>
          <div className="lt-regua" style={{ marginLeft: ROTULO }} onPointerDown={arrastarCabeca}>
            {marcas.map((s) => <span key={s} style={{ left: s * pps }}>{hms(s)}</span>)}
          </div>
          <div className="lt-faixa">
            <div className="lt-rotulo">🎬 {e.faixas.video}</div>
            <div className="lt-trilha video" style={{ width: largura }} onPointerDown={arrastarCabeca}>
              {quadros.map((q) => <img key={q.tempo} src={midia(q.imagem)} style={{ left: q.tempo * pps - 34 }} alt="" draggable={false} />)}
              {emendas.map((x) => <i key={x} className="emenda" style={{ left: x * pps }} title={e.emenda} />)}
            </div>
          </div>
          <div className="lt-faixa">
            <div className="lt-rotulo">🎵 {e.faixas.audio}</div>
            <div className="lt-trilha audio" style={{ width: largura }} onPointerDown={arrastarCabeca}>
              {onda.map((b, k) => <i key={k} style={{ left: b.x, height: b.h }} />)}
            </div>
          </div>
          <div className="lt-faixa">
            <div className="lt-rotulo">💬 {e.faixas.legenda}</div>
            <div className="lt-trilha legenda" style={{ width: largura }} onPointerDown={arrastarCabeca}>
              {palavras.map((w, k) => <span key={k} style={{ left: w.inicio * pps, width: Math.max(2, (w.fim - w.inicio) * pps) }} title={w.texto}>{pps > 50 ? w.texto : ''}</span>)}
            </div>
          </div>
          {FAIXAS.map((f) => (
            <div key={f} className="lt-faixa">
              <div className="lt-rotulo">{f === 'cena' ? '🎬' : f === 'efeito' ? '✨' : f === 'texto' ? 'T' : f === 'sticker' ? '😀' : '🔊'} {e.faixas[f]}</div>
              <div className="lt-trilha itens" style={{ width: largura }} onPointerDown={(ev) => {
                setSel(null)
                arrastarCabeca(ev)
              }}>
                {itens.filter((i) => (tipos[i.tipo] ?? 'efeito') === f).map((i) => (
                  <div key={i.id} className={`lt-item ${f} ${sel === i.id ? 'sel' : ''} ${i.origem === 'ia' ? 'ia' : ''}`}
                    style={{ left: i.inicio * pps, width: Math.max(6, (i.fim - i.inicio) * pps) }}
                    title={`${e.tipos[i.tipo as keyof typeof e.tipos] ?? i.tipo} ${hms(i.inicio)}–${hms(i.fim)}${i.motivo ? ` · ${i.motivo}` : ''}`}
                    onPointerDown={(ev) => arrastar(ev, i, 'mover')}>
                    <span className="alca ini" onPointerDown={(ev) => arrastar(ev, i, 'ini')} />
                    <span className="nome">{ICONES[i.tipo]} {i.tipo === 'texto' ? String(i.params.texto) : i.tipo === 'emoji' ? String(i.params.emoji) : i.tipo === 'som' ? String(i.params.nome) : i.tipo === 'sticker' ? nomeDoRef(i.params.ref) : i.tipo === 'cena' ? `${ICONES_CENA[String(i.params.cena)] ?? ''} ${resumoCena(i.params)}` : e.tipos[i.tipo as keyof typeof e.tipos] ?? i.tipo}</span>
                    <span className="alca fim" onPointerDown={(ev) => arrastar(ev, i, 'fim')} />
                  </div>
                ))}
              </div>
            </div>
          ))}
          <div className="lt-cabeca" style={{ left: ROTULO + tempo * pps }} />
        </div>
      </div>
    </div>
  )
}

// Texto, cores, idioma e som de uma chamada animada (Inscreva-se, curtir…). Vazio = o padrão do modelo.
function CamposChamada(props: { p: Record<string, unknown>; chamada: Chamada; mudar(m: Partial<ItemEd>, registrar?: boolean): void }): React.JSX.Element {
  const { p, chamada, mudar } = props
  const t = useT()
  const e = t.ed
  const idioma = p.idioma === 'en' ? 'en' : 'pt'
  const [padrao1, padrao2] = chamada.textos[idioma]
  const preset = PRESETS_CHAMADA[String(p.preset || chamada.preset)] ?? [chamada.cor, chamada.cor_texto]
  const cor = String(p.cor || preset[0])
  const corTexto = String(p.cor_texto || preset[1])
  const livre = !!chamada.fixo
  return (
    <>
      <label className="campo">{e.params.texto}
        <input value={String(p.texto ?? '')} maxLength={40} placeholder={padrao1} onChange={(ev) => mudar({ params: { texto: ev.target.value } })} />
      </label>
      {chamada.tem_texto2 && (
        <label className="campo">{e.textoDepois}
          <input value={String(p.texto2 ?? '')} maxLength={40} placeholder={padrao2} onChange={(ev) => mudar({ params: { texto2: ev.target.value } })} />
        </label>
      )}
      <div className="linha" style={{ flexWrap: 'wrap', gap: 4 }}>
        {Object.entries(PRESETS_CHAMADA).map(([nome, [c1, c2]]) => (
          <button key={nome} className={`preset-cor${cor.toUpperCase() === c1 && corTexto.toUpperCase() === c2 ? ' ativo' : ''}`} title={e.presetsChamada[nome as keyof typeof e.presetsChamada]}
            style={{ background: c1, color: c2 }} onClick={() => mudar({ params: { preset: nome, cor: '', cor_texto: '' } })}>Aa</button>
        ))}
      </div>
      <div className="linha">
        <label className="campo">{livre ? e.corContorno : e.corBotao}<input type="color" value={cor.toLowerCase()} onChange={(ev) => mudar({ params: { cor: ev.target.value } })} /></label>
        <label className="campo">{e.corTexto}<input type="color" value={corTexto.toLowerCase()} onChange={(ev) => mudar({ params: { cor_texto: ev.target.value } })} /></label>
      </div>
      <div className="linha">
        <label className="campo">{e.idioma}
          <select value={idioma} onChange={(ev) => mudar({ params: { idioma: ev.target.value, texto: '', texto2: '' } })}>
            <option value="pt">Português</option>
            <option value="en">English</option>
          </select>
        </label>
        {chamada.som && (
          <label className="linha"><input type="checkbox" checked={p.som !== false} onChange={(ev) => mudar({ params: { som: ev.target.checked } })} /> {e.somChamada(chamada.som)}</label>
        )}
      </div>
    </>
  )
}

type Fonte = { id: string; nome: string; italico: boolean; origem: string; categoria: string; instalada: boolean; bytes?: number }
const BOTOES_FORMATO = [
  { k: 'negrito', rotulo: 'B', estilo: { fontWeight: 900 } },
  { k: 'italico', rotulo: 'I', estilo: { fontStyle: 'italic' } },
  { k: 'sublinhado', rotulo: 'U', estilo: { textDecoration: 'underline' } },
  { k: 'riscado', rotulo: 'S', estilo: { textDecoration: 'line-through' } },
  { k: 'maiusculas', rotulo: 'AA', estilo: {} }
] as const
const PADRAO_FORMATO: Record<string, boolean> = { negrito: false, italico: false, sublinhado: false, riscado: false, contorno: true, sombra: true, maiusculas: false }
const ligado = (p: Record<string, unknown>, k: string): boolean => (p[k] === undefined || p[k] === '' ? PADRAO_FORMATO[k] : p[k] === true || p[k] === 'true' || p[k] === '1')

// Fonte e formatação do texto sem fundo, como num editor de texto (negrito, itálico, sublinhado, riscado,
// caixa alta, contorno e sombra). O canal pode subir fontes próprias (TTF/OTF).
function FormatoTexto(props: { api: Api; canal: string; p: Record<string, unknown>; mudar(m: Partial<ItemEd>, registrar?: boolean): void }): React.JSX.Element {
  const { api, canal, p, mudar } = props
  const t = useT()
  const e = t.ed
  const [fontes, setFontes] = useState<Fonte[]>([])
  const [msg, setMsg] = useState('')
  const [busca, setBusca] = useState('')
  const [cat, setCat] = useState('')
  const [baixando, setBaixando] = useState<string | null>(null) // id da fonte, ou "n/total" ao baixar todas
  const atual = String(p.fonte || 'montserrat')
  const visiveis = fontes.filter((f) => (!cat || f.categoria === cat) && (!busca.trim() || f.nome.toLowerCase().includes(busca.trim().toLowerCase())))
  const faltam = fontes.filter((f) => !f.instalada)
  const escolher = async (f: Fonte): Promise<void> => {
    setMsg('')
    if (!f.instalada) {
      setBaixando(f.id)
      try {
        await api.post('/api/fontes/baixar', { id: f.id })
        carregar()
      } catch (err) {
        setMsg(err instanceof Error ? err.message : String(err))
        setBaixando(null)
        return
      }
      setBaixando(null)
    }
    mudar({ params: { fonte: f.id } })
  }
  const baixarTodas = async (): Promise<void> => {
    setMsg('')
    for (let k = 0; k < faltam.length; k++) {
      setBaixando(`${k + 1}/${faltam.length}`)
      try {
        await api.post('/api/fontes/baixar', { id: faltam[k].id })
      } catch (err) {
        setMsg(err instanceof Error ? err.message : String(err))
        break
      }
    }
    setBaixando(null)
    carregar()
  }
  const carregar = (): void => { api.get<Fonte[]>('/api/fontes', { canal }).then(setFontes, () => setFontes([])) }
  useEffect(carregar, [api, canal]) // eslint-disable-line react-hooks/exhaustive-deps
  const enviar = (arq: File | undefined): void => {
    if (!arq) return
    setMsg('')
    if (arq.size > 10 * 1024 * 1024) return setMsg(e.fonteGrande)
    const leitor = new FileReader()
    leitor.onload = () => {
      api.post<Fonte>('/api/fontes/enviar', { canal, nome: arq.name, arquivo: String(leitor.result) }).then((f) => {
        carregar()
        mudar({ params: { fonte: f.id } })
      }, (err) => setMsg(err instanceof Error ? err.message : String(err)))
    }
    leitor.readAsDataURL(arq)
  }
  return (
    <>
      <div className="campo">{e.fonte}: <strong>{fontes.find((f) => f.id === atual)?.nome ?? atual}</strong></div>
      <div className="linha" style={{ gap: 4 }}>
        <input type="search" placeholder={e.buscarFonte} value={busca} onChange={(ev) => setBusca(ev.target.value)} style={{ flex: 1, minWidth: 0 }} />
        <select value={cat} onChange={(ev) => setCat(ev.target.value)} aria-label={e.categoria}>
          <option value="">{e.todas}</option>
          {[...new Set(fontes.map((f) => f.categoria))].map((c) => <option key={c} value={c}>{e.catFontes[c as keyof typeof e.catFontes] ?? c}</option>)}
        </select>
      </div>
      <div className="lista-fontes" role="listbox" aria-label={e.fonte}>
        {visiveis.map((f) => (
          <button key={f.id} role="option" aria-selected={f.id === atual} className={`fonte-btn${f.id === atual ? ' ativo' : ''}`}
            title={`${f.nome}${f.origem === 'google' ? ' · Google Fonts' : f.origem === 'canal' ? ` · ${e.doCanal}` : ''}`}
            disabled={!!baixando} onClick={() => void escolher(f)}>
            {f.instalada
              ? <img src={api.url('/api/fontes/amostra', { id: f.id, canal, token: api.token })} alt={f.nome} loading="lazy" />
              : <span>{f.nome} <span className="dica">{baixando === f.id ? e.baixando : '⬇'}</span></span>}
          </button>
        ))}
      </div>
      {faltam.length > 0 && (
        <button className="link" disabled={!!baixando} onClick={() => void baixarTodas()} title={e.baixarFontesDica}>
          ⬇ {baixando?.includes('/') ? `${e.baixando} ${baixando}` : e.baixarFontes(faltam.length, Math.round(faltam.reduce((a, f) => a + (f.bytes ?? 0), 0) / 1e6))}
        </button>
      )}
      <label className="link" title={e.enviarFonteDica} style={{ cursor: 'pointer' }}>
        + {e.enviarFonte}
        <input type="file" accept=".ttf,.otf,font/ttf,font/otf" hidden onChange={(ev) => {
          enviar(ev.target.files?.[0])
          ev.target.value = ''
        }} />
      </label>
      <div className="linha" style={{ flexWrap: 'wrap', gap: 4 }}>
        {BOTOES_FORMATO.map((b) => (
          <button key={b.k} className={`preset-cor${ligado(p, b.k) ? ' ativo' : ''}`} title={e.formatos[b.k]} aria-pressed={ligado(p, b.k)}
            style={b.estilo} onClick={() => mudar({ params: { [b.k]: !ligado(p, b.k) } })}>{b.rotulo}</button>
        ))}
      </div>
      <label className="linha"><input type="checkbox" checked={ligado(p, 'contorno')} onChange={(ev) => mudar({ params: { contorno: ev.target.checked } })} /> {e.formatos.contorno}</label>
      <label className="linha"><input type="checkbox" checked={ligado(p, 'sombra')} onChange={(ev) => mudar({ params: { sombra: ev.target.checked } })} /> {e.formatos.sombra}</label>
      {msg && <p className="erro-txt" style={{ margin: 0 }}>{msg}</p>}
    </>
  )
}

// A imagem do sticker na prévia. Cada vez que o item entra em cena ganha um endereço novo, para a animação
// começar do primeiro quadro junto com o vídeo. As chamadas (que tocam uma vez só) são desenhadas quadro a
// quadro no tempo do item, assim a prévia bate com o render mesmo com o vídeo pausado ou ao arrastar a cabeça.
function ImgSticker(props: { src(n: string): string; className: string; style: React.CSSProperties; t?: number; repetir?: boolean; esticar?: number; segurar?: boolean }): React.JSX.Element {
  const [n] = useState(() => Math.random().toString(36).slice(2, 8))
  const [nat, setNat] = useState<[number, number] | null>(null)
  const prop = nat && props.esticar && props.esticar !== 1 ? { aspectRatio: `${nat[0]} / ${nat[1] * props.esticar}`, objectFit: 'fill' as const } : {}
  const canvas = useRef<HTMLCanvasElement>(null)
  const [anim, setAnim] = useState<Animacao | null>(null)
  const porQuadro = props.t !== undefined && typeof (window as unknown as { ImageDecoder?: unknown }).ImageDecoder === 'function'
  const url = props.src('')
  useEffect(() => {
    if (!porQuadro) return
    let vivo = true
    quadrosDe(url).then((a) => vivo && setAnim(a), () => undefined)
    return () => { vivo = false }
  }, [url, porQuadro])
  useEffect(() => {
    const c = canvas.current
    if (!anim || !c || props.t === undefined) return
    const t = props.repetir ? props.t % anim.duracao : props.t
    let k = 0
    while (k + 1 < anim.inicios.length && anim.inicios[k + 1] <= t) k++
    const q = anim.quadros[k]
    if (c.width !== q.width) c.width = q.width
    if (c.height !== q.height) c.height = q.height
    const ctx = c.getContext('2d')
    ctx?.clearRect(0, 0, c.width, c.height)
    if (t < anim.duracao || props.segurar) ctx?.drawImage(q, 0, 0) // o texto fica no último quadro
  }, [anim, props.t, props.repetir, props.segurar])
  useEffect(() => { if (anim) setNat([anim.quadros[0].width, anim.quadros[0].height]) }, [anim])
  if (porQuadro) return <canvas ref={canvas} className={props.className} style={{ ...props.style, height: 'auto', ...prop }} />
  return <img className={props.className} src={props.src(n)} alt="" style={{ ...props.style, ...prop }}
    onLoad={(ev) => setNat([ev.currentTarget.naturalWidth, ev.currentTarget.naturalHeight])} />
}

type Animacao = { quadros: ImageBitmap[]; inicios: number[]; duracao: number }
const animacoes = new Map<string, Promise<Animacao>>()
type Decodificador = { tracks: { ready: Promise<void>; selectedTrack: { frameCount: number } | null }; decode(o: { frameIndex: number }): Promise<{ image: VideoFrame }>; close(): void }

// os quadros de um APNG (ImageDecoder do Chromium), guardados por endereço
function quadrosDe(url: string): Promise<Animacao> {
  const pronto = animacoes.get(url)
  if (pronto) return pronto
  if (animacoes.size > 24) animacoes.clear()
  const p = (async () => {
    const dados = await (await fetch(url)).arrayBuffer()
    const Dec = (window as unknown as { ImageDecoder: new (o: { data: ArrayBuffer; type: string }) => Decodificador }).ImageDecoder
    const dec = new Dec({ data: dados, type: 'image/png' })
    await dec.tracks.ready
    const n = dec.tracks.selectedTrack?.frameCount ?? 1
    const quadros: ImageBitmap[] = []
    const inicios: number[] = []
    let acc = 0
    for (let k = 0; k < n; k++) {
      const { image } = await dec.decode({ frameIndex: k })
      inicios.push(acc)
      acc += (image.duration ?? 40000) / 1e6
      quadros.push(await createImageBitmap(image))
      image.close()
    }
    dec.close()
    return { quadros, inicios, duracao: acc }
  })()
  p.catch(() => animacoes.delete(url))
  animacoes.set(url, p)
  return p
}

// ---- objetos arrastáveis na prévia -------------------------------------------------------------
// x, y = centro do objeto em fração do quadro (o render usa os mesmos números); tamanho = fração da largura
// (sticker, emoji) ou da altura (texto, tamanho da fonte); esticar = altura/largura do sticker (Shift no canto).
type Guia = { dir: 'v' | 'h'; pos: number }
type Zona = { esq: number; dir: number; topo: number; base: number }
const MOVEIS = ['texto', 'emoji', 'sticker']
const LIMITES: Record<string, [number, number]> = { texto: [0.02, 0.2], emoji: [0.05, 0.5], sticker: [0.05, 0.8] }

// margens onde a interface das plataformas cobre o vídeo (botões à direita, legenda e nome embaixo)
const zonaDoFormato = (w: number, h: number): Zona => (h > w ? { esq: 0.06, dir: 0.16, topo: 0.1, base: 0.22 } : { esq: 0.05, dir: 0.05, topo: 0.06, base: 0.1 })
const zonaCss = (z: Zona): React.CSSProperties => ({ left: `${z.esq * 100}%`, right: `${z.dir * 100}%`, top: `${z.topo * 100}%`, bottom: `${z.base * 100}%` })

function centroNaTela(id: string): { x: number; y: number; w: number; h: number } | null {
  const el = document.querySelector<HTMLElement>(`[data-movel="${id}"]`)
  const tela = el?.closest('.tela')
  if (!el || !tela) return null
  const r = el.getBoundingClientRect()
  const t = tela.getBoundingClientRect()
  return { x: (r.left + r.width / 2 - t.left) / t.width, y: (r.top + r.height / 2 - t.top) / t.height, w: r.width / t.width, h: r.height / t.height }
}

function Movel(props: {
  item: ItemEd
  sel: string | null
  zona: Zona | null
  largura?: string
  extra?: string
  opacidade?: number
  selecionar(id: string): void
  mudar(id: string, params: Record<string, unknown>, registrar: boolean): void
  setGuias(g: Guia[]): void
  children: React.ReactNode
}): React.JSX.Element {
  const { item: i, sel, zona, largura, extra = '', opacidade = 1, selecionar, mudar, setGuias } = props
  const ref = useRef<HTMLDivElement>(null)
  const giro = i.tipo === 'sticker' ? Number(i.params.rotacao) || 0 : 0
  const livre = typeof i.params.x === 'number' && typeof i.params.y === 'number'
  const base: React.CSSProperties = livre
    ? { position: 'absolute', left: `${Number(i.params.x) * 100}%`, top: `${Number(i.params.y) * 100}%`, transform: 'translate(-50%, -50%)' }
    : posicaoCss(String(i.params.posicao))
  const estilo: React.CSSProperties = { ...base, width: largura, opacity: opacidade, transform: `${base.transform ?? ''} rotate(${giro}deg)${extra}` }

  // arrastar: corpo move, canto redimensiona, bolinha de cima gira
  const comecar = (ev: React.PointerEvent, modo: 'mover' | 'tamanho' | 'girar'): void => {
    if (ev.button !== 0) return
    ev.preventDefault()
    ev.stopPropagation()
    selecionar(i.id)
    const tela = ref.current?.closest('.tela')?.getBoundingClientRect()
    const c0 = centroNaTela(i.id)
    if (!tela || !c0) return
    const px0 = ev.clientX, py0 = ev.clientY
    const cx = tela.left + c0.x * tela.width, cy = tela.top + c0.y * tela.height
    const t0 = Number(i.params.tamanho) || 0.1
    const e0 = Number(i.params.esticar) || 1
    const [lo, hi] = LIMITES[i.tipo] ?? [0.02, 0.8]
    let primeiro = true
    const aplicar = (params: Record<string, unknown>): void => {
      mudar(i.id, { x: +c0.x.toFixed(4), y: +c0.y.toFixed(4), ...params }, primeiro) // o primeiro passo entra no desfazer
      primeiro = false
    }
    const mover = (m: PointerEvent): void => {
      if (modo === 'mover') {
        let x = c0.x + (m.clientX - px0) / tela.width
        let y = c0.y + (m.clientY - py0) / tela.height
        const g: Guia[] = []
        const lim = 0.012
        const alvosX = [0.5, c0.w / 2, 1 - c0.w / 2, ...(zona ? [zona.esq + c0.w / 2, 1 - zona.dir - c0.w / 2] : [])]
        const linhasX = [0.5, 0, 1, ...(zona ? [zona.esq, 1 - zona.dir] : [])]
        const alvosY = [0.5, c0.h / 2, 1 - c0.h / 2, ...(zona ? [zona.topo + c0.h / 2, 1 - zona.base - c0.h / 2] : [])]
        const linhasY = [0.5, 0, 1, ...(zona ? [zona.topo, 1 - zona.base] : [])]
        if (!m.altKey) {
          const kx = alvosX.findIndex((a) => Math.abs(x - a) < lim)
          if (kx >= 0) { x = alvosX[kx]; g.push({ dir: 'v', pos: linhasX[kx] }) }
          const ky = alvosY.findIndex((a) => Math.abs(y - a) < lim)
          if (ky >= 0) { y = alvosY[ky]; g.push({ dir: 'h', pos: linhasY[ky] }) }
        }
        setGuias(g)
        aplicar({ x: +Math.min(1, Math.max(0, x)).toFixed(4), y: +Math.min(1, Math.max(0, y)).toFixed(4) })
      } else if (modo === 'tamanho') {
        const d0 = Math.hypot(px0 - cx, py0 - cy) || 1
        if (m.shiftKey && i.tipo === 'sticker') {
          const fx = Math.abs(m.clientX - cx) / (Math.abs(px0 - cx) || 1)
          const fy = Math.abs(m.clientY - cy) / (Math.abs(py0 - cy) || 1)
          const tam = Math.min(hi, Math.max(lo, t0 * fx))
          aplicar({ tamanho: +tam.toFixed(3), esticar: +Math.min(4, Math.max(0.25, (e0 * fy * t0) / tam)).toFixed(3) })
        } else {
          aplicar({ tamanho: +Math.min(hi, Math.max(lo, t0 * (Math.hypot(m.clientX - cx, m.clientY - cy) / d0))).toFixed(3) })
        }
      } else {
        const a0 = Math.atan2(py0 - cy, px0 - cx)
        let r = giro + ((Math.atan2(m.clientY - cy, m.clientX - cx) - a0) * 180) / Math.PI
        r = ((r + 540) % 360) - 180
        if (m.shiftKey) r = Math.round(r / 15) * 15
        aplicar({ rotacao: Math.round(r) })
      }
    }
    const soltar = (): void => {
      window.removeEventListener('pointermove', mover)
      window.removeEventListener('pointerup', soltar)
      setGuias([])
    }
    window.addEventListener('pointermove', mover)
    window.addEventListener('pointerup', soltar)
  }

  const ativo = sel === i.id
  return (
    <div ref={ref} data-movel={i.id} className={`movel${ativo ? ' ativo' : ''}`} style={estilo} onPointerDown={(ev) => comecar(ev, 'mover')}>
      {props.children}
      {ativo && (
        <>
          {(['ne', 'no', 'se', 'so'] as const).map((c) => <span key={c} className={`alca-canto ${c}`} onPointerDown={(ev) => comecar(ev, 'tamanho')} />)}
          {i.tipo === 'sticker' && <span className="alca-giro" onPointerDown={(ev) => comecar(ev, 'girar')} />}
        </>
      )}
    </div>
  )
}
