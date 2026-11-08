import { useEffect, useMemo, useState } from 'react'
import type { Api, Job } from '../api'
import { useT } from '../i18n'

export type Chamada = { textos: Record<'pt' | 'en', [string, string]>; preset: string; cor: string; cor_texto: string; tem_texto2: boolean; som: string | null; fixo?: boolean; caixa_alta?: boolean }
export type Sticker = { ref: string; nome: string; categoria: string; palavras: string[]; animado: boolean; pacote: string; licenca: string; credito: boolean; instalado: boolean; duracao?: number; chamada?: Chamada }
type Biblioteca = { stickers: Sticker[]; categorias: string[]; status: { instalados: number; total: number; bytes: number; pasta: string } }
type Web = { id: string; nome: string; colecao: string; licenca: string; credito: boolean }

const semAcento = (s: string): string => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
// as chamadas ("cta:…") são geradas pelo motor com o texto e as cores do item
const CAMPOS_CHAMADA = ['texto', 'texto2', 'cor', 'cor_texto', 'idioma', 'preset', 'fonte',
  'negrito', 'italico', 'sublinhado', 'riscado', 'contorno', 'sombra', 'maiusculas'] as const
export const urlSticker = (api: Api, ref: string, canal: string, params?: Record<string, unknown>, extra?: string): string => {
  const q: Record<string, string> = { ref, canal, token: api.token }
  if (ref.startsWith('cta:') && params) for (const k of CAMPOS_CHAMADA) if (params[k] !== undefined && params[k] !== '') q[k] = String(params[k])
  if (extra) q.n = extra
  return api.url('/api/stickers/arquivo', q)
}
export const PRESETS_CHAMADA: Record<string, [string, string]> = {
  vermelho: ['#E62117', '#FFFFFF'], preto: ['#141416', '#FFFFFF'], branco: ['#FFFFFF', '#E62117'], neon: ['#39FF14', '#0A0A0A'],
  contorno: ['#141416', '#FFFFFF']
}
export const MODOS_CHAMADA = ['nenhuma', 'inicio', 'fim', 'inicio-e-fim'] as const

