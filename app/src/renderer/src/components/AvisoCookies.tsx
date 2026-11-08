import { useEffect, useState } from 'react'
import type { Api, Job } from '../api'
import { useT } from '../i18n'
import { ponte } from '../ponte'
import { useContaYoutube } from './ContaYoutube'

export type Navegadores = { instalados: string[]; todos: string[]; nomes: Record<string, string> }
// começo fixo das mensagens do motor (ingest.AVISO_ROBO) e dos erros de leitura dos cookies
export const ehErroDeCookies = (erro?: string | null): boolean =>
  !!erro && (erro.includes('confirmar que você não é um robô') || erro.includes('cookies do') || erro.includes('Arquivo de cookies'))

// Passo 1: o YouTube pediu login. O caminho principal é conectar a conta no navegador do Clipator
// (Chrome ou Edge com um perfil só dele); quando a conta conecta, o motor recomeça o download sozinho.
// Navegador do dia a dia e cookies.txt ficam em "Mais opções".
export function AvisoCookies(props: { api: Api; base: string; erro: string; jobs: Record<string, Job>; aoTentar(): void }): React.JSX.Element {
  const { api, base, erro, jobs, aoTentar } = props
  const t = useT()
  const [navs, setNavs] = useState<Navegadores | null>(null)
  const [escolhido, setEscolhido] = useState('')
  const [lembrar, setLembrar] = useState(true)
  const [msg, setMsg] = useState('')
  const conta = useContaYoutube(api, jobs, aoTentar)
  const [, , canal, , projeto] = base.split('/').slice(1)

  useEffect(() => {
    api.get<Navegadores>('/api/navegadores').then((n) => {
      setNavs(n)
      setEscolhido((e) => e || (n.instalados.includes('firefox') ? 'firefox' : n.instalados[0] ?? ''))
    }, () => setNavs({ instalados: [], todos: [], nomes: {} }))
  }, [api])

  const tentar = async (navegador: string | null, arquivo?: string): Promise<void> => {
    try {
      if (arquivo) await api.put('/api/config', { youtube: { cookies_navegador: '', cookies_arquivo: arquivo } })
      else if (lembrar && navegador) await api.put('/api/config', { youtube: { cookies_navegador: navegador, cookies_arquivo: '' } })
      await api.post(`${base}/analisar`, {}, navegador ? { cookies_navegador: navegador } : {})
      aoTentar()
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e))
    }
  }

  // abre o navegador do Clipator; quando a conta conecta, o motor já recomeça o download
  const entrar = async (): Promise<void> => {
    try {
      await conta.conectar(decodeURIComponent(canal ?? ''), decodeURIComponent(projeto ?? ''))
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e))
    }
  }

  const nome = (n: string): string => navs?.nomes[n] ?? n
  return (
    <div className="aviso-login aviso-cookies">
      <strong>🔐 {t.cookiesTitulo}</strong>
      <span>{erro}</span>
      {conta.falhouChrome && !conta.conectando && (
        <div className="linha" style={{ flexWrap: 'wrap' }}>
          <button className="primario" onClick={() => void conta.firefox(decodeURIComponent(canal ?? ''), decodeURIComponent(projeto ?? ''))}
            title={t.ytFirefoxDica}>🦊 {t.ytUsarFirefox}</button>
          <span className="dica">{t.ytGoogleRecusou}</span>
        </div>
      )}
      <div className="linha" style={{ flexWrap: 'wrap' }}>
        <button className={conta.falhouChrome ? '' : 'primario'} disabled={conta.conectando} onClick={() => void entrar()}>
          {conta.conectando ? t.ytEntrando(conta.estado?.navegador ?? 'Chrome') : conta.falhouChrome ? t.ytTentarDeNovo(conta.estado?.navegador ?? 'Chrome') : t.ytEntrar}
        </button>
        {conta.conectando && <button className="primario" onClick={() => void conta.continuar()}>{t.ytJaEntrei}</button>}
        {!conta.falhouChrome && !conta.conectando && (
          <button className="link" onClick={() => void conta.firefox(decodeURIComponent(canal ?? ''), decodeURIComponent(projeto ?? ''))}>{t.ytRecusouLink}</button>
        )}
        <span className="dica">{conta.conectando ? t.ytEntrandoDica(conta.estado?.navegador ?? 'Chrome') : t.ytEntrarDica(conta.estado?.navegador ?? 'Chrome')}</span>
      </div>
      {conta.msg && <span className="dica">{conta.msg}</span>}
      <details>
        <summary className="dica">{t.maisOpcoes}</summary>
        <div className="aviso-cookies" style={{ marginTop: 6 }}>
          {navs && navs.instalados.length > 0 && (
            <>
              <div className="linha" style={{ flexWrap: 'wrap' }}>
                {navs.instalados.map((n) => (
                  <label key={n} className="linha">
                    <input type="radio" name="nav-cookies" checked={escolhido === n} onChange={() => setEscolhido(n)} /> {nome(n)}
                  </label>
                ))}
              </div>
              <label className="linha">
                <input type="checkbox" checked={lembrar} onChange={(e) => setLembrar(e.target.checked)} /> {t.cookiesLembrar}
              </label>
            </>
          )}
          <div className="linha" style={{ flexWrap: 'wrap' }}>
            <button disabled={conta.conectando} onClick={() => void conta.firefox(decodeURIComponent(canal ?? ''), decodeURIComponent(projeto ?? ''))}
              title={t.ytFirefoxDica}>🦊 {t.ytUsarFirefox}</button>
            {escolhido && <button onClick={() => void tentar(escolhido)}>{t.cookiesTentar(nome(escolhido))}</button>}
            <button onClick={() => void ponte.escolherCookies().then(async (p) => {
              if (p) await tentar(null, p)
            })}>{t.cookiesArquivo}</button>
          </div>
          <span className="dica">{t.cookiesUltimoRecurso}</span>
        </div>
      </details>
      <span className="dica">{t.cookiesPrivacidade}</span>
      {msg && <span className="erro-txt">{msg}</span>}
    </div>
  )
}
