// Thumbnails do clip: gera as variações por código (e por imagem com o Codex),
// mostra a grade e copia a escolhida para thumb.png.
import { useCallback, useEffect, useState } from 'react'
import type { Api, Job } from '../api'
import { useT } from '../i18n'
import { ponte } from '../ponte'

type Info = {
  variacoes: string[]
  ia: string[]
  quadros: { arquivo: string; tempo: number; rosto: boolean }[]
  linhas?: string[]
  destaques?: string[]
  fonte_frase?: string
  detalhes?: Record<string, { tipo: string; linhas: string[]; prova: string; layout: string }>
  tamanho?: [number, number]
  escolhida: boolean
  pasta: string
}

export function Thumbs(props: { api: Api; base: string; clipId: string; jobs: Record<string, Job>; raiz: string }): React.JSX.Element {
  const { api, base, clipId, jobs, raiz } = props
  const t = useT()
  const url = `${base}/clips/${encodeURIComponent(clipId)}/thumbs`
  const [info, setInfo] = useState<Info | null>(null)
  const [frase, setFrase] = useState('')
  const [msg, setMsg] = useState('')
  const [versao, setVersao] = useState(0)

  const meus = Object.values(jobs).filter((j) => (j.tipo === 'thumbnail' || j.tipo === 'thumbnail_ia') && j.params.clip === clipId)
  const rodando = meus.find((j) => j.status === 'rodando' || j.status === 'na_fila')
  const ultimoFim = meus.filter((j) => j.status === 'ok' || j.status === 'erro').map((j) => j.criado).sort().pop() ?? 0
  const ultimoErro = meus.filter((j) => j.status === 'erro').sort((a, b) => b.criado - a.criado)[0]

  const carregar = useCallback(async () => {
    try {
      const i = await api.get<Info>(url)
      setInfo(i)
      // a caixa mostra só a frase que você escreveu; vazia, o motor gera insights e sensacionalistas
      setFrase((atual) => atual || (i.fonte_frase === 'clip' ? (i.linhas ?? []).join('\n') : ''))
      setVersao(Date.now())
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e))
    }
  }, [api, url])

  useEffect(() => {
    void carregar()
  }, [carregar, ultimoFim])

  const gerar = async (): Promise<void> => {
    setMsg('')
    // lista vazia apaga a frase própria do clip e volta para as variações da transcrição
    const linhas = frase.split('\n').map((x) => x.trim()).filter(Boolean)
    await api.post(url, { usar_ia: true, linhas })
  }

  const porImagem = async (): Promise<void> => {
    setMsg('')
    await api.post(`${url}/ia`)
  }

  const escolher = async (arquivo: string): Promise<void> => {
    await api.post(`${url}/escolher`, { arquivo })
    await carregar()
  }

  const todas = [...(info?.variacoes ?? []), ...(info?.ia ?? [])]
  // variações agrupadas pela origem da frase; as antigas, sem detalhes, ficam em "outras"
  const ordemGrupos = ['sua', 'insight', 'sensacionalista', 'outras', 'ia']
  const grupos: Record<string, string[]> = {}
  for (const v of info?.variacoes ?? []) (grupos[info?.detalhes?.[v]?.tipo ?? 'outras'] ??= []).push(v)
  if (info?.ia.length) grupos.ia = info.ia
  const proporcao = info?.tamanho ? `${info.tamanho[0]} / ${info.tamanho[1]}` : undefined

  return (
    <div className="campo thumbs">
      <label>{t.thumbnail}</label>
      <div className="linha" style={{ alignItems: 'flex-start' }}>
        {info?.escolhida && (
          <img className="thumb-escolhida" style={{ aspectRatio: proporcao }} src={api.midia(`${info.pasta}/thumb.png`, String(versao))} alt="thumb.png" />
        )}
        <div className="campo" style={{ flex: 1 }}>
          <textarea rows={4} value={frase} placeholder={t.fraseThumbDica} onChange={(e) => setFrase(e.target.value)} />
          <div className="linha">
            <button className="primario" disabled={!!rodando} onClick={() => void gerar()}>
              {todas.length ? t.gerarThumbsDeNovo : t.gerarThumbs}
            </button>
            <button disabled={!!rodando} title={t.thumbPorImagemDica} onClick={() => void porImagem()}>{t.thumbPorImagem}</button>
            {rodando && <span className="chip">{Math.round(rodando.progresso * 100)}% {rodando.mensagem}</span>}
            {info?.fonte_frase && <span className="dica">{t.fraseDe(info.fonte_frase)}</span>}
          </div>
          {ultimoErro && ultimoErro.criado >= ultimoFim && <span className="erro-txt">{ultimoErro.erro}</span>}
          <span className="dica">{msg}</span>
        </div>
      </div>
      {ordemGrupos.filter((g) => grupos[g]?.length).map((g) => (
        <div key={g} className="grupo-thumbs">
          <span className="rotulo-grupo">{t.gruposThumb[g] ?? g}</span>
          <div className={`grade-thumbs ${info?.tamanho && info.tamanho[1] > info.tamanho[0] ? 'vertical' : ''}`}>
            {grupos[g].map((v) => {
              const d = info?.detalhes?.[v]
              return (
                <button key={v} className="thumb-opcao" title={d?.prova ? `${t.provaThumb}: “${d.prova}”` : v} onClick={() => void escolher(v)}>
                  <img src={api.midia(`${info?.pasta}/thumbs/${v}`, String(versao))} alt={d?.linhas.join(' ') ?? v} loading="lazy"
                    style={{ aspectRatio: g === 'ia' ? undefined : proporcao }} />
                </button>
              )
            })}
          </div>
        </div>
      ))}
      {info?.escolhida && (
        <button className="link" onClick={() => void ponte.mostrarNaPasta(`${raiz}/${info.pasta}/thumb.png`)}>{t.mostrarNaPasta}</button>
      )}
    </div>
  )
}