// Stickers do editor: o pacote curado (Fluent Emoji, MIT), os do canal e a busca online (só ao clicar).
export function BibliotecaStickers(props: {
  api: Api
  canal: string
  jobs: Record<string, Job>
  adicionar(ref: string): void
  previa(ref: string | null): void
}): React.JSX.Element {
  const { api, canal, jobs, adicionar, previa } = props
  const t = useT()
  const e = t.ed
  const [lib, setLib] = useState<Biblioteca | null>(null)
  const [busca, setBusca] = useState('')
  const [cat, setCat] = useState('')
  const [pacote, setPacote] = useState('')
  const [jobBaixar, setJobBaixar] = useState<string | null>(null)
  const [web, setWeb] = useState<Web[] | null>(null)
  const [buscandoWeb, setBuscandoWeb] = useState(false)
  const [msg, setMsg] = useState('')
  const [auto, setAuto] = useState<string>('nenhuma')
  const [enviando, setEnviando] = useState(false)

  const carregar = (): void => {
    api.get<Biblioteca>('/api/stickers', { canal }).then(setLib, () => setLib(null))
  }
  useEffect(carregar, [api, canal]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    api.get<{ chamada_automatica: string }>(`/api/canais/${encodeURIComponent(canal)}/chamada`).then((r) => setAuto(r.chamada_automatica), () => undefined)
  }, [api, canal])
  const mudarAuto = (v: string): void => {
    setAuto(v)
    api.put(`/api/canais/${encodeURIComponent(canal)}/chamada`, { chamada_automatica: v }).catch((err) => setMsg(err instanceof Error ? err.message : String(err)))
  }

  const job = jobBaixar ? jobs[jobBaixar] : undefined
  useEffect(() => {
    if (job && (job.status === 'ok' || job.status === 'erro')) {
      setJobBaixar(null)
      carregar()
    }
  }, [job?.status]) // eslint-disable-line react-hooks/exhaustive-deps

  const lista = useMemo(() => {
    const q = semAcento(busca.trim())
    return (lib?.stickers ?? []).filter((s) => s.instalado && (!cat || s.categoria === cat) && (!pacote || s.pacote === pacote) &&
      (!q || semAcento(`${s.nome} ${s.palavras.join(' ')}`).includes(q)))
  }, [lib, busca, cat, pacote])
  const pacotes = [...new Set((lib?.stickers ?? []).map((s) => s.pacote))]
  const faltam = lib ? lib.status.total - lib.status.instalados : 0

  const buscarWeb = async (): Promise<void> => {
    if (!busca.trim()) return
    setBuscandoWeb(true)
    setMsg('')
    try {
      setWeb(await api.get<Web[]>('/api/stickers/web/buscar', { q: busca.trim() }))
    } catch (err) {
      setMsg(err instanceof Error ? err.message : String(err))
    }
    setBuscandoWeb(false)
  }

  // a marca do usuário (ou qualquer PNG): o motor confere tamanho e imagem e guarda nos stickers do canal
  const enviar = (arq: File | undefined): void => {
    if (!arq) return
    setMsg('')
    if (arq.type && arq.type !== 'image/png') return setMsg(e.soPng)
    if (arq.size > 5 * 1024 * 1024) return setMsg(e.stickerGrande(arq.size / 1e6))
    setEnviando(true)
    const leitor = new FileReader()
    leitor.onload = () => {
      api.post<{ ref: string }>('/api/stickers/canal/enviar', { canal, nome: arq.name, png: String(leitor.result) }).then((r) => {
        carregar()
        adicionar(r.ref)
      }, (err) => setMsg(err instanceof Error ? err.message : String(err))).finally(() => setEnviando(false))
    }
    leitor.onerror = () => {
      setEnviando(false)
      setMsg(e.soPng)
    }
    leitor.readAsDataURL(arq)
  }

  // o SVG vira PNG aqui (o navegador desenha o vetor) e o motor guarda no canal com o crédito
  const baixarWeb = async (w: Web): Promise<void> => {
    setMsg('')
    try {
      const img = new Image()
      img.crossOrigin = 'anonymous'
      img.src = api.url('/api/stickers/web/svg', { id: w.id, token: api.token })
      await img.decode()
      const lado = 512
      const c = document.createElement('canvas')
      c.width = lado
      c.height = lado
      const ctx = c.getContext('2d')
      if (!ctx) throw new Error('sem canvas')
      const esc = lado / Math.max(img.naturalWidth || lado, img.naturalHeight || lado)
      const w2 = (img.naturalWidth || lado) * esc
      const h2 = (img.naturalHeight || lado) * esc
      ctx.drawImage(img, (lado - w2) / 2, (lado - h2) / 2, w2, h2)
      const r = await api.post<{ ref: string }>('/api/stickers/web/salvar', { canal, id: w.id, png: c.toDataURL('image/png') })
      carregar()
      adicionar(r.ref)
    } catch (err) {
      setMsg(err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <div className="biblioteca-stickers">
      <input type="search" placeholder={e.buscarStickers} value={busca} onChange={(ev) => setBusca(ev.target.value)}
        onKeyDown={(ev) => ev.key === 'Enter' && !lista.length && void buscarWeb()} />
      <div className="linha" style={{ flexWrap: 'wrap', gap: 3 }}>
        <select value={cat} onChange={(ev) => setCat(ev.target.value)} aria-label={e.categoria}>
          <option value="">{e.todas}</option>
          {(lib?.categorias ?? []).map((c) => <option key={c} value={c}>{e.catStickers[c as keyof typeof e.catStickers] ?? c}</option>)}
        </select>
        {pacotes.length > 1 && (
          <select value={pacote} onChange={(ev) => setPacote(ev.target.value)} aria-label={e.pacote}>
            <option value="">{e.todosPacotes}</option>
            {pacotes.map((p) => <option key={p}>{p}</option>)}
          </select>
        )}
      </div>
      {lib && faltam > 0 && (
        <div className="aviso-stickers">
          <span className="dica">{e.stickersFaltam(faltam, Math.round(lib.status.bytes / 1e6))}</span>
          <button disabled={!!jobBaixar} onClick={() => void api.post<{ job: string }>('/api/stickers/instalar').then((r) => setJobBaixar(r.job))}>
            {job ? `${Math.round(job.progresso * 100)}%` : e.baixarStickers}
          </button>
        </div>
      )}
      <label className="link" title={e.enviarStickerDica} style={{ cursor: enviando ? 'wait' : 'pointer' }}>
        ⬆ {enviando ? e.enviando : e.enviarSticker}
        <input type="file" accept="image/png" hidden disabled={enviando} onChange={(ev) => {
          enviar(ev.target.files?.[0])
          ev.target.value = ''
        }} />
      </label>
      {(!cat || cat === 'chamadas') && (
        <label className="linha dica" title={e.chamadaAutoDica}>
          {e.chamadaAuto}
          <select value={auto} onChange={(ev) => mudarAuto(ev.target.value)}>
            {MODOS_CHAMADA.map((m) => <option key={m} value={m}>{e.modosChamada[m]}</option>)}
          </select>
        </label>
      )}
      <div className="grade-stickers">
        {lista.slice(0, 200).map((s) => (
          <button key={s.ref} className={`sticker-btn${s.chamada ? ' chamada' : ''}`} draggable title={`${s.nome} · ${s.pacote} (${s.licenca})${s.animado ? ` · ${e.animado}` : ''}`}
            onDragStart={(ev) => ev.dataTransfer.setData('text/x-efeito', JSON.stringify({ tipo: 'sticker', extra: { ref: s.ref } }))}
            onMouseEnter={() => previa(s.ref)} onMouseLeave={() => previa(null)}
            onClick={() => adicionar(s.ref)}>
            <img src={urlSticker(api, s.ref, canal)} alt={s.nome} loading="lazy" draggable={false} />
          </button>
        ))}
      </div>
      {lib && !lista.length && <p className="dica" style={{ margin: 0 }}>{e.semStickers}</p>}
      <div className="linha">
        <button className="link" disabled={!busca.trim() || buscandoWeb} onClick={() => void buscarWeb()} title={e.buscarWebDica}>
          🌐 {buscandoWeb ? e.buscando : e.buscarWeb}
        </button>
      </div>
      {web && (
        <>
          <div className="dica">{e.resultadosWeb(web.length)}</div>
          <div className="grade-stickers">
            {web.map((w) => (
              <button key={w.id} className="sticker-btn" title={`${w.nome} · ${w.colecao} (${w.licenca})${w.credito ? ` · ${e.pedeCredito}` : ''}`} onClick={() => void baixarWeb(w)}>
                <img src={api.url('/api/stickers/web/svg', { id: w.id, token: api.token })} alt={w.nome} loading="lazy" draggable={false} />
              </button>
            ))}
          </div>
        </>
      )}
      {msg && <p className="erro-txt" style={{ margin: 0 }}>{msg}</p>}
    </div>
  )
}
