import { useEffect, useState } from 'react'
import type { Api, Clip, Job } from '../api'
import { useT } from '../i18n'
import { ponte } from '../ponte'
import { PainelPostagem } from './PainelPostagem'

// Passo 5: o usuário escolhe os clips renderizados que vai publicar e, para cada um, gera e ajusta
// o texto de cada plataforma (PainelPostagem), com a thumb e a legenda .srt ao lado.
export function PassoPublicacao(props: { api: Api; base: string; clips: Clip[]; jobs: Record<string, Job>; raiz: string; irParaClips(): void }): React.JSX.Element {
  const { api, base, clips, jobs, raiz, irParaClips } = props
  const t = useT()
  const prontos = clips.filter((c) => c.saida)
  const chave = `clipator.publicacao.${base}`
  const [marcados, setMarcados] = useState<Set<string>>(() => {
    try {
      const salvo = localStorage.getItem(chave)
      if (salvo) return new Set(JSON.parse(salvo) as string[])
    } catch {
      /* sem armazenamento */
    }
    return new Set(prontos.map((c) => c.id))
  })
  useEffect(() => {
    try {
      localStorage.setItem(chave, JSON.stringify([...marcados]))
    } catch {
      /* sem armazenamento */
    }
  }, [marcados, chave])

  if (!prontos.length) {
    return (
      <div className="passo-publicacao">
        <p className="dica">{t.pubSemClips}</p>
        <div><button onClick={irParaClips}>{t.pubIrClips}</button></div>
      </div>
    )
  }
  const alternar = (id: string): void => {
    const n = new Set(marcados)
    if (n.has(id)) n.delete(id)
    else n.add(id)
    setMarcados(n)
  }
  return (
    <div className="passo-publicacao">
      <div>
        <h3 style={{ margin: '0 0 4px' }}>{t.pubTitulo}</h3>
        <p className="dica" style={{ margin: 0 }}>{t.pubDica}</p>
      </div>
      <div className="linha" style={{ flexWrap: 'wrap' }}>
        <div className="pub-lista">
          {prontos.map((c) => (
            <label key={c.id} className={`chip-filtro ${marcados.has(c.id) ? 'ativo' : ''}`}>
              <input type="checkbox" checked={marcados.has(c.id)} onChange={() => alternar(c.id)} /> {c.titulo || c.id}
            </label>
          ))}
        </div>
        <button className="link" onClick={() => setMarcados(new Set(prontos.map((c) => c.id)))}>{t.pubTodos}</button>
        <button className="link" onClick={() => setMarcados(new Set())}>{t.pubNenhum}</button>
      </div>
      {prontos.filter((c) => marcados.has(c.id)).map((c) => {
        const saida = c.versao ? `${c.pasta}/${c.versao}` : `${c.pasta}/saida.mp4`
        return (
          <div key={c.id} className="pub-clip">
            <div className="midia">
              <img src={api.midia(`${c.pasta}/thumb.png`, String(Date.now() >> 16))} alt={t.pubSemThumb}
                onError={(ev) => (ev.currentTarget.style.display = 'none')} />
              <video src={api.midia(saida)} controls preload="none" />
              <button className="link" onClick={() => void ponte.abrir(`${raiz}/${c.pasta}/legenda.srt`)}>📄 {t.pubLegenda}</button>
              <button className="link" onClick={() => void ponte.mostrarNaPasta(`${raiz}/${saida}`)}>{t.pubMostrar}</button>
            </div>
            <div>
              <strong>{c.titulo || c.id}</strong>
              <RevisaoClip api={api} base={base} clipId={c.id} jobs={jobs} />
              <PainelPostagem api={api} base={base} clipId={c.id} jobs={jobs} />
            </div>
          </div>
        )
      })}
    </div>
  )
}

type Revisao = { nota: number; fonte: string; aviso?: string; feito_em?: string
  criterios: { nome: string; nota: number; max: number; comentario: string }[]
  problemas: { segundo: number | null; texto: string; gravidade: string }[]
  alertas: { segundo: number | null; trecho: string; motivo: string }[] }

// Revisão antes de publicar: nota de 0 a 100, o que corrigir e o que precisa de fonte (com IA ou pelas regras)
function RevisaoClip(props: { api: Api; base: string; clipId: string; jobs: Record<string, Job> }): React.JSX.Element {
  const { api, base, clipId, jobs } = props
  const t = useT()
  const r = t.rev
  const url = `${base}/clips/${encodeURIComponent(clipId)}/revisao`
  const [rev, setRev] = useState<Revisao | null>(null)
  const [jobId, setJobId] = useState<string | null>(null)
  const job = jobId ? jobs[jobId] : undefined
  useEffect(() => { api.get<{ revisao: Revisao | null }>(url).then((x) => setRev(x.revisao), () => undefined) }, [api, url])
  useEffect(() => {
    if (job && (job.status === 'ok' || job.status === 'erro')) {
      if (job.status === 'ok') setRev(job.resultado as unknown as Revisao)
      setJobId(null)
    }
  }, [job?.status]) // eslint-disable-line react-hooks/exhaustive-deps
  const cor = (n: number): string => (n >= 80 ? 'var(--ok)' : n >= 60 ? 'var(--nota-media)' : 'var(--erro)')
  return (
    <details className="revisao-clip" open={!!rev || undefined}>
      <summary>
        ✅ {r.titulo} {rev && <span className="nota-revisao" style={{ background: cor(rev.nota) }}>{rev.nota}</span>}
        {rev && <span className="dica"> · {rev.fonte === 'regras' ? r.porRegras : r.porIA(rev.fonte)}</span>}
      </summary>
      <div className="linha">
        <button disabled={!!job} onClick={() => void api.post<{ job: string }>(url).then((x) => setJobId(x.job))}>
          {job ? `${Math.round(job.progresso * 100)}%` : rev ? r.deNovo : r.revisar}
        </button>
        <span className="dica">{r.dica}</span>
      </div>
      {rev?.aviso && <p className="dica">{rev.aviso}</p>}
      {rev && (
        <>
          <ul className="criterios-revisao">
            {rev.criterios.map((c) => <li key={c.nome}><b>{c.nome}</b> {c.nota}/{c.max} <span className="dica">{c.comentario}</span></li>)}
          </ul>
          {rev.problemas.length > 0 && (
            <>
              <strong>{r.corrigir}</strong>
              <ul className="problemas-revisao">
                {rev.problemas.map((p, k) => <li key={k} className={p.gravidade}>{p.segundo != null ? `${p.segundo.toFixed(1)} s · ` : ''}{p.texto}</li>)}
              </ul>
            </>
          )}
          {rev.alertas.length > 0 && (
            <>
              <strong>{r.fontes}</strong>
              <ul className="problemas-revisao">
                {rev.alertas.map((a, k) => <li key={k}>{a.segundo != null ? `${a.segundo.toFixed(1)} s · ` : ''}“{a.trecho}” — {a.motivo}</li>)}
              </ul>
            </>
          )}
        </>
      )}
    </details>
  )
}
