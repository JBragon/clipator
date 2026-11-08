import { useEffect, useRef, useState } from 'react'
import type { Api, Job } from '../api'
import { useT } from '../i18n'
import { AvisoLogin } from './AvisoLogin'

// Etapas da análise na ordem em que o motor as informa (pipeline.analisar).
const ETAPAS_ANALISE = ['ingestao', 'audio', 'transcricao', 'sinais', 'candidatos', 'ranking']

function useAgora(ativo: boolean): number {
  const [agora, setAgora] = useState(() => Date.now() / 1000)
  useEffect(() => {
    if (!ativo) return
    const id = setInterval(() => setAgora(Date.now() / 1000), 1000)
    return () => clearInterval(id)
  }, [ativo])
  return agora
}

export function duracaoCurta(s: number): string {
  if (!isFinite(s) || s < 0) return '—'
  if (s < 60) return `${Math.round(s)} s`
  if (s < 3600) return `${Math.floor(s / 60)} min ${Math.round(s % 60)} s`
  return `${Math.floor(s / 3600)} h ${Math.round((s % 3600) / 60)} min`
}

// Tempo restante pela velocidade da etapa atual: o quanto o progresso geral andou desde que ela começou.
function restante(job: Job, agora: number): number | null {
  if (job.status !== 'rodando' || job.aguardando) return null
  const ini = job.etapa_iniciado ?? job.iniciado ?? job.criado
  const p0 = job.etapa_iniciado ? (job.etapa_progresso_inicial ?? 0) : 0
  const dt = agora - ini
  const dp = job.progresso - p0
  if (dt < 5 || dp < 0.002) return null
  return ((1 - job.progresso) * dt) / dp
}

const ehErro = (linha: string): boolean => /traceback|error|erro|exception|falhou/i.test(linha)

// Log do job, recolhido até pedir: atualiza sozinho, rola para o fim e destaca as linhas de erro.
export function LogJob({ api, job }: { api: Api; job: Job }): React.JSX.Element {
  const t = useT()
  const [aberto, setAberto] = useState(false)
  const [texto, setTexto] = useState('')
  const [copiado, setCopiado] = useState(false)
  const caixa = useRef<HTMLPreElement>(null)
  const ativo = job.status === 'rodando' || job.status === 'na_fila'

  useEffect(() => {
    if (!aberto) return
    let vivo = true
    const ler = (): void => {
      api.get<Job>(`/api/jobs/${job.id}`).then((j) => vivo && setTexto([j.log, j.erro].filter(Boolean).join('\n')), () => undefined)
    }
    ler()
    const id = ativo ? setInterval(ler, 2000) : undefined
    return () => {
      vivo = false
      if (id) clearInterval(id)
    }
  }, [api, job.id, aberto, ativo, job.status])

  useEffect(() => {
    if (caixa.current) caixa.current.scrollTop = caixa.current.scrollHeight
  }, [texto])

  const copiar = async (): Promise<void> => {
    await navigator.clipboard.writeText(texto)
    setCopiado(true)
    setTimeout(() => setCopiado(false), 1500)
  }

  return (
    <div className="log-job" onClick={(e) => e.stopPropagation()}>
      <button className="link" onClick={() => setAberto(!aberto)}>{aberto ? `▾ ${t.ocultarDetalhes}` : `▸ ${t.verDetalhes}`}</button>
      {aberto && (
        <>
          <button className="link" onClick={() => void copiar()} disabled={!texto}>{copiado ? t.copiado : t.copiar}</button>
          <pre ref={caixa} className="log">
            {texto
              ? texto.split('\n').map((l, i) => <div key={i} className={ehErro(l) ? 'linha-erro' : ''}>{l || ' '}</div>)
              : '—'}
          </pre>
        </>
      )}
    </div>
  )
}

