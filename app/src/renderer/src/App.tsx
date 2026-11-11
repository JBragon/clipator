import { useCallback, useEffect, useMemo, useState } from 'react'
import { Api, type Job } from './api'
import { IdiomaCtx, textos, type Idioma } from './i18n'
import { ponte, type InfoMotor } from './ponte'
import { Explorador } from './components/Explorador'
import { EditorArquivo } from './components/EditorArquivo'
import { ProjetoView } from './components/ProjetoView'
import { PainelJobs } from './components/PainelJobs'
import { ProgressoGlobal } from './components/BarraProgresso'
import { Configuracoes } from './components/Configuracoes'
import { GaleriaEstilos } from './components/GaleriaEstilos'
import { Skills } from './components/Skills'
import { NovoCanal, NovoProjeto } from './components/Dialogos'
import { AvisoDireitos } from './components/AvisoDireitos'

export type Aba =
  | { tipo: 'arquivo'; id: string; titulo: string; caminho: string }
  | { tipo: 'projeto'; id: string; titulo: string; canal: string; projeto: string }
  | { tipo: 'config'; id: 'config'; titulo: string }
  | { tipo: 'estilos'; id: 'estilos'; titulo: string }
  | { tipo: 'skills'; id: 'skills'; titulo: string }

export type ProjetoRef = { canal: string; projeto: string }
type Config = { idioma_interface: Idioma; tema: 'sistema' | 'claro' | 'escuro'; aviso_direitos_aceito: boolean; [k: string]: unknown }

