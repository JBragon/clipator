import { useEffect, useState } from 'react'
import type { Api, Job } from '../api'
import { useT } from '../i18n'
import { noElectron, ponte } from '../ponte'
import type { Navegadores } from './AvisoCookies'
import { useContaYoutube } from './ContaYoutube'

type Agente = { instalado: boolean; versao?: string | null; logado?: boolean | null }
type Config = {
  idioma_interface: 'pt' | 'en'
  tema: 'sistema' | 'claro' | 'escuro'
  whisper?: { modelo: string; dispositivo: string; idioma: string }
  ia?: { ranking: string; estilos: string; imagens: string }
  youtube?: { cookies_navegador: string; cookies_arquivo: string }
  [k: string]: unknown
}

export function Configuracoes(props: { api: Api; config: Config; salvar(c: Partial<Config>): Promise<void>; workspace: string; jobs: Record<string, Job> }): React.JSX.Element {
  const { api, config, salvar, workspace, jobs } = props
  const t = useT()
  const pastasSkills = (config.pastas_skills as string[] | undefined) ?? []
  const [agentes, setAgentes] = useState<Record<string, Agente> | null>(null)
  const [navs, setNavs] = useState<Navegadores | null>(null)
  const conta = useContaYoutube(api, jobs)

  useEffect(() => {
    api.get<Record<string, Agente>>('/api/agentes').then(setAgentes, () => setAgentes({}))
    api.get<Navegadores>('/api/navegadores').then(setNavs, () => setNavs(null))
  }, [api])

  const trocarWorkspace = async (): Promise<void> => {
    const p = await ponte.escolherPasta()
    if (p) {
      await ponte.definirWorkspace(p)
      location.reload()
    }
  }

  const ia = config.ia ?? { ranking: 'claude', estilos: 'claude', imagens: 'codex' }
  const whisper = config.whisper ?? { modelo: 'auto', dispositivo: 'auto', idioma: 'auto' }
  const yt = config.youtube ?? { cookies_navegador: '', cookies_arquivo: '' }

  return (
    <div className="config">
      <section>
        <h3>{t.idiomaInterface}</h3>
        <select value={config.idioma_interface} onChange={(e) => void salvar({ idioma_interface: e.target.value as Config['idioma_interface'] })}>
          <option value="pt">Português</option>
          <option value="en">English</option>
        </select>
      </section>
      <section>
        <h3>{t.tema}</h3>
        <div className="linha">
          {(['sistema', 'claro', 'escuro'] as const).map((v) => (
            <label key={v} className="linha">
              <input type="radio" name="tema" checked={config.tema === v} onChange={() => void salvar({ tema: v })} />
              {v === 'sistema' ? t.temaSistema : v === 'claro' ? t.temaClaro : t.temaEscuro}
            </label>
          ))}
        </div>
      </section>
      <section>
        <h3>{t.workspace}</h3>
        <div className="linha">
          <code>{workspace}</code>
          {noElectron && <button onClick={() => void trocarWorkspace()}>{t.trocar}</button>}
        </div>
      </section>
      <section>
        <h3>{t.pastasSkills}</h3>
        <p className="dica" style={{ margin: 0 }}>{t.pastasSkillsDica}</p>
        {pastasSkills.map((p) => (
          <div key={p} className="linha">
            <code>{p}</code>
            <button className="link" onClick={() => void salvar({ pastas_skills: pastasSkills.filter((x) => x !== p) })}>×</button>
          </div>
        ))}
        <div className="linha">
          <button
            onClick={() =>
              void ponte.escolherPasta().then(async (p) => {
                if (p && !pastasSkills.includes(p)) await salvar({ pastas_skills: [...pastasSkills, p] })
              })
            }
          >
            {t.adicionarPasta}
          </button>
        </div>
      </section>
      <section>
        <h3>{t.agentes}</h3>
        <p className="dica" style={{ margin: 0 }}>{t.agentesDica}</p>
        {agentes &&
          Object.entries(agentes).map(([nome, a]) => (
            <div key={nome} className="agente">
              <strong>{nome === 'codex' ? 'Codex' : 'Claude Code'}</strong>
              <span style={{ color: a.instalado && a.logado !== false ? 'var(--ok)' : 'var(--texto-2)' }}>
                {a.instalado ? `${a.versao ?? t.instalado}${a.logado === true ? ` · ${t.logado}` : a.logado === false ? ` · ${t.naoLogado}` : ''}` : t.naoInstalado}
              </span>
            </div>
          ))}
        <label className="campo">
          {t.iaRanking}
          <select value={ia.ranking} onChange={(e) => void salvar({ ia: { ...ia, ranking: e.target.value } })}>
            <option value="claude">Claude Code</option>
            <option value="codex">Codex</option>
            <option value="nenhum">{t.nenhuma}</option>
          </select>
        </label>
      </section>
      <section>
        <h3>{t.contaYoutube}</h3>
        <p className="dica" style={{ margin: 0 }}>{t.contaYoutubeDica}</p>
        <div className="linha" style={{ flexWrap: 'wrap' }}>
          <span style={{ color: conta.estado?.conectada ? 'var(--ok)' : 'var(--texto-2)' }}>
            {conta.estado?.conectada ? `✓ ${t.ytConectada}` : t.ytDesconectada}{conta.estado?.navegador ? ` · ${conta.estado.navegador}` : ''}
          </span>
          {conta.estado?.conectada ? (
            <button onClick={() => void conta.desconectar()}>{t.ytDesconectar}</button>
          ) : (
            <button className="primario" disabled={conta.conectando || !conta.estado?.navegador} onClick={() => void conta.conectar()}>
              {conta.conectando ? t.ytEntrando(conta.estado?.navegador ?? 'Chrome') : t.ytEntrar}
            </button>
          )}
        </div>
        {!conta.estado?.navegador && conta.estado && <p className="dica" style={{ margin: 0 }}>{t.ytSemNavegador}</p>}
        {conta.msg && <p className="dica" style={{ margin: 0 }}>{conta.msg}</p>}
      </section>
      <section>
        <h3>{t.cookiesYoutube}</h3>
        <p className="dica" style={{ margin: 0 }}>{t.cookiesYoutubeDica}</p>
        <label className="campo">
          {t.cookiesNavegador}
          <select value={yt.cookies_navegador} onChange={(e) => void salvar({ youtube: { ...yt, cookies_navegador: e.target.value } })}>
            <option value="">{t.nenhum}</option>
            {(navs?.todos ?? []).map((n) => (
              <option key={n} value={n}>{navs?.nomes[n] ?? n}{navs && !navs.instalados.includes(n) ? ` (${t.naoEncontrado})` : ''}</option>
            ))}
          </select>
        </label>
        <div className="linha">
          <span>{t.cookiesArquivoTxt}</span>
          {yt.cookies_arquivo ? <code>{yt.cookies_arquivo}</code> : <span className="dica">{t.nenhum}</span>}
          <button onClick={() => void ponte.escolherCookies().then(async (p) => {
            if (p) await salvar({ youtube: { ...yt, cookies_arquivo: p } })
          })}>{t.escolherArquivo}</button>
          {yt.cookies_arquivo && <button className="link" onClick={() => void salvar({ youtube: { ...yt, cookies_arquivo: '' } })}>×</button>}
        </div>
        <p className="dica" style={{ margin: 0 }}>{t.cookiesWindowsDica}</p>
      </section>
      <section>
        <h3>{t.modeloWhisper}</h3>
        <select value={whisper.modelo} onChange={(e) => void salvar({ whisper: { ...whisper, modelo: e.target.value } })}>
          <option value="auto">{t.automatico}</option>
          {['tiny', 'base', 'small', 'medium', 'large-v3-turbo', 'large-v3'].map((m) => <option key={m}>{m}</option>)}
        </select>
      </section>
    </div>
  )
}
