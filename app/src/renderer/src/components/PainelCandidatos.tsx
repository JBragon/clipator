import { useEffect, useState } from 'react'
import { hms, proj, type Api, type Candidato, type Estilo } from '../api'
import { useT } from '../i18n'
import type { ProjetoRef } from '../App'

type Props = {
  api: Api
  projeto: ProjetoRef | null
  versao: number
  selecionados: Set<string>
  setSelecionados(s: Set<string>): void
  focar(t: number): void
  aposCriar(): void
}

export function PainelCandidatos({ api, projeto, versao, selecionados, setSelecionados, focar, aposCriar }: Props): React.JSX.Element {
  const t = useT()
  const [cands, setCands] = useState<Candidato[]>([])
  const [estilos, setEstilos] = useState<Estilo[]>([])
  const [focado, setFocado] = useState<string | null>(null)
  const [formato, setFormato] = useState('')
  const [estilo, setEstilo] = useState('')
  const [cartela, setCartela] = useState(true)
  const [msg, setMsg] = useState('')

  useEffect(() => {
    if (!projeto) return setCands([])
    api.get<Candidato[]>(`${proj(projeto.canal, projeto.projeto)}/candidatos`).then(setCands, () => setCands([]))
    api.get<Estilo[]>('/api/estilos', { canal: projeto.canal }).then(setEstilos, () => setEstilos([]))
  }, [api, projeto, versao])

  const alternar = (id: string): void => {
    const n = new Set(selecionados)
    if (n.has(id)) n.delete(id)
    else n.add(id)
    setSelecionados(n)
  }

  const criar = async (renderizar: boolean): Promise<void> => {
    if (!projeto) return
    const base = proj(projeto.canal, projeto.projeto)
    try {
      const clips = await api.post<{ id: string }[]>(`${base}/selecionar`, {
        ids: [...selecionados],
        formato: formato || null,
        estilo: estilo || null,
        cartela
      })
      if (renderizar) await api.post(`${base}/renderizar`, { clips: clips.map((c) => c.id) })
      setMsg('')
      setSelecionados(new Set())
      aposCriar()
    } catch (e) {
      setMsg((e instanceof Error ? e.message : String(e)))
    }
  }

  const cor = (n: number): string => (n >= 65 ? 'var(--nota-alta)' : n >= 45 ? 'var(--nota-media)' : 'var(--nota-baixa)')

  return (
    <aside className="painel direita">
      <h2>
        {t.candidatos}
        <span className="espaco" />
        {cands.length > 0 && <span>{cands.length}</span>}
      </h2>
      <div className="rolagem">
        {!projeto && <p className="dica" style={{ padding: 10 }}>{t.semCandidatos}</p>}
        {projeto && !cands.length && <p className="dica" style={{ padding: 10 }}>{t.aguardandoAnalise}</p>}
        {cands.map((c) => (
          <div
            key={c.id}
            className={`cand ${focado === c.id ? 'focado' : ''}`}
            onClick={() => {
              setFocado(c.id)
              focar(c.inicio)
            }}
          >
            <input type="checkbox" checked={selecionados.has(c.id)} onClick={(e) => e.stopPropagation()} onChange={() => alternar(c.id)} aria-label={c.id} />
            <div style={{ minWidth: 0 }}>
              <div className="titulo">{(c.titulos ?? [])[0] ?? c.id}</div>
              <div className="meta">
                {hms(c.inicio)}–{hms(c.fim)} · {Math.round(c.duracao)}
                {t.segundos}
                {c.modo === 'longo' ? ` · ${t.longo}` : ''}
                {c.ia ? ` · ${c.ia.agente}` : ''}
              </div>
              {focado === c.id && (
                <>
                  <ul className="motivos" title={t.porqueNota}>
                    {c.ia?.motivo && <li>{c.ia.motivo}</li>}
                    {c.motivos.map((m) => <li key={m}>{m}</li>)}
                  </ul>
                  <p className="meta" style={{ margin: '4px 0 0' }}>{c.texto.slice(0, 400)}{c.texto.length > 400 ? '…' : ''}</p>
                </>
              )}
            </div>
            <span className="nota" style={{ color: cor(c.nota) }} title={c.nota_local !== undefined ? `local ${c.nota_local.toFixed(0)}` : ''}>
              {c.nota.toFixed(0)}
            </span>
          </div>
        ))}
      </div>
      {projeto && cands.length > 0 && (
        <div className="barra-acoes">
          <span className="dica">{t.selecionados(selecionados.size)}</span>
          <div className="linha">
            <select value={formato} onChange={(e) => setFormato(e.target.value)} aria-label={t.formato}>
              <option value="">{t.formato}: auto</option>
              {['9:16', '1:1', '4:5', '16:9'].map((f) => <option key={f}>{f}</option>)}
            </select>
            <select value={estilo} onChange={(e) => setEstilo(e.target.value)} aria-label={t.estilo}>
              <option value="">{t.estilo}: auto</option>
              {estilos.map((e) => <option key={e.id} value={e.id}>{e.nome}</option>)}
            </select>
          </div>
          <label className="linha">
            <input type="checkbox" checked={cartela} onChange={(e) => setCartela(e.target.checked)} /> {t.cartela}
          </label>
          <div className="linha">
            <button disabled={!selecionados.size} onClick={() => void criar(false)}>{t.criarClips}</button>
            <button className="primario" disabled={!selecionados.size} onClick={() => void criar(true)}>{t.renderizarSelecionados}</button>
          </div>
          {msg && <span className="erro-txt">{msg}</span>}
        </div>
      )}
    </aside>
  )
}
