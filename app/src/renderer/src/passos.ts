// Passos da tela do vídeo. O passo 3 (Estilo) entrou entre os cortes e os clips: quem tinha guardado o
// passo antigo (1 vídeo, 2 cortes, 3 clips, 4 publicação) cai na mesma tela com o número novo.
export type Passo = 1 | 2 | 3 | 4 | 5
export const PASSO_ESTILO: Passo = 3
export const PASSO_CLIPS: Passo = 4
export const PASSO_PUBLICACAO: Passo = 5

export const chavePasso = (canal: string, projeto: string): string => `clipator.passo.v2.${canal}/${projeto}`
export const chavePassoAntiga = (canal: string, projeto: string): string => `clipator.passo.${canal}/${projeto}`

const DO_ANTIGO: Record<number, Passo> = { 1: 1, 2: 2, 3: PASSO_CLIPS, 4: PASSO_PUBLICACAO }

const valido = (v: number): v is Passo => Number.isInteger(v) && v >= 1 && v <= 5

// o passo guardado (no formato novo) ou o antigo convertido; null se não houver nada que preste
export function passoGuardado(novo: string | null, antigo: string | null): Passo | null {
  if (novo !== null && novo !== '') {
    const v = Number(novo)
    if (valido(v)) return v
  }
  if (antigo !== null && antigo !== '') {
    const v = Number(antigo)
    if (Number.isInteger(v) && DO_ANTIGO[v]) return DO_ANTIGO[v]
  }
  return null
}

// lê do armazenamento (migrando a chave antiga para a nova)
export function lerPasso(armazem: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>, canal: string, projeto: string): Passo | null {
  const novo = armazem.getItem(chavePasso(canal, projeto))
  const antigo = armazem.getItem(chavePassoAntiga(canal, projeto))
  const p = passoGuardado(novo, antigo)
  if (antigo !== null) {
    if (p !== null && novo === null) armazem.setItem(chavePasso(canal, projeto), String(p))
    armazem.removeItem(chavePassoAntiga(canal, projeto))
  }
  return p
}

// passo em que o vídeo abre quando nada foi guardado
export function passoPadrao(analisePronta: boolean, temClips: boolean, temCortes: boolean): Passo {
  if (!analisePronta) return 1
  if (temClips) return PASSO_CLIPS
  return temCortes ? 2 : 1
}
