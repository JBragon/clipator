import { useEffect, useState } from 'react'
import { hms, type Api, type Candidato, type Job } from '../api'
import { useT } from '../i18n'
import { criarClips, type EscolhaEstilo } from './PassoEstilo'

// Passo 4: checagem de fatos. O motor lista o que os cortes citam (pessoas, empresas, produtos, lugares e dados) com o
// nome que identificou e a fonte; o usuário confirma, corrige o nome e/ou a fonte, ou ignora. O que foi conferido vale
// na montagem: o texto na tela, as imagens reais e as fontes da descrição (motor/checagem.py).

export type TipoFato = 'pessoa' | 'empresa' | 'organizacao' | 'produto' | 'lugar' | 'dado' | 'outro'
export type StatusFato = 'pendente' | 'confirmado' | 'corrigido' | 'ignorado'
export type Fonte = { titulo: string; url: string; descricao: string; origem: string; id: string }
export type ItemFato = {
  id: string
  termo: string
  tipo: TipoFato
  nome: string
  fonte: Fonte
  sugerido_nome: string
  sugerido_fonte: Fonte
  ocorrencias: { candidato: string; inicio: number; trecho: string }[]
  origem: string
  status: StatusFato
}
export type ResumoChecagem = { total: number; pendente: number; confirmado: number; corrigido: number; ignorado: number }
export type EstadoChecagem = { candidatos: string[]; itens: ItemFato[]; usou_ia: boolean; avisos: string[]; atualizado_em: string; resumo: ResumoChecagem }

const TIPOS: TipoFato[] = ['pessoa', 'empresa', 'organizacao', 'produto', 'lugar', 'dado', 'outro']
const FONTE_VAZIA: Fonte = { titulo: '', url: '', descricao: '', origem: '', id: '' }

