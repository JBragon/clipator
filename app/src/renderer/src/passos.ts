// Passos da tela do vídeo. O passo 3 (Estilo) entrou entre os cortes e os clips, e depois o passo 4 (Checagem de
// fatos) entrou entre o estilo e os clips: quem tinha guardado um passo antigo cai na mesma tela com o número novo.
export type Passo = 1 | 2 | 3 | 4 | 5 | 6
export const PASSO_ESTILO: Passo = 3
export const PASSO_CHECAGEM: Passo = 4
export const PASSO_CLIPS: Passo = 5
export const PASSO_PUBLICACAO: Passo = 6

export const chavePasso = (canal: string, projeto: string): string => `clipator.passo.v3.${canal}/${projeto}`
// v2: 1 vídeo, 2 cortes, 3 estilo, 4 clips, 5 publicação
export const chavePassoV2 = (canal: string, projeto: string): string => `clipator.passo.v2.${canal}/${projeto}`
// v1: 1 vídeo, 2 cortes, 3 clips, 4 publicação
export const chavePassoAntiga = (canal: string, projeto: string): string => `clipator.passo.${canal}/${projeto}`

const DO_V2: Record<number, Passo> = { 1: 1, 2: 2, 3: PASSO_ESTILO, 4: PASSO_CLIPS, 5: PASSO_PUBLICACAO }
const DO_ANTIGO: Record<number, Passo> = { 1: 1, 2: 2, 3: PASSO_CLIPS, 4: PASSO_PUBLICACAO }

const valido = (v: number): v is Passo => Number.isInteger(v) && v >= 1 && v <= 6

const converter = (s: string | null, mapa: Record<number, Passo>): Passo | null => {
  if (s === null || s === '') return null
  const v = Number(s)
  return Number.isInteger(v) && mapa[v] ? mapa[v] : null
}

// o passo guardado (no formato novo) ou o de um formato antigo convertido; null se não houver nada que preste
export function passoGuardado(novo: string | null, antigo: string | null, v2: string | null = null): Passo | null {
  if (novo !== null && novo !== '') {
    const v = Number(novo)
    if (valido(v)) return v
  }
  return converter(v2, DO_V2) ?? converter(antigo, DO_ANTIGO)
}

// lê do armazenamento (migrando as chaves antigas para a nova)
export function lerPasso(armazem: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>, canal: string, projeto: string): Passo | null {
  const novo = armazem.getItem(chavePasso(canal, projeto))
  const v2 = armazem.getItem(chavePassoV2(canal, projeto))
  const antigo = armazem.getItem(chavePassoAntiga(canal, projeto))
  const p = passoGuardado(novo, antigo, v2)
  if (antigo !== null || v2 !== null) {
    if (p !== null && novo === null) armazem.setItem(chavePasso(canal, projeto), String(p))
    armazem.removeItem(chavePassoAntiga(canal, projeto))
    armazem.removeItem(chavePassoV2(canal, projeto))
  }
  return p
}

// O que a tela sabe para decidir quais passos já abrem.
export type EstadoPassos = {
  analiseFeita: boolean // a análise do passo 1 terminou (e não está rodando de novo)
  temCortes: boolean // o passo 2 tem cortes sugeridos
  temSelecao: boolean // algum corte escolhido no passo 2
  temClips: boolean // algum clip criado (no passo 3 ou no 4)
  temVideoGerado: boolean // algum clip com o vídeo final gerado no passo 5
}

// Cada passo só abre com o anterior concluído. A checagem de fatos (4) é opcional: os clips podem ser criados
// direto no passo 3, então o passo 5 só pede que exista algum clip, e o 4 abre junto com o 3.
export function passoLiberado(p: Passo, e: EstadoPassos): boolean {
  if (p === 1) return true
  if (p === 2) return e.analiseFeita && e.temCortes
  if (p === PASSO_ESTILO || p === PASSO_CHECAGEM) return passoLiberado(2, e) && (e.temSelecao || e.temClips)
  if (p === PASSO_CLIPS) return e.temClips
  return e.temClips && e.temVideoGerado // publicação
}

// o passo que a tela mostra: o pedido, se já abriu; senão o último liberado antes dele
export function passoPermitido(p: Passo, e: EstadoPassos): Passo {
  for (let n = p; n > 1; n--) if (passoLiberado(n as Passo, e)) return n as Passo
  return 1
}

// passo em que o vídeo abre quando nada foi guardado
export function passoPadrao(analisePronta: boolean, temClips: boolean, temCortes: boolean): Passo {
  if (!analisePronta) return 1
  if (temClips) return PASSO_CLIPS
  return temCortes ? 2 : 1
}
