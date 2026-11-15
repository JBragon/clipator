import { useEffect, useRef } from 'react'
import { createRoot } from 'react-dom/client'

// Confirmação dentro do app, no lugar do confirm() do navegador. No Electron para Windows, depois de um
// confirm()/alert() nativo os campos de texto param de aceitar digitação até a janela perder e ganhar o foco
// de novo; com o modal do próprio app isso não acontece.
export type PedidoConfirmacao = {
  titulo: string
  mensagem?: React.ReactNode
  ok: string
  cancelar: string
  perigo?: boolean // ação destrutiva: botão vermelho e o foco começa no "Cancelar"
}

function CaixaConfirmar({ p, responder }: { p: PedidoConfirmacao; responder(sim: boolean): void }): React.JSX.Element {
  const cancelar = useRef<HTMLButtonElement>(null)
  const ok = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    ;(p.perigo ? cancelar : ok).current?.focus()
    const tecla = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        responder(false)
      }
    }
    window.addEventListener('keydown', tecla, true)
    return () => window.removeEventListener('keydown', tecla, true)
  }, [p, responder])
  return (
    <div className="modal-fundo" onMouseDown={(e) => e.target === e.currentTarget && responder(false)}>
      <div className={`modal confirmar ${p.perigo ? 'perigo' : ''}`} role="alertdialog" aria-modal="true" aria-label={p.titulo}>
        <h3>{p.perigo && <span className="icone-perigo" aria-hidden>🗑</span>}{p.titulo}</h3>
        {p.mensagem && <div className="mensagem">{p.mensagem}</div>}
        <div className="botoes">
          <button ref={cancelar} onClick={() => responder(false)}>{p.cancelar}</button>
          <button ref={ok} className={p.perigo ? 'perigo-cheio' : 'primario'} onClick={() => responder(true)}>{p.ok}</button>
        </div>
      </div>
    </div>
  )
}

export function confirmar(p: PedidoConfirmacao): Promise<boolean> {
  return new Promise((resolver) => {
    const antes = document.activeElement as HTMLElement | null
    const div = document.createElement('div')
    document.body.appendChild(div)
    const raiz = createRoot(div)
    let respondido = false
    const responder = (sim: boolean): void => {
      if (respondido) return
      respondido = true
      raiz.unmount()
      div.remove()
      antes?.focus?.()
      resolver(sim)
    }
    raiz.render(<CaixaConfirmar p={p} responder={responder} />)
  })
}
