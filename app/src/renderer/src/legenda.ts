// Funções da tela "Editar legenda" (passo 5), sem React, para os testes do node.

export type Palavra = { texto: string; inicio: number; fim: number }
export type Frase = { inicio: number; fim: number; texto: string; palavras: Palavra[] }
export const r2 = (v: number): number => Math.round(v * 100) / 100

export function tempo(v: number): string {
  const s = Math.max(0, v)
  const m = Math.floor(s / 60)
  return `${m}:${(s - m * 60).toFixed(2).padStart(5, '0')}`
}

// troca um texto em todas as frases (nomes que a transcrição errou sempre do mesmo jeito)
export function trocarEmTodas(frases: Frase[], de: string, para: string, maiusculas = false): [Frase[], number] {
  if (!de.trim()) return [frases, 0]
  const re = new RegExp(de.trim().replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), maiusculas ? 'g' : 'gi')
  let n = 0
  const out = frases.map((f) => {
    const texto = f.texto.replace(re, () => (n++, para))
    return texto === f.texto ? f : { ...f, texto }
  })
  return [out, n]
}

export function juntar(frases: Frase[], i: number): Frase[] {
  if (i < 0 || i + 1 >= frases.length) return frases
  const a = frases[i]
  const b = frases[i + 1]
  const nova: Frase = { inicio: a.inicio, fim: b.fim, texto: `${a.texto} ${b.texto}`.trim(), palavras: [...a.palavras, ...b.palavras] }
  return [...frases.slice(0, i), nova, ...frases.slice(i + 2)]
}
