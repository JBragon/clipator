// Cliente da API local do motor.

export type Etapas = Record<string, { status: string; atualizado_em?: string; erro?: string }>

export type Candidato = {
  id: string
  inicio: number
  fim: number
  duracao: number
  nota: number
  nota_local?: number
  motivos: string[]
  titulos?: string[]
  texto: string
  modo: 'curto' | 'longo'
  fonte: string
  sinais?: Record<string, number>
  ia?: { agente: string; motivo: string; gancho: string; destaques: string[]; fecha_assunto?: boolean }
  pesos?: Record<string, number>
  fator_duracao?: number
  fechamento?: string[]
  ajuste_ia?: { inicio: number; fim: number }
}

export type Clip = {
  id: string
  candidato?: string
  inicio: number
  fim: number
  titulo: string
  titulos_sugeridos: string[]
  gancho: string
  formato: string
  plataforma?: string | null
  versao?: string | null
  pedido_ia?: { agente: 'claude' | 'codex'; texto: string; abrir_ao_terminar: boolean; enviado?: string | null; erro?: string | null } | null
  estilo: string
  cartela: boolean
  cortes_internos: [number, number][]
  ajustes_estilo: Record<string, unknown>
  status: string
  pasta?: string
  saida?: boolean
  preview?: boolean
}

export type Job = {
  id: string
  tipo: string
  params: Record<string, unknown>
  status: string
  progresso: number
  mensagem: string
  erro?: string
  log?: string
  linha_log?: string
  linhas?: string[] // as linhas do log que chegaram ao vivo (o App junta)
  aguardando?: string | null
  etapa?: string | null
  progresso_etapa?: number | null
  etapa_iniciado?: number | null
  etapa_progresso_inicial?: number | null
  iniciado?: number | null
  terminado?: number | null
  criado: number
  resultado?: Record<string, unknown> | null
}

export type NoArvore = { nome: string; caminho: string; tipo: 'pasta' | 'arquivo'; filhos?: NoArvore[]; tamanho?: number }
export type DetalhesEstilo = {
  legenda: { fonte: string; tamanho: number; cor: string; destaque: string; contorno: string; posicao: string; animacao: string; modo: string; caixa_alta: boolean; fundo: string | null }
  cartela: boolean; zoom: boolean; intensidade_zoom: number; jump_cuts: boolean; sons: Record<string, string>; volume_sons: number
  musica: boolean; logo: boolean; reenquadramento: string; direcao?: string; ficha?: string
  dividido?: { em_cima: string; tamanho_rosto: number }
}
export type Estilo = {
  id: string; nome: string; descricao?: string; objetivo?: string[]; formato?: string; motor?: string; nivel_ia?: string; erro?: string
  embutido?: boolean; caminho: string; origem?: 'embutido' | 'workspace' | 'canal' | 'skill'; padrao?: boolean; detalhes?: DetalhesEstilo; amostra?: string | null
  requer_ia?: boolean
}
export type Transcricao = { idioma: string; duracao: number; segmentos: { inicio: number; fim: number; texto: string }[] }
export type ErroValidacao = { linha: number; mensagem: string }

export class Api {
  constructor(public base: string, public token: string) {}

  url(caminho: string, q: Record<string, string> = {}): string {
    const u = new URL(this.base + caminho)
    for (const [k, v] of Object.entries(q)) u.searchParams.set(k, v)
    return u.toString()
  }

  midia(caminho: string, versao = ''): string {
    return this.url('/api/midia', { caminho, token: this.token, v: versao })
  }

  async req<T>(metodo: string, caminho: string, corpo?: unknown, q: Record<string, string> = {}): Promise<T> {
    const r = await fetch(this.url(caminho, q), {
      method: metodo,
      headers: { 'x-clipator-token': this.token, ...(corpo !== undefined ? { 'content-type': 'application/json' } : {}) },
      body: corpo !== undefined ? JSON.stringify(corpo) : undefined
    })
    if (!r.ok) {
      let msg = `${r.status}`
      try {
        const j = await r.json()
        msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail)
      } catch {
        /* resposta sem JSON */
      }
      throw new Error(msg)
    }
    return (await r.json()) as T
  }

  get = <T>(c: string, q?: Record<string, string>) => this.req<T>('GET', c, undefined, q)
  post = <T>(c: string, corpo?: unknown, q?: Record<string, string>) => this.req<T>('POST', c, corpo ?? {}, q)
  put = <T>(c: string, corpo: unknown) => this.req<T>('PUT', c, corpo)
  del = <T>(c: string, q?: Record<string, string>) => this.req<T>('DELETE', c, undefined, q)

  eventos(aoJob: (j: Job) => void): () => void {
    let ws: WebSocket | null = null
    let parar = false
    const abrir = (): void => {
      ws = new WebSocket(this.base.replace('http', 'ws') + `/api/eventos?token=${encodeURIComponent(this.token)}`)
      ws.onmessage = (ev) => {
        const m = JSON.parse(ev.data)
        if (m.tipo === 'job') aoJob(m.job as Job)
      }
      ws.onclose = () => {
        if (!parar) setTimeout(abrir, 1500)
      }
    }
    abrir()
    return () => {
      parar = true
      ws?.close()
    }
  }
}

export const proj = (canal: string, projeto: string): string =>
  `/api/canais/${encodeURIComponent(canal)}/projetos/${encodeURIComponent(projeto)}`

export function hms(t: number): string {
  const s = Math.max(0, Math.floor(t))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const ss = String(s % 60).padStart(2, '0')
  return h ? `${h}:${String(m).padStart(2, '0')}:${ss}` : `${m}:${ss}`
}
