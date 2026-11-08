import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import type { Candidato } from '../api'
import { useT } from '../i18n'

// Pesos padrão do regras.md, para explicar notas de análises antigas que não guardaram os pesos.
const PESOS_PADRAO: Record<string, number> = {
  gancho: 20, energia: 15, reacoes: 10, ritmo: 15, historia: 20, palavras_chave: 10, plataforma: 10, fechamento: 25
}

type Props = { cand: Candidato; className?: string; style?: React.CSSProperties; titulo?: string }

// A nota vira um botão: clicar abre o porquê (sinais com peso, fechamento do assunto e o que a IA disse).
export function NotaDetalhe({ cand, className, style, titulo }: Props): React.JSX.Element {
  const t = useT()
  const [aberto, setAberto] = useState<{ x: number; y: number } | null>(null)
  const caixa = useRef<HTMLSpanElement>(null)
  const pop = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!aberto) return
    const tecla = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') setAberto(null)
    }
    const fora = (e: MouseEvent): void => {
      const alvo = e.target as Node
      if (!caixa.current?.contains(alvo) && !pop.current?.contains(alvo)) setAberto(null)
    }
    document.addEventListener('keydown', tecla)
    document.addEventListener('mousedown', fora)
    return () => {
      document.removeEventListener('keydown', tecla)
      document.removeEventListener('mousedown', fora)
    }
  }, [aberto])

  const sinais = Object.entries(cand.sinais ?? {})
  const pesos = cand.pesos ?? PESOS_PADRAO
  const totalPeso = sinais.reduce((s, [k]) => s + (pesos[k] ?? 0), 0) || 1
  const linhas = sinais
    .map(([k, v]) => ({ k, v, peso: pesos[k] ?? 0, pontos: (100 * (pesos[k] ?? 0) * v) / totalPeso }))
    .sort((a, b) => b.pontos - a.pontos)

  // o painel sai fora do card (que corta o que passa da miniatura), colado no selo da nota
  const abrir = (e: React.MouseEvent<HTMLButtonElement>): void => {
    e.stopPropagation()
    if (aberto) return setAberto(null)
    const r = e.currentTarget.getBoundingClientRect()
    const largura = 340
    setAberto({ x: Math.max(8, Math.min(r.left, window.innerWidth - largura - 8)), y: r.bottom + 6 })
  }

  return (
    <span className="nota-detalhe" ref={caixa}>
      <button className={className} style={style} title={titulo ?? t.verMotivoNota} aria-expanded={!!aberto} onClick={abrir}>
        {cand.nota.toFixed(0)}
      </button>
      {aberto && createPortal(
        <div className="pop-nota" ref={pop} role="dialog" aria-label={t.porqueNota} onClick={(e) => e.stopPropagation()}
          style={{ left: aberto.x, top: Math.min(aberto.y, window.innerHeight - 120), maxHeight: window.innerHeight - Math.min(aberto.y, window.innerHeight - 120) - 12 }}>
          <div className="topo-pop">
            <strong>{t.notaFinal} {cand.nota.toFixed(0)}</strong>
            {cand.nota_local !== undefined && cand.ia && (
              <span className="dica">{t.notaLocalEIA(cand.nota_local.toFixed(0), cand.ia.agente)}</span>
            )}
            <button className="link" onClick={() => setAberto(null)} aria-label={t.fechar}>×</button>
          </div>

          {cand.ia?.motivo && (
            <section>
              <h5>{t.motivoIA(cand.ia.agente)}</h5>
              <p>{cand.ia.motivo}</p>
              {cand.ia.gancho && <p className="dica">{t.ganchoIA}: {cand.ia.gancho}</p>}
            </section>
          )}

          {linhas.length > 0 && (
            <section>
              <h5>{t.notaLocalSinais}</h5>
              <table className="tabela-sinais">
                <tbody>
                  {linhas.map((l) => (
                    <tr key={l.k} className={l.peso ? '' : 'sem-peso'}>
                      <td>{t.sinais[l.k] ?? l.k}</td>
                      <td className="barra-sinal"><span style={{ width: `${Math.round(l.v * 100)}%` }} /></td>
                      <td className="num">{Math.round(l.v * 100)}%</td>
                      <td className="num dica" title={t.pesoDoSinal}>×{l.peso}</td>
                      <td className="num">+{l.pontos.toFixed(1)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {cand.fator_duracao !== undefined && cand.fator_duracao < 0.995 && (
                <p className="dica">{t.ajusteDuracao(Math.round((1 - cand.fator_duracao) * 100))}</p>
              )}
              {!cand.pesos && <p className="dica">{t.pesosPadrao}</p>}
            </section>
          )}

          <section>
            <h5>{t.fechamentoAssunto}{cand.sinais?.fechamento !== undefined ? ` · ${Math.round(cand.sinais.fechamento * 100)}%` : ''}</h5>
            {cand.ia?.fecha_assunto !== undefined && (
              <p>{cand.ia.fecha_assunto ? t.iaDizFecha(cand.ia.agente) : t.iaDizAberto(cand.ia.agente)}</p>
            )}
            {cand.ajuste_ia && (cand.ajuste_ia.inicio !== 0 || cand.ajuste_ia.fim !== 0) && (
              <p className="dica">{t.ajusteIA(cand.ajuste_ia.inicio, cand.ajuste_ia.fim)}</p>
            )}
            {cand.fechamento?.length ? (
              <ul className="lista-fechamento">
                {cand.fechamento.map((f) => <li key={f} className={f.startsWith('−') ? 'menos' : 'mais'}>{f}</li>)}
              </ul>
            ) : (
              <p className="dica">{t.semFechamento}</p>
            )}
          </section>

          {cand.motivos.length > 0 && (
            <section>
              <h5>{t.destaques}</h5>
              <ul>{cand.motivos.map((m) => <li key={m}>{m}</li>)}</ul>
            </section>
          )}
        </div>,
        document.body
      )}
    </span>
  )
}
