import { useT } from '../i18n'
import { Modal } from './Dialogos'

export function AvisoDireitos({ aceitar }: { aceitar(): void }): React.JSX.Element {
  const t = useT()
  return (
    <Modal titulo={t.avisoTitulo} fechar={() => undefined}>
      <p>{t.avisoTexto}</p>
      <div className="botoes">
        <button className="primario" autoFocus onClick={aceitar}>{t.entendi}</button>
      </div>
    </Modal>
  )
}
