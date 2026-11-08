// Monaco empacotado junto com o app (sem CDN): o editor funciona offline.
import { loader } from '@monaco-editor/react'
import * as monaco from 'monaco-editor'
import editorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker'

self.MonacoEnvironment = { getWorker: () => new editorWorker() }
loader.config({ monaco })

export { monaco }
