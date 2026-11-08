import { useEffect, useRef, useState } from 'react'
import type { Api, Job } from '../api'
import { useT } from '../i18n'

// Os passos de um job ao vivo (o log que o motor vai escrevendo): o pedido para a IA, "pensando… 12 s",
// o texto que ela vai produzindo (✎), o raciocínio (💭), o que foi aceito ou descartado e as etapas do render.
export function RelatoJob(props: { api: Api; job: Job; aberto?: boolean }): React.JSX.Element | null {
  const { api, job } = props
  const t = useT()
  const [antes, setAntes] = useState<string[]>([]) // o que já estava no log antes de a tela abrir
  const lista = useRef<HTMLOListElement>(null)
  useEffect(() => {
    api.get<Job>(`/api/jobs/${job.id}`).then((j) => setAntes((j.log ?? '').split('\n').filter(Boolean)), () => undefined)
  }, [api, job.id])
  const vivas = job.linhas ?? []
  // junta sem repetir: o log do motor tem a hora na frente, as linhas ao vivo não
  const semHora = (l: string): string => l.replace(/^\d\d:\d\d:\d\d /, '')
  const vistas = new Set(antes.map(semHora))
  const linhas = [...antes.map(semHora), ...vivas.filter((l) => !vistas.has(l))].slice(-200)
  useEffect(() => {
    const el = lista.current
    if (el) el.scrollTop = el.scrollHeight
  }, [linhas.length])
  if (!linhas.length && !job.mensagem) return null
  return (
    <details className="relato-job" open={props.aberto ?? true}>
      <summary>
        <span className="dica">{t.relato.titulo(linhas.length)}</span>
        {job.mensagem && <span className="mensagem-viva"> · {job.mensagem.replace(/^[\w-]+: /, '')}</span>}
      </summary>
      <ol ref={lista}>
        {linhas.map((l, k) => (
          <li key={k} className={l.startsWith('✎') ? 'texto-ia' : l.startsWith('💭') ? 'pensando-ia' : l.startsWith('•') ? 'passo' : ''}>{l}</li>
        ))}
      </ol>
    </details>
  )
}
