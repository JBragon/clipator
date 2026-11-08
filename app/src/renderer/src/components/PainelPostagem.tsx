import { useCallback, useEffect, useState } from 'react'
import type { Api, Job } from '../api'
import { useT } from '../i18n'

type Pacote = {
  plataforma: string
  nome: string
  titulo: string | null
  descricao: string
  hashtags: string[]
  tags: string[]
  legenda: string | null
  thumb: string | null
  fonte: string
  avisos: string[]
}

// Texto de postagem pronto para colar, por plataforma, conferido contra os limites de cada uma.
export function PainelPostagem(props: { api: Api; base: string; clipId: string; jobs: Record<string, Job> }): React.JSX.Element {
  const { api, base, clipId, jobs } = props
  const t = useT()
  const url = `${base}/clips/${encodeURIComponent(clipId)}/postagem`
  const [pacotes, setPacotes] = useState<Record<string, Pacote>>({})
  const [aba, setAba] = useState<string | null>(null)
  const [copiado, setCopiado] = useState('')
  const meus = Object.values(jobs).filter((j) => j.tipo === 'postagem' && j.params.clip === clipId)
  const rodando = meus.find((j) => j.status === 'rodando' || j.status === 'na_fila')
  const fim = meus.filter((j) => j.status === 'ok' || j.status === 'erro').map((j) => j.criado).sort().pop() ?? 0
  const erro = meus.filter((j) => j.status === 'erro').sort((a, b) => b.criado - a.criado)[0]

  const carregar = useCallback(() => {
    api.get<Record<string, Pacote>>(url).then(setPacotes, () => setPacotes({}))
  }, [api, url])
  useEffect(carregar, [carregar, fim])

  const ids = Object.keys(pacotes)
  const atual = pacotes[aba && pacotes[aba] ? aba : ids[0]]

  const copiar = async (rotulo: string, texto: string): Promise<void> => {
    await navigator.clipboard.writeText(texto)
    setCopiado(rotulo)
    setTimeout(() => setCopiado(''), 1500)
  }

  const campo = (rotulo: string, valor: string, limite?: number): React.JSX.Element => (
    <div className="campo-postagem">
      <div className="linha">
        <label>{rotulo}</label>
        {limite !== undefined && <span className="dica">{valor.length}/{limite}</span>}
        <span className="espaco" />
        <button className="link" onClick={() => void copiar(rotulo, valor)}>{copiado === rotulo ? t.copiado : t.copiar}</button>
      </div>
      <pre>{valor || '—'}</pre>
    </div>
  )

  return (
    <div className="campo postagem">
      <label>{t.postagem}</label>
      <div className="linha">
        <button disabled={!!rodando} onClick={() => void api.post(url, {}, { usar_ia: 'false' })}>{t.gerarPostagem}</button>
        <button disabled={!!rodando} onClick={() => void api.post(url, {}, { usar_ia: 'true' })}>{t.gerarPostagemIA}</button>
        {rodando && <span className="chip">{t.status[rodando.status]}</span>}
        {atual && <span className="dica">{t.textoDe(atual.fonte)}</span>}
      </div>
      {erro && erro.criado >= fim && <span className="erro-txt">{erro.erro}</span>}
      {!ids.length && <p className="dica">{t.semPostagem}</p>}
      {ids.length > 0 && (
        <div className="abas-postagem" role="tablist">
          {ids.map((id) => (
            <button key={id} role="tab" aria-selected={atual?.plataforma === id} className={atual?.plataforma === id ? 'ativa' : ''} onClick={() => setAba(id)}>
              {pacotes[id].nome}{pacotes[id].avisos.length ? ' ⚠' : ''}
            </button>
          ))}
        </div>
      )}
      {atual && (
        <>
          {atual.avisos.length > 0 && <ul className="avisos-postagem">{atual.avisos.map((a) => <li key={a}>{a}</li>)}</ul>}
          {atual.titulo !== null && campo(t.titulo, atual.titulo, atual.plataforma.startsWith('youtube') ? 100 : undefined)}
          {campo(t.descricao, atual.descricao)}
          {campo(t.hashtags, atual.hashtags.join(' '))}
          {atual.tags.length > 0 && campo(t.tags, atual.tags.join(', '))}
          <p className="dica">
            {atual.legenda ? `${t.legendaArquivo}: ${atual.legenda}` : t.semLegendaArquivo}
            {atual.thumb ? ` · ${t.thumbnail}: ${atual.thumb}` : ''}
          </p>
        </>
      )}
    </div>
  )
}
