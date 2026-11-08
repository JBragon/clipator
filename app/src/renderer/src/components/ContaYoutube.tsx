import { useEffect, useState } from 'react'
import type { Api, Job } from '../api'
import { useT } from '../i18n'

export type EstadoConta = { conectada: boolean; navegador: string | null; atualizada_em: number | null }

// Conectar a conta do YouTube: o motor abre o Chrome (ou o Edge) com um perfil só do Clipator, a
// pessoa entra nele, e os cookies desse perfil vão para o yt-dlp. Com `canal` e `projeto`, o download
// daquele projeto recomeça sozinho quando a conta conecta.
export function useContaYoutube(api: Api, jobs: Record<string, Job>, aoConectar?: () => void): {
  estado: EstadoConta | null
  conectando: boolean
  msg: string
  falhouChrome: boolean // o login no Chrome/Edge não deu certo: o Firefox vira o botão principal
  conectar(canal?: string, projeto?: string): Promise<void>
  continuar(): Promise<void>
  firefox(canal?: string, projeto?: string): Promise<void>
  desconectar(): Promise<void>
} {
  const t = useT()
  const [estado, setEstado] = useState<EstadoConta | null>(null)
  const [job, setJob] = useState<string | null>(null)
  const [msg, setMsg] = useState('')
  const [falhouChrome, setFalhou] = useState(() => {
    try {
      return localStorage.getItem('clipator.yt.chromeFalhou') === '1'
    } catch {
      return false
    }
  })
  const marcarFalha = (f: boolean): void => {
    setFalhou(f)
    try {
      localStorage.setItem('clipator.yt.chromeFalhou', f ? '1' : '0')
    } catch {
      /* sem armazenamento */
    }
  }
  const recarregar = (): void => {
    api.get<EstadoConta>('/api/youtube/conta').then(setEstado, () => setEstado(null))
  }
  useEffect(recarregar, [api]) // eslint-disable-line react-hooks/exhaustive-deps

  const j = job ? jobs[job] : undefined
  useEffect(() => {
    if (!j || (j.status !== 'ok' && j.status !== 'erro' && j.status !== 'cancelado')) return
    setJob(null)
    recarregar()
    const r = (j.resultado ?? {}) as { conectada?: boolean; motivo?: string; firefox?: boolean; cancelado?: boolean }
    if (j.status === 'ok' && r.firefox && !r.cancelado) {
      setMsg(t.ytFirefoxPronto)
      aoConectar?.()
    } else if (j.status === 'ok' && r.conectada) {
      setMsg(t.ytConectou)
      marcarFalha(false)
      aoConectar?.()
    } else {
      setMsg(j.erro || r.motivo || t.ytNaoEntrou)
      if (!r.firefox && !r.cancelado) marcarFalha(true)
    }
  }, [j?.status]) // eslint-disable-line react-hooks/exhaustive-deps

  return {
    estado,
    conectando: !!job,
    msg,
    falhouChrome,
    conectar: async (canal, projeto) => {
      setMsg('')
      const q: Record<string, string> = {}
      if (canal && projeto) Object.assign(q, { canal, projeto })
      const r = await api.post<{ job: string }>('/api/youtube/conta', {}, q)
      setJob(r.job)
    },
    continuar: async () => {
      await api.post('/api/youtube/continuar')
    },
    firefox: async (canal, projeto) => {
      setMsg('')
      const q: Record<string, string> = {}
      if (canal && projeto) Object.assign(q, { canal, projeto })
      const r = await api.post<{ job: string }>('/api/youtube/firefox', {}, q)
      setJob(r.job)
    },
    desconectar: async () => {
      setEstado(await api.del<EstadoConta>('/api/youtube/conta'))
      setMsg('')
    }
  }
}
