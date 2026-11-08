// Minhas skills: importar (pasta, .zip ou GitHub), ver o que muda, ativar por
// escopo (global, canal ou projeto), exportar como .zip e remover.
import { useCallback, useEffect, useState } from 'react'
import type { Api } from '../api'
import { useT } from '../i18n'
import { ponte } from '../ponte'

type Ativacao = { skill: string; escopo: 'global' | 'canal' | 'projeto'; canal?: string; projeto?: string }
type Skill = {
  id: string
  nome: string
  autor: string
  versao: string
  licenca: string
  preco: 'gratis' | 'pago'
  link_compra?: string
  tipos: string[]
  descricao: string
  origem: 'instalada' | 'pasta-extra' | 'embutida'
  pasta: string
  estilos: string[]
  avisos: string[]
  resumo: string[]
  ativacoes: Ativacao[]
}
type Lista = { skills: Skill[]; erros: string[]; pasta: string }
type Canal = { slug: string; nome: string }

export function Skills({ api, aoMudar }: { api: Api; aoMudar(): void }): React.JSX.Element {
  const t = useT()
  const [lista, setLista] = useState<Lista | null>(null)
  const [canais, setCanais] = useState<Canal[]>([])
  const [link, setLink] = useState('')
  const [msg, setMsg] = useState('')
  const [ocupado, setOcupado] = useState(false)

  const carregar = useCallback(async () => {
    setLista(await api.get<Lista>('/api/skills'))
    setCanais(await api.get<Canal[]>('/api/canais'))
  }, [api])

  useEffect(() => {
    void carregar()
  }, [carregar])

  const rodar = async (f: () => Promise<unknown>, ok?: string): Promise<void> => {
    setOcupado(true)
    setMsg('…')
    try {
      await f()
      setMsg(ok ?? '')
      await carregar()
      aoMudar()
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e))
    } finally {
      setOcupado(false)
    }
  }

  const importar = async (origem: string | null): Promise<void> => {
    if (!origem) return
    await rodar(async () => {
      try {
        await api.post('/api/skills/importar', { origem })
      } catch (e) {
        const m = e instanceof Error ? e.message : String(e)
        if (m.includes('já está instalada') && confirm(t.skillSubstituir)) await api.post('/api/skills/importar', { origem, substituir: true })
        else throw e
      }
    }, t.skillImportada)
  }

  return (
    <div className="skills">
      <h2 style={{ margin: 0 }}>{t.skills}</h2>
      <p className="dica" style={{ margin: 0 }}>{t.skillsDica}</p>
      <div className="linha">
        <button disabled={ocupado} onClick={() => void ponte.escolherPasta().then(importar)}>{t.importarPasta}</button>
        <button disabled={ocupado} onClick={() => void ponte.escolherZip().then(importar)}>{t.importarZip}</button>
        <input style={{ flex: 1, minWidth: 220 }} placeholder="https://github.com/autor/repo/tree/main/pasta" value={link} onChange={(e) => setLink(e.target.value)} />
        <button disabled={ocupado || !link.startsWith('https://github.com/')} onClick={() => void importar(link).then(() => setLink(''))}>{t.importarGithub}</button>
      </div>
      <span className="dica">{msg}</span>
      {lista?.erros.map((e) => <span key={e} className="erro-txt">{e}</span>)}
      {lista && lista.skills.length === 0 && <p className="dica">{t.semSkills(lista.pasta)}</p>}
      {lista?.skills.map((s) => (
        <CartaoSkill key={s.id} s={s} canais={canais} api={api} rodar={rodar} />
      ))}
    </div>
  )
}