export function Checagem(props: {
  api: Api
  base: string
  canal: string
  projeto: string
  cands: Candidato[]
  idsCortes: string[] // os cortes que vão virar clip (os escolhidos, ou os dos clips que já existem)
  deClipsExistentes: boolean
  jobs: Record<string, Job>
  escolha: EscolhaEstilo
  setEscolha(e: EscolhaEstilo): void
  setSelecionados(s: Set<string>): void
  voltarEstilo(): void
  irParaClips(): void
  aposCriar(n: number): void
  aoMudar(): void
}): React.JSX.Element {
  const { api, base, canal, projeto, cands, idsCortes, deClipsExistentes, jobs, escolha, setEscolha, setSelecionados, voltarEstilo, irParaClips, aposCriar, aoMudar } = props
  const t = useT()
  const tf = t.fatos
  const [estado, setEstado] = useState<EstadoChecagem | null>(null)
  const [msg, setMsg] = useState('')
  const [usarIA, setUsarIA] = useState(true)
  const [jobId, setJobId] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)
  const [filtro, setFiltro] = useState<'todos' | StatusFato>('todos')

  const carregar = async (): Promise<void> => {
    try {
      setEstado(await api.get<EstadoChecagem>(`${base}/checagem`))
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e))
    }
  }
  useEffect(() => {
    void carregar()
  }, [base]) // eslint-disable-line react-hooks/exhaustive-deps

  // o job da identificação: quem já estava rodando (de outra visita ao passo) também conta
  const jobAtual = jobId ? jobs[jobId] : Object.values(jobs).find((j) => j.tipo === 'checagem' && j.params.canal === canal
    && j.params.projeto === projeto && (j.status === 'rodando' || j.status === 'na_fila'))
  const rodando = (!!jobId && !jobAtual) || (!!jobAtual && (jobAtual.status === 'rodando' || jobAtual.status === 'na_fila'))
  useEffect(() => {
    if (!jobAtual || rodando) return
    if (jobAtual.status === 'erro') setMsg(jobAtual.erro ?? t.status.erro)
    setJobId(null)
    void carregar().then(aoMudar)
  }, [jobAtual?.status]) // eslint-disable-line react-hooks/exhaustive-deps

  const escolhidos = cands.filter((c) => idsCortes.includes(c.id)).sort((a, b) => b.nota - a.nota)
  const ids = escolhidos.map((c) => c.id)
  const cobre = !!estado && ids.length > 0 && ids.every((id) => estado.candidatos.includes(id))
  const doCorte = (it: ItemFato): boolean => it.ocorrencias.some((o) => ids.includes(o.candidato))
  const itens = (estado?.itens ?? []).filter(doCorte)
  const pendentes = itens.filter((i) => i.status === 'pendente').length
  const visiveis = itens.filter((i) => filtro === 'todos' || i.status === filtro)

  const identificar = async (): Promise<void> => {
    setMsg('')
    try {
      const r = await api.post<{ job: string }>(`${base}/checagem`, { candidatos: ids, usar_ia: usarIA })
      setJobId(r.job)
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e))
    }
  }

  const trocar = (novo: ItemFato): void => {
    if (!estado) return
    setEstado({ ...estado, itens: estado.itens.map((i) => (i.id === novo.id ? novo : i)) })
    aoMudar()
  }

  const confirmarTodos = async (): Promise<void> => {
    try {
      await api.post(`${base}/checagem/confirmar-pendentes`)
      await carregar()
      aoMudar()
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e))
    }
  }

  const criar = async (renderizar: boolean): Promise<void> => {
    setEnviando(true)
    try {
      const n = await criarClips(api, base, escolhidos, escolha, renderizar)
      setMsg('')
      setSelecionados(new Set())
      setEscolha({ ...escolha, pedidoIA: null })
      aposCriar(n)
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e))
    }
    setEnviando(false)
  }

  return (
    <div className="passo-conteudo passo-checagem">
      <div className="barra-grade">
        <button className="link" onClick={voltarEstilo}>← {tf.voltarEstilo}</button>
        <strong>{tf.titulo}</strong>
        <span className="dica">{deClipsExistentes ? tf.dosClips(ids.length) : t.selecionados(ids.length)}</span>
        <span className="espaco" />
        <label className="linha" title={tf.usarIADica}>
          <input type="checkbox" checked={usarIA} onChange={(e) => setUsarIA(e.target.checked)} /> {tf.usarIA}
        </label>
        <button disabled={!ids.length || rodando} onClick={() => void identificar()}>{cobre ? tf.identificarDeNovo : tf.identificar}</button>
        {!deClipsExistentes && (
          <>
            <button disabled={!escolhidos.length || enviando || rodando} onClick={() => void criar(false)}>{t.criarClips}</button>
            <button className="primario" disabled={!escolhidos.length || enviando || rodando} onClick={() => void criar(true)}>
              {t.gal.renderizarN(escolhidos.length)}
            </button>
          </>
        )}
        {deClipsExistentes && <button className="primario" onClick={irParaClips}>{tf.irParaClips} →</button>}
      </div>

      <div className="checagem-corpo">
        <p className="dica">{deClipsExistentes ? tf.explicacaoClips : tf.explicacao}</p>
        {!ids.length && (
          <div className="sem-longos">
            <span className="dica">{t.gal.semCortes}</span>
          </div>
        )}
        {msg && <p className="erro-txt">{msg}</p>}
        {rodando && (
          <div className="checagem-rodando">
            <span>{jobAtual?.mensagem || tf.identificando}</span>
            <span className="barra"><span style={{ width: `${Math.round((jobAtual?.progresso ?? 0) * 100)}%` }} /></span>
            <span className="dica">{Math.round((jobAtual?.progresso ?? 0) * 100)}%</span>
          </div>
        )}
        {ids.length > 0 && !rodando && !cobre && (
          <div className="sem-longos">
            <span className="dica">{estado?.candidatos.length ? tf.cortesNovos : tf.nadaAinda}</span>
            <button className="primario" onClick={() => void identificar()}>{tf.identificar}</button>
          </div>
        )}
        {cobre && estado && estado.avisos.length > 0 && (
          <ul className="checagem-avisos">{estado.avisos.map((a, i) => <li key={i} className="dica">⚠ {a}</li>)}</ul>
        )}
        {cobre && (
          <div className="linha checagem-resumo">
            <span className="chip">{estado?.usou_ia ? tf.comIA : tf.semIA}</span>
            {(['todos', 'pendente', 'corrigido', 'confirmado', 'ignorado'] as const).map((f) => (
              <button key={f} className={`chip-filtro ${filtro === f ? 'ativo' : ''}`} onClick={() => setFiltro(f)}>
                {f === 'todos' ? `${tf.todos} · ${itens.length}` : `${tf.status[f]} · ${itens.filter((i) => i.status === f).length}`}
              </button>
            ))}
            <span className="espaco" />
            {pendentes > 0 && <button onClick={() => void confirmarTodos()}>{tf.confirmarTodos(pendentes)}</button>}
          </div>
        )}
        {cobre && !itens.length && <p className="dica">{tf.nadaCitado}</p>}
        {cobre && (
          <div className="checagem-lista">
            {visiveis.map((it) => (
              <CartaoFato key={it.id} api={api} base={base} item={it} cands={ids.length > 1 ? cands : []} aoSalvar={trocar} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function CartaoFato(props: { api: Api; base: string; item: ItemFato; cands: Candidato[]; aoSalvar(i: ItemFato): void }): React.JSX.Element {
  const { api, base, item, cands, aoSalvar } = props
  const t = useT()
  const tf = t.fatos
  const [nome, setNome] = useState(item.nome)
  const [tipo, setTipo] = useState<TipoFato>(item.tipo)
  const [fonte, setFonte] = useState<Fonte>(item.fonte)
  const [opcoes, setOpcoes] = useState<Fonte[] | null>(null)
  const [buscando, setBuscando] = useState(false)
  const [erro, setErro] = useState('')
  const [editandoFonte, setEditandoFonte] = useState(false)
  useEffect(() => {
    setNome(item.nome)
    setTipo(item.tipo)
    setFonte(item.fonte)
  }, [item])

  const mudou = nome.trim() !== item.nome || tipo !== item.tipo || JSON.stringify(fonte) !== JSON.stringify(item.fonte)
  const dado = tipo === 'dado'
  const oc = item.ocorrencias[0]
  const corte = oc ? cands.find((c) => c.id === oc.candidato) : undefined

  const enviar = async (corpo: Record<string, unknown>): Promise<void> => {
    setErro('')
    try {
      aoSalvar(await api.put<ItemFato>(`${base}/checagem/itens/${encodeURIComponent(item.id)}`, corpo))
      setOpcoes(null)
      setEditandoFonte(false)
    } catch (e) {
      setErro(e instanceof Error ? e.message : String(e))
    }
  }
  const salvar = (): Promise<void> => enviar({ nome: nome.trim(), tipo, fonte, ...(mudou ? {} : { status: 'confirmado' }) })

  const buscar = async (): Promise<void> => {
    setBuscando(true)
    setErro('')
    try {
      setOpcoes(await api.get<Fonte[]>('/api/checagem/fontes', { busca: nome.trim() || item.termo }))
    } catch (e) {
      setErro(e instanceof Error ? e.message : String(e))
    }
    setBuscando(false)
  }

  // o trecho da fala com o termo em negrito
  const trecho = (oc?.trecho ?? '').split(new RegExp(`(${item.termo.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'i'))

  return (
    <div className={`cartao-fato ${item.status}`}>
      <div className="linha cabeca-fato">
        <select value={tipo} onChange={(e) => setTipo(e.target.value as TipoFato)} aria-label={tf.tipo}>
          {TIPOS.map((x) => <option key={x} value={x}>{tf.tipos[x]}</option>)}
        </select>
        <span className={`chip status-fato ${item.status}`}>{tf.status[item.status]}</span>
        {item.origem === 'ia' && <span className="chip usa-ia">IA</span>}
        <span className="espaco" />
        {oc && <span className="dica">{hms(oc.inicio)}{corte ? ` · ${tf.noCorte(hms(corte.inicio))}` : ''}{item.ocorrencias.length > 1 ? ` · ${tf.vezes(item.ocorrencias.length)}` : ''}</span>}
      </div>
      <div className="campo-fato">
        <span className="rotulo">{tf.dito}</span>
        <span><strong>“{item.termo}”</strong>{oc?.trecho && <span className="dica trecho-fato"> … {trecho.map((p, i) => i % 2 ? <b key={i}>{p}</b> : p)} …</span>}</span>
      </div>
      <label className="campo-fato">
        <span className="rotulo">{dado ? tf.comoAparece : tf.identificado}</span>
        <input value={nome} onChange={(e) => setNome(e.target.value)} />
        {item.sugerido_nome && item.sugerido_nome !== nome && (
          <button className="link" onClick={() => setNome(item.sugerido_nome)}>{tf.usarSugerido(item.sugerido_nome)}</button>
        )}
      </label>
      <div className="campo-fato">
        <span className="rotulo">{dado ? tf.deOnde : tf.fonte}</span>
        <div className="fonte-fato">
          {fonte.url || fonte.titulo ? (
            <span>
              {fonte.url ? <a href={fonte.url} target="_blank" rel="noreferrer">{fonte.titulo || fonte.url}</a> : <strong>{fonte.titulo}</strong>}
              {fonte.descricao && <span className="dica"> · {fonte.descricao}</span>}
              {fonte.origem && <span className="chip">{tf.origens[fonte.origem] ?? fonte.origem}</span>}
            </span>
          ) : (
            <span className="aviso-txt">{dado ? tf.semFonteDado : tf.semFonte}</span>
          )}
          {(editandoFonte || !(fonte.url || fonte.titulo)) && (
            <div className="campos-fonte">
              <input placeholder={tf.fonteNome} value={fonte.titulo}
                onChange={(e) => setFonte({ ...fonte, titulo: e.target.value, descricao: '', origem: 'usuario', id: '' })} />
              <input placeholder={tf.fonteLink} value={fonte.url}
                onChange={(e) => setFonte({ ...fonte, url: e.target.value, descricao: '', origem: 'usuario', id: '' })} />
            </div>
          )}
          <div className="linha">
            {(fonte.url || fonte.titulo) && !editandoFonte && <button onClick={() => setEditandoFonte(true)}>{tf.editarFonte}</button>}
            {!dado && tipo !== 'lugar' && (
              <button disabled={buscando} onClick={() => void buscar()}>{buscando ? '…' : tf.buscarFonte}</button>
            )}
            {(fonte.titulo || fonte.url) && (
              <button className="link" onClick={() => setFonte(FONTE_VAZIA)}>{tf.limparFonte}</button>
            )}
          </div>
          {opcoes && (
            <ul className="opcoes-fonte">
              {!opcoes.length && <li className="dica">{tf.nenhumaFonte}</li>}
              {opcoes.map((o) => (
                <li key={o.id}>
                  <button className="link" onClick={() => {
                    setFonte({ titulo: o.titulo, url: o.url, descricao: o.descricao, origem: 'wikidata', id: o.id })
                    setOpcoes(null)
                  }}>{o.titulo}</button>
                  <span className="dica"> · {o.descricao || o.id}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
      {erro && <p className="erro-txt">{erro}</p>}
      <div className="linha acoes-fato">
        <button className="primario" onClick={() => void salvar()}>{mudou ? tf.salvarCorrecao : item.status === 'confirmado' ? tf.confirmado : item.status === 'corrigido' ? tf.corrigido : tf.confirmar}</button>
        {item.status !== 'ignorado'
          ? <button onClick={() => void enviar({ status: 'ignorado' })} title={tf.ignorarDica}>{tf.ignorar}</button>
          : <span className="dica">{tf.ignoradoDica}</span>}
        {mudou && <button className="link" onClick={() => { setNome(item.nome); setTipo(item.tipo); setFonte(item.fonte); setEditandoFonte(false) }}>{tf.desfazer}</button>}
      </div>
    </div>
  )
}