export function App(): React.JSX.Element {
  const [info, setInfo] = useState<InfoMotor | null>(null)
  const [api, setApi] = useState<Api | null>(null)
  const [config, setConfig] = useState<Config | null>(null)
  const [abas, setAbas] = useState<Aba[]>([])
  const [ativa, setAtiva] = useState<string | null>(null)
  const [jobs, setJobs] = useState<Record<string, Job>>({})
  const [versao, setVersao] = useState(0) // sobe quando um job termina: recarrega o que estiver aberto
  const [dialogo, setDialogo] = useState<null | 'canal' | 'projeto'>(null)
  const [selecionados, setSelecionados] = useState<Set<string>>(new Set())

  const t = textos[config?.idioma_interface ?? 'pt']

  const conectar = useCallback(async (reiniciar = false) => {
    setInfo(null)
    const i = reiniciar ? await ponte.reiniciarMotor() : await ponte.infoMotor()
    setInfo(i)
    if (i.porta && i.token) {
      const a = new Api(`http://127.0.0.1:${i.porta}`, i.token)
      setApi(a)
      try {
        setConfig(await a.get<Config>('/api/config'))
      } catch (e) {
        setInfo({ ...i, erro: (e instanceof Error ? e.message : String(e)) })
      }
    }
  }, [])

  useEffect(() => {
    void conectar()
  }, [conectar])

  // "Abrir Configurações" de qualquer tela (o aviso de que o recurso precisa da IA)
  useEffect(() => {
    const abrirCfg = (): void => abrir({ tipo: 'config', id: 'config', titulo: t.configuracoes })
    window.addEventListener('clipator:abrir-configuracoes', abrirCfg)
    return () => window.removeEventListener('clipator:abrir-configuracoes', abrirCfg)
  })

  // tema: o padrão segue o sistema; o Monaco e as prévias acompanham
  useEffect(() => {
    if (!config) return
    const raiz = document.documentElement
    if (config.tema === 'sistema') raiz.removeAttribute('data-tema')
    else raiz.setAttribute('data-tema', config.tema)
    void ponte.definirTema(config.tema)
  }, [config])

  useEffect(() => {
    if (!api) return
    void api.get<Job[]>('/api/jobs').then((js) => setJobs(Object.fromEntries(js.map((j) => [j.id, j]))))
    return api.eventos((j) => {
      setJobs((atual) => {
        const antes = atual[j.id]
        const linhas = j.linha_log ? [...(antes?.linhas ?? []), ...j.linha_log.split('\n').filter(Boolean)].slice(-200) : antes?.linhas
        return { ...atual, [j.id]: { ...antes, ...j, linhas } }
      })
      if (['ok', 'erro', 'cancelado'].includes(j.status) && !j.linha_log) setVersao((v) => v + 1)
    })
  }, [api])

  const abrir = useCallback((aba: Aba) => {
    setAbas((as) => (as.some((a) => a.id === aba.id) ? as : [...as, aba]))
    setAtiva(aba.id)
  }, [])

  const fechar = (id: string): void => {
    setAbas((as) => {
      const resto = as.filter((a) => a.id !== id)
      if (ativa === id) setAtiva(resto.length ? resto[resto.length - 1].id : null)
      return resto
    })
  }

  const abaAtual = abas.find((a) => a.id === ativa) ?? null
  const projetoAtual: ProjetoRef | null = useMemo(
    () => (abaAtual?.tipo === 'projeto' ? { canal: abaAtual.canal, projeto: abaAtual.projeto } : null),
    [abaAtual]
  )
  useEffect(() => setSelecionados(new Set()), [projetoAtual?.canal, projetoAtual?.projeto])

  const abrirProjeto = useCallback(
    (canal: string, projeto: string, titulo?: string) =>
      abrir({ tipo: 'projeto', id: `p:${canal}/${projeto}`, titulo: titulo ?? projeto, canal, projeto }),
    [abrir]
  )

  const [canalNovoVideo, setCanalNovoVideo] = useState('')

  const salvarConfig = async (parcial: Partial<Config>): Promise<void> => {
    if (!api) return
    setConfig(await api.put<Config>('/api/config', parcial))
  }

  if (!info || (!api && !info.erro)) {
    return (
      <IdiomaCtx.Provider value={t}>
        <div className="vazio">{t.conectando}</div>
      </IdiomaCtx.Provider>
    )
  }
  if (info.erro || !api) {
    return (
      <IdiomaCtx.Provider value={t}>
        <div className="vazio">
          <div>
            <h1>{t.motorErro}</h1>
            <p>{info.erro}</p>
            <p className="dica">{t.motorErroDica}</p>
            <pre className="log" style={{ textAlign: 'left' }}>{info.log}</pre>
            <button className="primario" onClick={() => void conectar(true)}>
              {t.tentarDeNovo}
            </button>
          </div>
        </div>
      </IdiomaCtx.Provider>
    )
  }

  const rodando = Object.values(jobs).filter((j) => j.status === 'rodando')

  return (
    <IdiomaCtx.Provider value={t}>
      <div className="app">
        <header className="topo">
          <span className="marca">Clipator</span>
          <button onClick={() => setDialogo('projeto')}>＋ {t.novoProjeto}</button>
          <button onClick={() => setDialogo('canal')}>＋ {t.novoCanal}</button>
          <span className="espaco" />
          <ProgressoGlobal jobs={jobs} projetoAtivo={projetoAtual} abrirProjeto={abrirProjeto} />
          <button onClick={() => abrir({ tipo: 'estilos', id: 'estilos', titulo: t.estilos })}>{t.estilos}</button>
          <button onClick={() => abrir({ tipo: 'skills', id: 'skills', titulo: t.skills })}>{t.skills}</button>
          <button onClick={() => abrir({ tipo: 'config', id: 'config', titulo: t.configuracoes })}>⚙ {t.configuracoes}</button>
        </header>

        <div className="meio">
          <Explorador
            api={api}
            versao={versao}
            ativo={projetoAtual ? `${projetoAtual.canal}/${projetoAtual.projeto}` : ''}
            jobs={jobs}
            abrirArquivo={(caminho) => abrir({ tipo: 'arquivo', id: `f:${caminho}`, titulo: caminho.split('/').pop() ?? caminho, caminho })}
            abrirProjeto={abrirProjeto}
            novoCanal={() => setDialogo('canal')}
            novoVideo={(canal) => {
              setCanalNovoVideo(canal ?? '')
              setDialogo('projeto')
            }}
            fecharAbas={(prefixo) => abas.filter((x) => x.id.startsWith(prefixo)).forEach((x) => fechar(x.id))}
            aoMudar={() => setVersao((v) => v + 1)}
          />

          <main className="centro">
            <div className="abas" role="tablist">
              {abas.map((a) => (
                <div
                  key={a.id}
                  role="tab"
                  aria-selected={a.id === ativa}
                  className={`aba ${a.id === ativa ? 'ativa' : ''}`}
                  onClick={() => setAtiva(a.id)}
                  // Clique com o botão do meio (scroll) fecha a aba, como no navegador.
                  // Sem o preventDefault no mousedown, o Windows liga o autoscroll.
                  onMouseDown={(e) => {
                    if (e.button === 1) e.preventDefault()
                  }}
                  onAuxClick={(e) => {
                    if (e.button !== 1) return
                    e.preventDefault()
                    fechar(a.id)
                  }}
                >
                  {a.tipo === 'projeto' ? '🎬 ' : ''}
                  {a.titulo}
                  <button className="fechar" aria-label={t.fechar} onClick={(e) => (e.stopPropagation(), fechar(a.id))}>
                    ×
                  </button>
                </div>
              ))}
            </div>
            <div className="conteudo">
              {!abaAtual && (
                <div className="vazio">
                  <div>
                    <h1>{t.bemVindo}</h1>
                    <p>{t.bemVindoTexto}</p>
                    <div className="linha" style={{ justifyContent: 'center' }}>
                      <button className="primario" onClick={() => setDialogo('projeto')}>
                        {t.novoProjeto}
                      </button>
                      <button onClick={() => setDialogo('canal')}>{t.novoCanal}</button>
                    </div>
                  </div>
                </div>
              )}
              {abaAtual?.tipo === 'arquivo' && <EditorArquivo key={abaAtual.id} api={api} caminho={abaAtual.caminho} tema={config?.tema ?? 'sistema'} />}
              {abaAtual?.tipo === 'projeto' && (
                <ProjetoView
                  key={abaAtual.id}
                  api={api}
                  canal={abaAtual.canal}
                  projeto={abaAtual.projeto}
                  versao={versao}
                  selecionados={selecionados}
                  setSelecionados={setSelecionados}
                  jobs={jobs}
                  aposCriar={() => setVersao((v) => v + 1)}
                />
              )}
              {abaAtual?.tipo === 'config' && config && <Configuracoes api={api} config={config} salvar={salvarConfig} workspace={info.workspace} jobs={jobs} />}
              {abaAtual?.tipo === 'skills' && <Skills api={api} aoMudar={() => setVersao((v) => v + 1)} />}
              {abaAtual?.tipo === 'estilos' && (
                <GaleriaEstilos api={api} jobs={jobs} abrirArquivo={(caminho) => abrir({ tipo: 'arquivo', id: `f:${caminho}`, titulo: caminho.split('/').pop() ?? caminho, caminho })} />
              )}
            </div>
          </main>

        </div>

        <PainelJobs api={api} jobs={jobs} />

        <footer className="status">
          <span>{info.workspace}</span>
          <span>{rodando.length ? `${rodando[0].mensagem || rodando[0].tipo} ${Math.round(rodando[0].progresso * 100)}%` : ''}</span>
        </footer>

        {dialogo === 'canal' && <NovoCanal api={api} fechar={() => setDialogo(null)} aoCriar={() => setVersao((v) => v + 1)} />}
        {dialogo === 'projeto' && (
          <NovoProjeto
            api={api}
            canalInicial={canalNovoVideo}
            fechar={() => setDialogo(null)}
            novoCanal={() => setDialogo('canal')}
            aoCriar={(canal, projeto) => {
              setVersao((v) => v + 1)
              abrirProjeto(canal, projeto)
            }}
          />
        )}
        {config && !config.aviso_direitos_aceito && <AvisoDireitos aceitar={() => void salvarConfig({ aviso_direitos_aceito: true })} />}
      </div>
    </IdiomaCtx.Provider>
  )
}
