import { useEffect, useState } from 'react'
import type { Api } from '../api'
import { useT } from '../i18n'
import { ponte } from '../ponte'

type Canal = { slug: string; nome: string }

export function Modal({ titulo, children, fechar }: { titulo: string; children: React.ReactNode; fechar(): void }): React.JSX.Element {
  useEffect(() => {
    const f = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') fechar()
    }
    window.addEventListener('keydown', f)
    return () => window.removeEventListener('keydown', f)
  }, [fechar])
  return (
    <div className="modal-fundo" onMouseDown={(e) => e.target === e.currentTarget && fechar()}>
      <div className="modal" role="dialog" aria-label={titulo}>
        <h3>{titulo}</h3>
        {children}
      </div>
    </div>
  )
}

export function NovoCanal({ api, fechar, aoCriar }: { api: Api; fechar(): void; aoCriar(slug: string): void }): React.JSX.Element {
  const t = useT()
  const [nome, setNome] = useState('')
  const [idioma, setIdioma] = useState('pt')
  const [chaves, setChaves] = useState('')
  const [erro, setErro] = useState('')
  const criar = async (): Promise<void> => {
    try {
      const r = await api.post<{ slug: string }>('/api/canais', {
        nome,
        idioma,
        palavras_chave: chaves.split(',').map((s) => s.trim()).filter(Boolean)
      })
      aoCriar(r.slug)
      fechar()
    } catch (e) {
      setErro((e instanceof Error ? e.message : String(e)))
    }
  }
  return (
    <Modal titulo={t.novoCanal} fechar={fechar}>
      <label className="campo">
        {t.nomeCanal}
        <input autoFocus value={nome} onChange={(e) => setNome(e.target.value)} />
      </label>
      <label className="campo">
        {t.idiomaVideos}
        <select value={idioma} onChange={(e) => setIdioma(e.target.value)}>
          <option value="pt">Português</option>
          <option value="en">English</option>
          <option value="auto">Auto</option>
        </select>
      </label>
      <label className="campo">
        {t.palavrasChave}
        <input value={chaves} onChange={(e) => setChaves(e.target.value)} />
      </label>
      {erro && <span className="erro-txt">{erro}</span>}
      <div className="botoes">
        <button onClick={fechar}>{t.cancelar}</button>
        <button className="primario" disabled={!nome.trim()} onClick={() => void criar()}>{t.criar}</button>
      </div>
    </Modal>
  )
}

export function NovoProjeto(props: { api: Api; canalInicial?: string; fechar(): void; novoCanal(): void; aoCriar(canal: string, projeto: string): void }): React.JSX.Element {
  const { api, canalInicial, fechar, novoCanal, aoCriar } = props
  const t = useT()
  const [canais, setCanais] = useState<Canal[]>([])
  const [canal, setCanal] = useState('')
  const [origem, setOrigem] = useState('')
  const [modo, setModo] = useState('completo')
  const [longo, setLongo] = useState(true)
  const [erro, setErro] = useState('')
  const [enviando, setEnviando] = useState(false)

  useEffect(() => {
    api.get<Canal[]>('/api/canais').then((cs) => {
      setCanais(cs)
      if (cs.length) setCanal(cs.some((c) => c.slug === canalInicial) ? canalInicial ?? cs[0].slug : cs[0].slug)
    })
  }, [api])

  const criar = async (): Promise<void> => {
    setEnviando(true)
    try {
      const r = await api.post<{ id: string }>(`/api/canais/${encodeURIComponent(canal)}/projetos`, {
        origem: origem.trim(),
        analisar: true,
        modo_ia: modo,
        corte_longo: longo
      })
      aoCriar(canal, r.id)
      fechar()
    } catch (e) {
      setErro((e instanceof Error ? e.message : String(e)))
      setEnviando(false)
    }
  }

  if (!canais.length)
    return (
      <Modal titulo={t.novoProjeto} fechar={fechar}>
        <p>{t.bemVindoTexto}</p>
        <div className="botoes">
          <button onClick={fechar}>{t.cancelar}</button>
          <button className="primario" onClick={novoCanal}>{t.novoCanal}</button>
        </div>
      </Modal>
    )

  return (
    <Modal titulo={t.novoProjeto} fechar={fechar}>
      <label className="campo">
        {t.canal}
        <select value={canal} onChange={(e) => setCanal(e.target.value)}>
          {canais.map((c) => <option key={c.slug} value={c.slug}>{c.nome}</option>)}
        </select>
      </label>
      <label className="campo">
        {t.linkOuArquivo}
        <div className="linha" style={{ flexWrap: 'nowrap' }}>
          <input autoFocus style={{ flex: 1 }} value={origem} placeholder="https://www.youtube.com/watch?v=…" onChange={(e) => setOrigem(e.target.value)} />
          <button
            onClick={() =>
              void ponte.escolherVideo().then((p) => {
                if (p) setOrigem(p)
              })
            }
          >
            {t.escolherArquivo}
          </button>
        </div>
      </label>
      <label className="campo">
        {t.modoIA}
        <select value={modo} onChange={(e) => setModo(e.target.value)}>
          <option value="sem-ia">{t.semIA}</option>
          <option value="economico">{t.economico}</option>
          <option value="completo">{t.completo}</option>
        </select>
      </label>
      <label className="linha">
        <input type="checkbox" checked={longo} onChange={(e) => setLongo(e.target.checked)} /> {t.corteLongo}
      </label>
      {erro && <span className="erro-txt">{erro}</span>}
      <div className="botoes">
        <button onClick={fechar}>{t.cancelar}</button>
        <button className="primario" disabled={!origem.trim() || enviando} onClick={() => void criar()}>{t.analisar}</button>
      </div>
    </Modal>
  )
}
