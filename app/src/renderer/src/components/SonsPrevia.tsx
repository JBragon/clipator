import { useEffect, useRef, useState } from 'react'
import type { Api } from '../api'
import { useT } from '../i18n'

// Os efeitos sintetizados no motor, para ouvir antes de pôr no campo `sons` do estilo.
export function SonsPrevia({ api }: { api: Api }): React.JSX.Element {
  const t = useT()
  const [nomes, setNomes] = useState<string[]>([])
  const audio = useRef<HTMLAudioElement | null>(null)

  useEffect(() => {
    api.get<{ sons: string[] }>('/api/sons').then((r) => setNomes(r.sons), () => setNomes([]))
  }, [api])

  const tocar = (nome: string): void => {
    audio.current?.pause()
    audio.current = new Audio(api.url(`/api/sons/${nome}`, { token: api.token }))
    void audio.current.play().catch(() => undefined)
  }

  if (!nomes.length) return <></>
  return (
    <div className="campo sons-previa">
      <label>{t.efeitosSonoros}</label>
      <div className="linha">
        {nomes.map((n) => <button key={n} className="chip" onClick={() => tocar(n)}>▶ {n}</button>)}
      </div>
      <span className="dica">{t.efeitosSonorosDica}</span>
    </div>
  )
}
