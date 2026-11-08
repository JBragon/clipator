import { useState } from 'react'
import type { Api, Job } from '../api'
import { useT } from '../i18n'
import { AvisoLogin } from './AvisoLogin'
import { LogJob } from './BarraProgresso'

// Lista compacta de todos os jobs; o progresso detalhado fica na tela de cada projeto.
export function PainelJobs({ api, jobs }: { api: Api; jobs: Record<string, Job> }): React.JSX.Element {
  const t = useT()
  const [aberto, setAberto] = useState(false)
  const lista = Object.values(jobs).sort((a, b) => b.criado - a.criado).slice(0, 30)
  const rodando = lista.filter((j) => j.status === 'rodando').length

  return (
    <section className={`jobs ${aberto ? '' : 'fechado'}`}>
      <h2 className="jobs-titulo" onClick={() => setAberto(!aberto)}>
        {aberto ? '▾' : '▸'} {t.jobs}
        {rodando > 0 && <span className="dica"> · {rodando} {t.status.rodando}</span>}
      </h2>
      <div className="rolagem">
        {!lista.length && <p className="dica" style={{ padding: '0 10px' }}>{t.semJobs}</p>}
        {lista.map((j) => (
          <div key={j.id} className={`job ${j.status}`}>
            <span className="nome">{t.tiposJob[j.tipo] ?? j.tipo}</span>
            <span className="dica projeto">{String(j.params.projeto ?? '')}</span>
            <span className="prog"><div style={{ width: `${Math.round(j.progresso * 100)}%` }} /></span>
            <span className="pct">{j.status === 'rodando' ? `${Math.round(j.progresso * 100)}%` : t.status[j.status] ?? j.status}</span>
            {j.status === 'rodando' || j.status === 'na_fila' ? (
              <button onClick={() => void api.post(`/api/jobs/${j.id}/cancelar`)}>{t.cancelarJob}</button>
            ) : (
              <span />
            )}
            <span className="msg">{j.erro ?? j.mensagem}</span>
            <AvisoLogin api={api} job={j} />
            <LogJob api={api} job={j} />
          </div>
        ))}
      </div>
    </section>
  )
}