function CartaoSkill(props: { s: Skill; canais: Canal[]; api: Api; rodar(f: () => Promise<unknown>, ok?: string): Promise<void> }): React.JSX.Element {
  const { s, canais, api, rodar } = props
  const t = useT()
  const [escopo, setEscopo] = useState<'global' | 'canal' | 'projeto'>('global')
  const [canal, setCanal] = useState('')
  const [projetos, setProjetos] = useState<{ id: string; titulo: string }[]>([])
  const [projeto, setProjeto] = useState('')
  const url = `/api/skills/${encodeURIComponent(s.id)}`

  useEffect(() => {
    if (escopo !== 'projeto' || !canal) return
    void api.get<{ id: string; titulo: string }[]>(`/api/canais/${encodeURIComponent(canal)}/projetos`).then(setProjetos)
  }, [api, canal, escopo])

  const onde = (a: Ativacao): string =>
    a.escopo === 'global' ? t.escopoGlobal : a.escopo === 'canal' ? `${t.canal}: ${a.canal}` : `${a.canal} / ${a.projeto}`
  const podeAtivar = escopo === 'global' || (canal && (escopo === 'canal' || projeto))

  return (
    <div className="skill">
      <div className="linha">
        <h3>{s.nome}</h3>
        <span className="chip">v{s.versao}</span>
        {s.autor && <span className="chip">{s.autor}</span>}
        {s.licenca && <span className="chip">{s.licenca}</span>}
        <span className="chip">{s.preco === 'pago' ? t.pago : t.gratis}</span>
        {s.origem === 'pasta-extra' && <span className="chip">{t.pastaExtra}</span>}
        {s.origem === 'embutida' && <span className="chip destaque" title={t.embutidaDica}>{t.embutida}</span>}
        {s.tipos.map((x) => <span key={x} className="chip">{x}</span>)}
      </div>
      {s.descricao && <span>{s.descricao}</span>}
      <ul>{s.resumo.map((r) => <li key={r}>{r}</li>)}</ul>
      {s.avisos.map((a) => <span key={a} className="aviso-txt">⚠ {a}</span>)}
      {s.preco === 'pago' && s.link_compra && (
        <a href={s.link_compra} target="_blank" rel="noreferrer">{t.paginaCompra}</a>
      )}
      <div className="linha">
        {s.ativacoes.map((a, i) => (
          <span key={i} className="chip" style={{ color: 'var(--ok)' }}>
            ✓ {onde(a)}{' '}
            <button className="link" onClick={() => void rodar(() => api.post(`${url}/desativar`, a))}>×</button>
          </span>
        ))}
      </div>
      <div className="linha">
        <select value={escopo} onChange={(e) => setEscopo(e.target.value as typeof escopo)}>
          <option value="global">{t.escopoGlobal}</option>
          <option value="canal">{t.escopoCanal}</option>
          <option value="projeto">{t.escopoProjeto}</option>
        </select>
        {escopo !== 'global' && (
          <select value={canal} onChange={(e) => setCanal(e.target.value)}>
            <option value="">{t.canal}…</option>
            {canais.map((c) => <option key={c.slug} value={c.slug}>{c.nome}</option>)}
          </select>
        )}
        {escopo === 'projeto' && canal && (
          <select value={projeto} onChange={(e) => setProjeto(e.target.value)}>
            <option value="">…</option>
            {projetos.map((p) => <option key={p.id} value={p.id}>{p.titulo}</option>)}
          </select>
        )}
        <button className="primario" disabled={!podeAtivar} onClick={() => void rodar(() => api.post(`${url}/ativar`, { escopo, canal: canal || null, projeto: projeto || null }))}>
          {t.ativar}
        </button>
        <span className="espaco" />
        <button onClick={() => void ponte.salvarArquivo(`${s.id}-${s.versao}.zip`).then(async (d) => {
            if (d) await rodar(() => api.post(`${url}/exportar`, { destino: d }), t.exportada)
          })}>
          {t.exportarZip}
        </button>
        {s.origem === 'instalada' && (
          <button onClick={() => confirm(t.confirmarRemoverSkill) && void rodar(() => api.del(url, { confirmar: 'true' }))}>{t.remover}</button>
        )}
      </div>
    </div>
  )
}
