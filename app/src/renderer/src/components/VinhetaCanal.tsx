import { useEffect, useRef, useState } from 'react'
import type { Api } from '../api'
import { useT } from '../i18n'

// A vinheta do canal: o vídeo curto da marca que entra só nos cortes longos (nunca nos Shorts).
// Fica nos Detalhes do canal e no passo 3, no quadro dos cortes longos.
export type PosicaoVinheta = 'inicio' | 'depois-do-gancho'
export type EstadoVinheta = { arquivo: string | null; nome: string | null; duracao: number | null; posicao: PosicaoVinheta; faltando: boolean }

export function useVinheta(api: Api, canal: string): [EstadoVinheta | null, (e: EstadoVinheta) => void] {
  const [estado, setEstado] = useState<EstadoVinheta | null>(null)
  useEffect(() => {
    if (!canal) return
    let vivo = true
    api.get<EstadoVinheta>(`/api/canais/${encodeURIComponent(canal)}/vinheta`)
      .then((r) => { if (vivo) setEstado(r) }, () => { if (vivo) setEstado(null) })
    return () => { vivo = false }
  }, [api, canal])
  return [estado, setEstado]
}

export function VinhetaCanal(props: {
  api: Api
  canal: string
  estado: EstadoVinheta | null
  setEstado(e: EstadoVinheta): void
  compacto?: boolean
}): React.JSX.Element {
  const { api, canal, estado, setEstado, compacto } = props
  const t = useT()
  const tv = t.vinheta
  const url = `/api/canais/${encodeURIComponent(canal)}/vinheta`
  const [msg, setMsg] = useState('')
  const [enviando, setEnviando] = useState(false)
  const [versao, setVersao] = useState(0)
  const entrada = useRef<HTMLInputElement>(null)

  const enviar = (arq: File | undefined): void => {
    if (!arq) return
    setEnviando(true)
    setMsg(tv.enviando)
    const leitor = new FileReader()
    leitor.onload = async () => {
      try {
        setEstado(await api.post<EstadoVinheta>(url, { nome: arq.name, arquivo: String(leitor.result) }))
        setVersao((v) => v + 1)
        setMsg('')
      } catch (e) {
        setMsg(e instanceof Error ? e.message : String(e))
      }
      setEnviando(false)
      if (entrada.current) entrada.current.value = ''
    }
    leitor.onerror = () => (setMsg(tv.falhaLeitura), setEnviando(false))
    leitor.readAsDataURL(arq)
  }
  const remover = async (): Promise<void> => {
    try {
      setEstado(await api.del<EstadoVinheta>(url))
      setMsg('')
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e))
    }
  }
  const posicao = async (p: PosicaoVinheta): Promise<void> => {
    try {
      setEstado(await api.put<EstadoVinheta>(url, { posicao: p }))
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e))
    }
  }

  const tem = !!estado?.arquivo
  return (
    <div className={`vinheta-canal ${compacto ? 'compacto' : ''}`}>
      {!compacto && <span className="dica">{tv.explica}</span>}
      {tem && estado && (
        <div className="vinheta-atual">
          <video src={api.url(`${url}/video`, { token: api.token, v: `${estado.arquivo}-${versao}` })} controls muted preload="metadata" />
          <div className="vinheta-info">
            <strong>{estado.nome}</strong>
            {estado.duracao !== null && <span className="dica">{tv.segundos(estado.duracao)}</span>}
            {!compacto && (
              <label className="campo">{tv.posicaoPadrao}
                <select value={estado.posicao} onChange={(e) => void posicao(e.target.value as PosicaoVinheta)}>
                  <option value="depois-do-gancho">{tv.posicoes['depois-do-gancho']}</option>
                  <option value="inicio">{tv.posicoes.inicio}</option>
                </select>
              </label>
            )}
          </div>
        </div>
      )}
      {estado?.faltando && <span className="erro-txt">{tv.faltando}</span>}
      <div className="linha">
        <input ref={entrada} type="file" accept="video/*,.mp4,.mov,.m4v,.mkv,.webm" hidden onChange={(e) => enviar(e.target.files?.[0])} />
        <button disabled={enviando} onClick={() => entrada.current?.click()}>{tem ? tv.trocar : tv.cadastrar}</button>
        {tem && <button className="link" disabled={enviando} onClick={() => void remover()}>{tv.remover}</button>}
      </div>
      {msg && <span className={enviando ? 'dica' : 'erro-txt'}>{msg}</span>}
    </div>
  )
}
