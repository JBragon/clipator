import { useEffect, useMemo, useRef, useState } from 'react'
import type { Api, Clip } from '../api'
import { useT } from '../i18n'
import { juntar, r2, tempo, trocarEmTodas, type Frase } from '../legenda'

// Editar a legenda depois do render (passo 5): corrigir o texto e os tempos de cada frase e gerar o clip de novo.
// A legenda é queimada no vídeo, então o motor guarda a correção (clips/<id>/legenda-editada.json) e refaz o render
// com ela; o acabamento em uso é refeito em cima do vídeo novo.

type Estado = { frases: Frase[]; editada: boolean; desatualizada: boolean; duracao: number; deslocamento: number; gerado: boolean }

export function EditarLegenda(props: { api: Api; base: string; clip: Clip; video: string | null; aoMudar(): void }): React.JSX.Element {
  const { api, base, clip, video: caminhoVideo } = props
  const t = useT()
  const tl = t.leg
  const url = `${base}/clips/${encodeURIComponent(clip.id)}/legenda`
  const [aberto, setAberto] = useState(false)
  const [estado, setEstado] = useState<Estado | null>(null)
  const [frases, setFrases] = useState<Frase[]>([])
  const [msg, setMsg] = useState('')
  const [ocupado, setOcupado] = useState(false)
  const [agora, setAgora] = useState(0) // tempo do clip no player
  const [de, setDe] = useState('')
  const [para, setPara] = useState('')
  const video = useRef<HTMLVideoElement>(null)
  const lista = useRef<HTMLDivElement>(null)

  const carregar = async (): Promise<void> => {
    try {
      const e = await api.get<Estado>(url)
      setEstado(e)
      setFrases(e.frases)
      setMsg('')
    } catch (e) {
      setEstado(null)
      setMsg(e instanceof Error ? e.message : String(e))
    }
  }
  useEffect(() => {
    void carregar() // fechada também: o chip "legenda editada" aparece sem abrir
  }, [aberto, clip.versao, clip.inicio, clip.fim]) // eslint-disable-line react-hooks/exhaustive-deps

  const mudou = !!estado && JSON.stringify(frases) !== JSON.stringify(estado.frases)
  const desloc = estado?.deslocamento ?? 0
  const duracao = estado?.duracao ?? 0
  const atual = useMemo(() => frases.findIndex((f) => agora >= f.inicio && agora < f.fim), [frases, agora])

  // a frase que está tocando fica visível na lista
  useEffect(() => {
    if (atual < 0 || !lista.current) return
    const el = lista.current.querySelector<HTMLElement>(`[data-i="${atual}"]`)
    const caixa = lista.current.getBoundingClientRect()
    const r = el?.getBoundingClientRect()
    if (el && r && (r.top < caixa.top || r.bottom > caixa.bottom)) el.scrollIntoView({ block: 'nearest' })
  }, [atual])

  const mudar = (i: number, f: Partial<Frase>): void => setFrases((fs) => fs.map((x, k) => (k === i ? { ...x, ...f } : x)))
  const tirar = (i: number): void => setFrases((fs) => fs.filter((_, k) => k !== i))
  const adicionarDepois = (i: number): void =>
    setFrases((fs) => {
      const a = fs[i]
      const prox = fs[i + 1]
      const ini = r2(a.fim)
      const fim = r2(Math.min(prox ? prox.inicio : duracao, ini + 1.5))
      if (fim - ini < 0.1) return fs
      return [...fs.slice(0, i + 1), { inicio: ini, fim, texto: '', palavras: [] }, ...fs.slice(i + 1)]
    })
  const irPara = (s: number, tocar = false): void => {
    const v = video.current
    if (!v) return
    v.currentTime = Math.max(0, s + desloc)
    if (tocar) void v.play().catch(() => undefined)
  }
  const doPlayer = (): number => r2(Math.max(0, Math.min(duracao, (video.current?.currentTime ?? 0) - desloc)))

  const trocar = (): void => {
    const [novas, n] = trocarEmTodas(frases, de, para)
    setFrases(novas)
    setMsg(n ? tl.trocadas(n) : tl.nadaTrocado)
  }

  // frases vazias não vão: o motor tira, mas aqui a mensagem fica mais clara
  const validas = (): Frase[] | null => {
    const fs = frases.filter((f) => f.texto.trim())
    const ruim = fs.findIndex((f) => !(f.fim > f.inicio))
    if (ruim >= 0) {
      setMsg(tl.tempoInvalido(ruim + 1))
      return null
    }
    if (!fs.length) {
      setMsg(tl.vazia)
      return null
    }
    return fs
  }

  const salvar = async (): Promise<boolean> => {
    const fs = validas()
    if (!fs) return false
    setOcupado(true)
    try {
      const e = await api.put<Estado>(url, { frases: fs })
      setEstado(e)
      setFrases(e.frases)
      setMsg(tl.salva)
      return true
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e))
      return false
    } finally {
      setOcupado(false)
    }
  }

  const gerar = async (): Promise<void> => {
    const fs = validas()
    if (!fs) return
    setOcupado(true)
    try {
      video.current?.pause()
      // o player sai da tela durante o render (no Windows o vídeo aberto impede trocar o arquivo)
      await api.post(`${url}/renderizar`, { frases: fs })
      setMsg('')
      props.aoMudar()
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e))
    } finally {
      setOcupado(false)
    }
  }

  const voltarATranscricao = async (): Promise<void> => {
    setOcupado(true)
    try {
      const e = await api.del<Estado>(url)
      setEstado(e)
      setFrases(e.frases)
      setMsg(tl.voltou)
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e))
    } finally {
      setOcupado(false)
    }
  }

  const campoTempo = (i: number, chave: 'inicio' | 'fim', valor: number): React.JSX.Element => (
    <span className="leg-tempo">
      <input type="number" min={0} max={duracao} step={0.05} value={r2(valor)} aria-label={chave === 'inicio' ? tl.inicio : tl.fim}
        onChange={(e) => mudar(i, { [chave]: Number(e.target.value) })} />
      <button className="link" title={tl.usarTempoDica} onClick={() => mudar(i, { [chave]: doPlayer() })}>⏱</button>
    </span>
  )

  return (
    <section className="editar-legenda">
      <div className="linha">
        <h4 style={{ margin: 0 }}>📝 {tl.titulo}</h4>
        {estado?.editada && !aberto && <span className="chip" style={{ color: 'var(--ok)' }}>✓ {tl.editada}</span>}
        <span className="espaco" style={{ flex: 1 }} />
        <button onClick={() => setAberto(!aberto)}>{aberto ? t.fechar : tl.abrir}</button>
      </div>
      {!aberto && <p className="dica" style={{ margin: 0 }}>{tl.dica}</p>}
      {aberto && !estado && msg && <p className="erro-txt" style={{ margin: 0 }}>{msg}</p>}
      {aberto && estado && (
        <div className="leg-corpo">
          <div className="leg-previa">
            {caminhoVideo && (
              <video ref={video} src={api.midia(caminhoVideo, String(Date.now() >> 14))} controls playsInline
                onTimeUpdate={(e) => setAgora(e.currentTarget.currentTime - desloc)} onSeeked={(e) => setAgora(e.currentTarget.currentTime - desloc)} />
            )}
            {/* o vídeo ainda tem a legenda antiga: aqui embaixo aparece como a frase vai ficar */}
            <div className="leg-nova" aria-live="polite">
              <span className="dica">{tl.comoFica}</span>
              <strong>{atual >= 0 ? frases[atual].texto || '—' : '—'}</strong>
            </div>
            <div className="leg-trocar">
              <input value={de} onChange={(e) => setDe(e.target.value)} placeholder={tl.trocarDe} aria-label={tl.trocarDe} />
              <input value={para} onChange={(e) => setPara(e.target.value)} placeholder={tl.trocarPara} aria-label={tl.trocarPara}
                onKeyDown={(e) => e.key === 'Enter' && trocar()} />
              <button disabled={!de.trim()} onClick={trocar}>{tl.trocar}</button>
            </div>
          </div>

          <div className="leg-controles">
            {estado.desatualizada && <p className="aviso-txt" style={{ margin: 0 }}>{tl.desatualizada}</p>}
            <div className="leg-lista" ref={lista}>
              {frases.map((f, i) => (
                <div key={i} data-i={i} className={`leg-frase ${i === atual ? 'tocando' : ''} ${f.texto.trim() ? '' : 'vazia'}`}>
                  <div className="linha">
                    <button className="link" title={`${tl.ouvirDica} (${tempo(f.inicio)})`} aria-label={tl.ouvirDica} onClick={() => irPara(f.inicio, true)}>▶</button>
                    {campoTempo(i, 'inicio', f.inicio)}
                    <span className="dica">→</span>
                    {campoTempo(i, 'fim', f.fim)}
                    <span className="espaco" style={{ flex: 1 }} />
                    <button className="link" title={tl.adicionarDica} onClick={() => adicionarDepois(i)}>＋</button>
                    <button className="link" title={tl.juntarDica} disabled={i + 1 >= frases.length} onClick={() => setFrases(juntar(frases, i))}>⤓</button>
                    <button className="link" title={tl.tirarDica} aria-label={tl.tirarDica} onClick={() => tirar(i)}>✕</button>
                  </div>
                  <textarea rows={2} value={f.texto} onChange={(e) => mudar(i, { texto: e.target.value })}
                    onFocus={() => irPara(f.inicio)} placeholder={tl.textoVazio} />
                </div>
              ))}
            </div>
            <div className="linha">
              <button disabled={ocupado || !mudou} onClick={() => void salvar()}>{t.salvar}</button>
              <button className="primario" disabled={ocupado || (!mudou && !estado.editada)} onClick={() => void gerar()}
                title={tl.gerarDica}>{tl.gerar}</button>
              {mudou && <button className="link" disabled={ocupado} onClick={() => setFrases(estado.frases)}>{tl.descartar}</button>}
              {(estado.editada || estado.desatualizada) && (
                <button className="link" disabled={ocupado} onClick={() => void voltarATranscricao()}>{tl.voltarTranscricao}</button>
              )}
              <span className="dica">{msg}</span>
            </div>
            <span className="dica">{tl.comoFunciona}</span>
          </div>
        </div>
      )}
    </section>
  )
}
