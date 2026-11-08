import Editor, { type OnMount } from '@monaco-editor/react'
import { useEffect, useRef, useState } from 'react'
import type { Api, ErroValidacao } from '../api'
import { useT } from '../i18n'
import { monaco } from '../monaco'

type Props = { api: Api; caminho: string; tema: string }

function linguagem(c: string): string {
  if (c.endsWith('.md')) return 'markdown'
  if (c.endsWith('.yaml') || c.endsWith('.yml')) return 'yaml'
  if (c.endsWith('.json')) return 'json'
  if (c.endsWith('.css')) return 'css'
  if (c.endsWith('.html')) return 'html'
  return 'plaintext'
}

function temaEscuro(tema: string): boolean {
  if (tema === 'escuro') return true
  if (tema === 'claro') return false
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

export function EditorArquivo({ api, caminho, tema }: Props): React.JSX.Element {
  const t = useT()
  const [conteudo, setConteudo] = useState<string | null>(null)
  const [erros, setErros] = useState<ErroValidacao[]>([])
  const [estado, setEstado] = useState('')
  const [escuro, setEscuro] = useState(temaEscuro(tema))
  const editorRef = useRef<Parameters<OnMount>[0] | null>(null)
  const timer = useRef<number | undefined>(undefined)

  useEffect(() => {
    api.get<{ conteudo: string; erros: ErroValidacao[] }>('/api/arquivo', { caminho }).then(
      (r) => {
        setConteudo(r.conteudo)
        setErros(r.erros)
      },
      (e) => setEstado((e instanceof Error ? e.message : String(e)))
    )
  }, [api, caminho])

  useEffect(() => {
    setEscuro(temaEscuro(tema))
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const f = (): void => setEscuro(temaEscuro(tema))
    mq.addEventListener('change', f)
    return () => mq.removeEventListener('change', f)
  }, [tema])

  // marcadores de erro no editor, como numa IDE
  useEffect(() => {
    const model = editorRef.current?.getModel()
    if (!model) return
    monaco.editor.setModelMarkers(
      model,
      'clipator',
      erros.map((e) => ({
        severity: monaco.MarkerSeverity.Error,
        message: e.mensagem,
        startLineNumber: e.linha,
        endLineNumber: e.linha,
        startColumn: 1,
        endColumn: model.getLineMaxColumn(Math.min(e.linha, model.getLineCount()))
      }))
    )
  }, [erros])

  const salvar = async (): Promise<void> => {
    const valor = editorRef.current?.getValue() ?? ''
    try {
      const r = await api.put<{ erros: ErroValidacao[] }>('/api/arquivo', { caminho, conteudo: valor })
      setErros(r.erros)
      setEstado(t.salvo)
    } catch (e) {
      setEstado((e instanceof Error ? e.message : String(e)))
    }
  }

  const aoMudar = (valor?: string): void => {
    setEstado('●')
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => {
      void api.post<{ erros: ErroValidacao[] }>('/api/validar', { caminho, conteudo: valor ?? '' }).then((r) => setErros(r.erros))
    }, 400)
  }

  const montar: OnMount = (ed) => {
    editorRef.current = ed
    ed.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => void salvar())
    setErros((e) => [...e])
  }

  if (conteudo === null) return <div className="vazio">{estado || '…'}</div>
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div className="linha" style={{ padding: '4px 10px', borderBottom: '1px solid var(--borda)' }}>
        <span className="dica">{caminho}</span>
        <span className="espaco" style={{ flex: 1 }} />
        <span className={erros.length ? 'erro-txt' : 'dica'}>{erros.length ? t.erros(erros.length) : t.validacaoOk}</span>
        <span className="dica">{estado}</span>
        <button className="primario" onClick={() => void salvar()}>
          {t.salvar}
        </button>
      </div>
      <div style={{ flex: 1, minHeight: 0 }}>
        <Editor
          defaultValue={conteudo}
          language={linguagem(caminho)}
          theme={escuro ? 'vs-dark' : 'vs'}
          onChange={aoMudar}
          onMount={montar}
          options={{ minimap: { enabled: false }, wordWrap: 'on', fontSize: 13, scrollBeyondLastLine: false, automaticLayout: true }}
        />
      </div>
    </div>
  )
}
