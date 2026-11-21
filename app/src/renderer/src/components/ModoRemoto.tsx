import { useCallback, useEffect, useState } from 'react'
import type { Api } from '../api'
import { useT } from '../i18n'

// Modo remoto: liga a página do celular (servida pelo motor numa segunda porta) e mostra o QR code de pareamento.
type Endereco = { tipo: 'tailscale' | 'wifi'; url: string }
type Aparelho = { id: string; nome: string; criado_em: number; ultimo_acesso: number }
type EstadoRemoto = {
  ligado: boolean
  porta: number
  erro?: string | null
  aparelhos: Aparelho[]
  enderecos: Endereco[]
  tailscale: { instalado?: boolean; ip?: string | null; nome?: string | null }
}
type Codigo = { codigo: string; expira_em: number; links: (Endereco & { link: string; qr: string })[] }

const ehWindows = typeof navigator !== 'undefined' && /Windows/.test(navigator.userAgent)

export function ModoRemoto({ api }: { api: Api }): React.JSX.Element {
  const t = useT().remoto
  const [st, setSt] = useState<EstadoRemoto | null>(null)
  const [cod, setCod] = useState<Codigo | null>(null)
  const [aba, setAba] = useState(0)
  const [ocupado, setOcupado] = useState(false)
  const [msg, setMsg] = useState('')
  const [agora, setAgora] = useState(() => Date.now() / 1000)

  const carregar = useCallback(() => api.get<EstadoRemoto>('/api/remoto').then(setSt, (e: Error) => setMsg(e.message)), [api])
  useEffect(() => {
    void carregar()
  }, [carregar])

  // enquanto o QR está na tela: conta o tempo e vê se o celular já entrou
  useEffect(() => {
    if (!cod) return
    const n = st?.aparelhos.length ?? 0
    const id = setInterval(() => {
      setAgora(Date.now() / 1000)
      void api.get<EstadoRemoto>('/api/remoto').then((novo) => {
        setSt(novo)
        if (novo.aparelhos.length > n) setCod(null) // pareou: some o QR
      }, () => {})
    }, 3000)
    return () => clearInterval(id)
  }, [api, cod, st?.aparelhos.length])

  const acao = async (f: () => Promise<unknown>): Promise<void> => {
    setOcupado(true)
    setMsg('')
    try {
      await f()
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e))
    }
    setOcupado(false)
  }

  const ligar = (): Promise<void> => acao(async () => setSt(await api.post<EstadoRemoto>('/api/remoto/ligar', {})))
  const desligar = (): Promise<void> => acao(async () => {
    setCod(null)
    setSt(await api.post<EstadoRemoto>('/api/remoto/desligar'))
  })
  const novoCodigo = (): Promise<void> => acao(async () => {
    setCod(await api.post<Codigo>('/api/remoto/codigo'))
    setAba(0)
    setAgora(Date.now() / 1000)
  })
  const remover = (id: string): Promise<void> => acao(async () => {
    await api.del(`/api/remoto/aparelhos/${encodeURIComponent(id)}`)
    await carregar()
  })

  const ts = st?.tailscale ?? {}
  const restante = cod ? Math.ceil((cod.expira_em - agora) / 60) : 0
  const link = cod?.links[Math.min(aba, cod.links.length - 1)]

  return (
    <section className="remoto">
      <h3>{t.titulo}</h3>
      <p className="dica" style={{ margin: 0 }}>{t.dica}</p>
      <div className="linha">
        <span style={{ color: st?.ligado ? 'var(--ok)' : 'var(--texto-2)' }}>{st?.ligado ? `● ${t.ligado(st.porta)}` : t.desligado}</span>
        {st?.ligado ? (
          <>
            <button className="primario" disabled={ocupado} onClick={() => void novoCodigo()}>{cod ? t.gerarOutro : t.conectarCelular}</button>
            <button disabled={ocupado} onClick={() => void desligar()}>{t.desligar}</button>
          </>
        ) : (
          <button className="primario" disabled={ocupado || !st} onClick={() => void ligar()}>{t.ligar}</button>
        )}
      </div>
      {msg && <p className="erro-txt" style={{ margin: 0 }}>{msg}</p>}

      {st?.ligado && cod && (
        <div className="remoto-qr">
          {cod.links.length === 0 ? (
            <p className="dica">{t.semEndereco}</p>
          ) : (
            <>
              {cod.links.length > 1 && (
                <div className="linha" role="tablist">
                  {cod.links.map((l, i) => (
                    <button key={l.tipo} role="tab" aria-selected={i === aba} className={i === aba ? 'primario' : ''} onClick={() => setAba(i)}>
                      {l.tipo === 'tailscale' ? t.tipoTailscale : t.tipoWifi}
                    </button>
                  ))}
                </div>
              )}
              {link && (
                <div className="remoto-qr-corpo">
                  <img src={link.qr} alt={link.link} width={220} height={220} />
                  <div>
                    <p style={{ marginTop: 0 }}>{t.leiaQr}</p>
                    <p className="dica">{restante > 0 ? t.vence(restante) : t.vencido}</p>
                    <p className="dica" style={{ marginBottom: 4 }}>{t.codigo}</p>
                    <code className="remoto-codigo">{cod.codigo}</code>
                    <p className="dica"><code>{link.url}</code></p>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {st?.ligado && (
        <p className="dica" style={{ margin: 0 }}>
          {ts.ip ? t.tailscaleOk(ts.nome ?? '') : ts.instalado ? t.tailscaleDesligado : t.tailscaleFalta}
          {!ts.ip && <> <a href="https://tailscale.com/download" target="_blank" rel="noreferrer">{t.baixarTailscale}</a></>}
        </p>
      )}
      {st?.ligado && ehWindows && <p className="dica" style={{ margin: 0 }}>{t.firewall}</p>}

      {st && (st.ligado || st.aparelhos.length > 0) && (
        <>
          <h4 style={{ margin: '8px 0 0' }}>{t.aparelhos}</h4>
          {st.aparelhos.length === 0 && <p className="dica" style={{ margin: 0 }}>{t.nenhumAparelho}</p>}
          {st.aparelhos.map((a) => (
            <div key={a.id} className="linha">
              <span>📱 {a.nome}</span>
              <span className="dica">{t.ultimoAcesso(new Date(a.ultimo_acesso * 1000).toLocaleString())}</span>
              <button className="link" disabled={ocupado} onClick={() => void remover(a.id)}>{t.remover}</button>
            </div>
          ))}
        </>
      )}
      <p className="dica" style={{ margin: 0 }}>{t.seguranca}</p>
    </section>
  )
}
