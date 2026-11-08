// Acesso ao processo principal. No navegador (npm run web) cai num modo de
// desenvolvimento que lê porta e token da URL.

export type InfoMotor = { porta?: number; token?: string; erro?: string; log: string; workspace: string }
export type AgenteIA = 'claude' | 'codex'
export type PedidoSessao = { agente: AgenteIA; modo: 'abrir' | 'continuar'; cwd: string; frase: string; titulo: string; alvo: string }
export type InfoSessao = PedidoSessao & { id: string; viva: boolean; criada: number; codigo?: number }

// conversa estilizada (chat): os eventos que o processo principal tira do Claude Code / Codex
export type Decisao = 'sim' | 'nao' | 'sempre'
export type EventoChat = { n: number } & (
  | { tipo: 'sistema'; sessao?: string; modelo?: string; modelos?: string[]; aviso?: string }
  | { tipo: 'usuario'; texto: string }
  | { tipo: 'texto'; id: string; texto: string; parcial?: boolean }
  | { tipo: 'pensando'; id: string; texto: string; parcial?: boolean }
  | { tipo: 'ferramenta'; id: string; nome: string; entrada?: unknown; estado: 'rodando' | 'ok' | 'erro'; saida?: string; diffs?: { arquivo: string; diff: string }[] }
  | { tipo: 'permissao'; id: string; nome: string; resumo: string; detalhe?: string; resposta?: Decisao }
  | { tipo: 'ocupado'; ocupado: boolean }
  | { tipo: 'fim'; custo?: number; tokens?: { entrada?: number; saida?: number }; duracao?: number; erro?: string }
  | { tipo: 'erro'; texto: string }
  | { tipo: 'saiu'; codigo: number | null })
export type InfoChat = { id: string; agente: AgenteIA; titulo: string; alvo: string; cwd: string; viva: boolean; ocupado: boolean; criada: number; modelo?: string }
export type PonteChat = {
  abrir(p: PedidoSessao & { modelo?: string }): Promise<InfoChat>
  listar(): Promise<InfoChat[]>
  eventos(id: string): Promise<EventoChat[]>
  enviar(id: string, texto: string): Promise<void>
  responder(id: string, perm: string, d: Decisao): Promise<void>
  interromper(id: string): Promise<void>
  fechar(id: string): Promise<void>
  aoEvento(f: (id: string, e: EventoChat) => void): () => void
}

// terminal embutido das conversas com a IA (só no Electron)
export type PonteIA = {
  disponivel(): Promise<Record<AgenteIA, boolean>>
  abrir(p: PedidoSessao, cols: number, rows: number): Promise<InfoSessao>
  listar(): Promise<InfoSessao[]>
  saida(id: string): Promise<{ texto: string; total: number }>
  escrever(id: string, dados: string): void
  redimensionar(id: string, cols: number, rows: number): void
  parar(id: string): Promise<void>
  fechar(id: string): Promise<void>
  aoDados(f: (id: string, d: string, total: number) => void): () => void
  aoSair(f: (id: string, codigo: number) => void): () => void
}

type Ponte = {
  infoMotor(): Promise<InfoMotor>
  reiniciarMotor(): Promise<InfoMotor>
  escolherVideo(): Promise<string | null>
  escolherPasta(): Promise<string | null>
  escolherZip(): Promise<string | null>
  escolherCookies(): Promise<string | null>
  salvarArquivo(nome: string): Promise<string | null>
  definirWorkspace(p: string): Promise<InfoMotor>
  definirTema(t: string): Promise<void>
  mostrarNaPasta(p: string): Promise<void>
  abrir(p: string): Promise<string>
  lixeira?(p: string): Promise<void>
  idiomaSistema(): Promise<string>
  ia?: PonteIA
  chat?: PonteChat
}

declare global {
  interface Window {
    clipator?: Ponte
  }
}

const params = new URLSearchParams(location.search)

const web: Ponte = {
  infoMotor: async () => ({ porta: Number(params.get('porta') ?? 8765), token: params.get('token') ?? 'dev', log: '', workspace: '' }),
  reiniciarMotor: async () => web.infoMotor(),
  escolherVideo: async () => prompt('Caminho do arquivo de vídeo'),
  escolherPasta: async () => prompt('Caminho da pasta'),
  escolherZip: async () => prompt('Caminho do arquivo .zip'),
  escolherCookies: async () => prompt('Caminho do arquivo cookies.txt'),
  salvarArquivo: async (nome) => prompt('Salvar em (caminho completo)', nome),
  definirWorkspace: async () => web.infoMotor(),
  definirTema: async () => undefined,
  mostrarNaPasta: async () => undefined,
  abrir: async () => '',
  idiomaSistema: async () => navigator.language
}

export const ponte: Ponte = window.clipator ?? web
export const noElectron = Boolean(window.clipator)