// Painel grande da tela do projeto: barra geral, etapas, ação atual, tempo e os botões do job.
export function ProgressoJob({ api, job }: { api: Api; job: Job }): React.JSX.Element {
  const t = useT()
  const ativo = job.status === 'rodando' || job.status === 'na_fila'
  const agora = useAgora(ativo)
  const pct = Math.round(job.progresso * 100)
  const falta = restante(job, agora)
  const decorrido = Math.max(0, agora - (job.iniciado ?? job.criado))
  const passos = job.tipo === 'analisar'
    ? ETAPAS_ANALISE
    : job.tipo === 'renderizar'
      ? ((job.params.clips as string[] | undefined) ?? [String(job.params.clip ?? '')]).filter(Boolean)
      : []
  const iAtual = job.etapa ? passos.indexOf(job.etapa) : job.status === 'ok' ? passos.length : -1

  const estado = (i: number): string => {
    if (job.status === 'ok' || i < iAtual) return 'feita'
    if (i > iAtual) return 'pendente'
    if (job.status === 'erro') return 'erro'
    if (job.aguardando) return 'aguardando'
    return 'atual'
  }

  return (
    <div className={`progresso-job ${job.status} ${job.aguardando ? 'aguardando' : ''}`}>
      <div className="linha-topo">
        <strong>{t.tiposJob[job.tipo] ?? job.tipo}</strong>
        <span className="msg">
          {job.status === 'erro' ? job.erro : job.status === 'na_fila' ? t.status.na_fila : job.aguardando ? t.aguardandoLoginCurto : job.mensagem}
        </span>
        <span className="espaco" />
        {ativo && (
          <span className="tempos">
            {t.decorrido} {duracaoCurta(decorrido)} · {falta === null ? t.calculando : `${t.faltaCerca} ${duracaoCurta(falta)}`}
          </span>
        )}
        <span className="pct">{pct}%</span>
        {ativo && <button onClick={() => void api.post(`/api/jobs/${job.id}/cancelar`)}>{t.cancelarJob}</button>}
      </div>
      <div className="barra"><div style={{ width: `${pct}%` }} /></div>
      {passos.length > 0 && (
        <ol className="passos">
          {passos.map((p, i) => {
            const e = estado(i)
            return (
              <li key={p} className={e}>
                <span className="bolinha">{e === 'feita' ? '✓' : e === 'erro' ? '!' : i + 1}</span>
                <span className="nome">{t.etapas[p] ?? p}</span>
                {e === 'atual' && <span className="dica">{Math.round((job.progresso_etapa ?? 0) * 100)}%</span>}
                {e === 'aguardando' && <span className="dica">{t.aguardandoLoginCurto}</span>}
                {e === 'atual' && <span className="mini-barra"><span style={{ width: `${Math.round((job.progresso_etapa ?? 0) * 100)}%` }} /></span>}
              </li>
            )
          })}
        </ol>
      )}
      <AvisoLogin api={api} job={job} />
      <LogJob api={api} job={job} />
    </div>
  )
}

// Anel discreto no topo quando há trabalho rodando em outro projeto; clicar abre esse projeto.
export function ProgressoGlobal(props: {
  jobs: Record<string, Job>
  projetoAtivo: { canal: string; projeto: string } | null
  abrirProjeto(canal: string, projeto: string): void
}): React.JSX.Element | null {
  const { jobs, projetoAtivo, abrirProjeto } = props
  const t = useT()
  const ativos = Object.values(jobs)
    .filter((j) => j.status === 'rodando' || j.status === 'na_fila')
    .filter((j) => !(projetoAtivo && j.params.canal === projetoAtivo.canal && j.params.projeto === projetoAtivo.projeto))
    .sort((a, b) => (a.status === 'rodando' ? -1 : 1) - (b.status === 'rodando' ? -1 : 1) || a.criado - b.criado)
  if (!ativos.length) return null
  const j = ativos[0]
  const pct = Math.round(j.progresso * 100)
  const r = 9
  const volta = 2 * Math.PI * r
  const canal = String(j.params.canal ?? '')
  const projeto = String(j.params.projeto ?? '')
  return (
    <button
      className={`progresso-global ${j.aguardando ? 'aguardando' : ''}`}
      onClick={() => canal && projeto && abrirProjeto(canal, projeto)}
      title={`${t.tiposJob[j.tipo] ?? j.tipo} · ${projeto} · ${j.mensagem}`}
    >
      <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="12" cy="12" r={r} className="anel-fundo" />
        <circle cx="12" cy="12" r={r} className="anel" strokeDasharray={volta} strokeDashoffset={volta * (1 - j.progresso)} transform="rotate(-90 12 12)" />
      </svg>
      <span>{pct}%</span>
      <span className="dica">{projeto.slice(0, 24)}</span>
      {ativos.length > 1 && <span className="dica">+{ativos.length - 1}</span>}
    </button>
  )
}
