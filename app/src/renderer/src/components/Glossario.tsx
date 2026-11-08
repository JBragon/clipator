import { useEffect, useState } from 'react'
import type { Api } from '../api'
import { useT } from '../i18n'

type Troca = { de: string; para: string; inicio: number }

// Glossário do canal: nomes que o Whisper costuma errar. Vale nas próximas transcrições
// e pode corrigir a transcrição que já existe, sem transcrever de novo.
export function Glossario({ api, canal, base, aoCorrigir }: { api: Api; canal: string; base: string; aoCorrigir(): void }): React.JSX.Element {
  const t = useT()
  const [texto, setTexto] = useState('')
  const [salvo, setSalvo] = useState('')
  const [msg, setMsg] = useState('')
  const [trocas, setTrocas] = useState<Troca[]>([])
  const [ocupado, setOcupado] = useState(false)

  useEffect(() => {
    api.get<{ glossario: string[] }>(`/api/canais/${encodeURIComponent(canal)}/glossario`).then((g) => {
      const v = g.glossario.join('\n')
      setTexto(v)
      setSalvo(v)
    }, () => undefined)
  }, [api, canal])

  const salvar = async (): Promise<void> => {
    const lista = texto.split('\n').map((x) => x.trim()).filter(Boolean)
    const r = await api.put<{ glossario: string[] }>(`/api/canais/${encodeURIComponent(canal)}/glossario`, { glossario: lista })
    const v = r.glossario.join('\n')
    setTexto(v)
    setSalvo(v)
    setMsg(t.glossarioSalvo(r.glossario.length))
  }

  const corrigir = async (): Promise<void> => {
    setOcupado(true)
    try {
      if (texto !== salvo) await salvar()
      const r = await api.post<{ trocas: Troca[] }>(`${base}/transcricao/corrigir-nomes`)
      setTrocas(r.trocas)
      setMsg(r.trocas.length ? t.nomesCorrigidos(r.trocas.length) : t.nenhumNomeCorrigido)
      if (r.trocas.length) aoCorrigir()
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e))
    } finally {
      setOcupado(false)
    }
  }

  return (
    <details className="glossario">
      <summary>{t.glossarioCanal}{salvo ? ` · ${salvo.split('\n').length}` : ''}</summary>
      <p className="dica">{t.glossarioDica}</p>
      <textarea rows={5} value={texto} placeholder={t.glossarioExemplo} onChange={(e) => setTexto(e.target.value)} />
      <div className="linha">
        <button disabled={texto === salvo} onClick={() => void salvar()}>{t.salvar}</button>
        <button disabled={ocupado || !texto.trim()} onClick={() => void corrigir()}>{t.corrigirNomes}</button>
        {msg && <span className="dica">{msg}</span>}
      </div>
      {trocas.length > 0 && (
        <ul className="lista-trocas">
          {trocas.slice(0, 12).map((x, i) => <li key={i}><s>{x.de}</s> → <strong>{x.para}</strong></li>)}
          {trocas.length > 12 && <li className="dica">+{trocas.length - 12}</li>}
        </ul>
      )}
    </details>
  )
}
