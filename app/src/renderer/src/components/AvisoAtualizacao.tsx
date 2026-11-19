import { useState } from 'react'
import { useT } from '../i18n'
import type { Atualizacao } from '../ponte'
import { Modal } from './Dialogos'

// Aparece ao abrir o app quando há uma versão nova no GitHub. "Atualizar agora" fecha o
// Clipator e roda o instalador da versão nova numa janela do terminal (app e motor).
export function AvisoAtualizacao(p: {
  a: Atualizacao
  jobsRodando: number
  atualizar(): Promise<void>
  depois(): void
}): React.JSX.Element {
  const t = useT()
  const [indo, setIndo] = useState(false)
  const [erro, setErro] = useState('')
  const atualizar = async (): Promise<void> => {
    setIndo(true)
    setErro('')
    try {
      await p.atualizar()
    } catch (e) {
      setErro(e instanceof Error ? e.message : String(e))
      setIndo(false)
    }
  }
  return (
    <Modal titulo={t.atualizacaoTitulo} fechar={() => !indo && p.depois()}>
      <p>{t.atualizacaoTexto(p.a.nova, p.a.atual)}</p>
      <p className="dica">{t.atualizacaoComoFunciona}</p>
      {p.jobsRodando > 0 && <p className="aviso-txt">{t.atualizacaoJobs(p.jobsRodando)}</p>}
      <p>
        <a href={p.a.pagina} target="_blank" rel="noreferrer">{t.atualizacaoNovidades}</a>
      </p>
      {erro && <p className="erro-txt">{erro}</p>}
      <div className="botoes">
        <button disabled={indo} onClick={p.depois}>{t.atualizacaoDepois}</button>
        <button className="primario" autoFocus disabled={indo} onClick={() => void atualizar()}>
          {indo ? t.atualizacaoAbrindo : t.atualizacaoAgora}
        </button>
      </div>
    </Modal>
  )
}
