import { useState } from 'react'
import type { Api, Job } from '../api'
import { useT } from '../i18n'

const NOMES: Record<string, string> = { claude: 'Claude', codex: 'Codex' }

// Job parado porque a IA perdeu o login: entrar de novo (e o job segue por ela) ou usar a outra IA.
export function AvisoLogin({ api, job }: { api: Api; job: Job }): React.JSX.Element | null {
  const t = useT()
  const [msg, setMsg] = useState('')
  if (!job.aguardando?.startsWith('login_')) return null
  const ia = job.aguardando.slice('login_'.length)
  const outra = ia === 'claude' ? 'codex' : 'claude'

  const entrar = async (): Promise<void> => {
    try {
      await api.post(`/api/agentes/${ia}/login`)
      setMsg(t.loginAberto(NOMES[ia] ?? ia))
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e))
    }
  }

  return (
    <div className="aviso-login" onClick={(e) => e.stopPropagation()}>
      <span>{t.aguardandoLogin(NOMES[ia] ?? ia)}</span>
      <div className="linha">
        <button className="primario" onClick={() => void entrar()}>{t.entrarNo(NOMES[ia] ?? ia)}</button>
        <button onClick={() => void api.post(`/api/jobs/${job.id}/usar-outra-ia`)}>{t.usarOutraIa(NOMES[outra])}</button>
      </div>
      {msg && <span className="dica">{msg}</span>}
    </div>
  )
}
