// Contas da tela "Editar duração": arrastar o início, o fim ou a faixa inteira do corte na trilha do
// vídeo pai, encaixar nas bordas das palavras e escolher a janela da trilha de perto.
// Sem React nem DOM, para testar com `node --test` (trecho.test.ts).

export type Trecho = { inicio: number; fim: number }
export type Modo = 'inicio' | 'fim' | 'faixa'

export const DURACAO_MIN = 1 // igual ao motor (trecho.py)

const arred = (t: number): number => Math.round(t * 1000) / 1000

// O trecho depois de arrastar `delta` segundos a partir de `orig`, sempre dentro do vídeo
// e com pelo menos DURACAO_MIN. Arrastar a faixa mantém a duração e para na borda do vídeo.
export function arrastar(modo: Modo, orig: Trecho, delta: number, total: number, min = DURACAO_MIN): Trecho {
  if (modo === 'faixa') {
    const dur = orig.fim - orig.inicio
    const ini = Math.max(0, Math.min(total - dur, orig.inicio + delta))
    return { inicio: arred(ini), fim: arred(ini + dur) }
  }
  if (modo === 'inicio') {
    const ini = Math.max(0, Math.min(orig.fim - min, orig.inicio + delta))
    return { inicio: arred(ini), fim: orig.fim }
  }
  const fim = Math.min(total, Math.max(orig.inicio + min, orig.fim + delta))
  return { inicio: orig.inicio, fim: arred(fim) }
}

// Bordas onde dá para encaixar: começo de cada palavra (para o início) e fim (para o fim).
export type Bordas = { inicios: number[]; fins: number[] }
export function bordasDasPalavras(segmentos: { palavras?: { inicio: number; fim: number }[] }[]): Bordas {
  const inicios: number[] = []
  const fins: number[] = []
  for (const s of segmentos) for (const p of s.palavras ?? []) {
    inicios.push(p.inicio)
    fins.push(p.fim)
  }
  return { inicios: inicios.sort((a, b) => a - b), fins: fins.sort((a, b) => a - b) }
}

// A borda mais próxima de `t` (lista ordenada), se estiver a até `tolerancia` segundos.
export function encaixar(t: number, bordas: number[], tolerancia: number): number {
  let lo = 0
  let hi = bordas.length
  while (lo < hi) {
    const m = (lo + hi) >> 1
    if (bordas[m] < t) lo = m + 1
    else hi = m
  }
  let melhor = t
  let dist = tolerancia
  for (const i of [lo - 1, lo]) {
    if (i < 0 || i >= bordas.length) continue
    const d = Math.abs(bordas[i] - t)
    if (d <= dist) {
      melhor = bordas[i]
      dist = d
    }
  }
  return melhor
}

// Arrastar com o encaixe nas palavras. Na faixa inteira quem encaixa é o início, e a duração fica igual.
export function arrastarEncaixado(modo: Modo, orig: Trecho, delta: number, total: number, bordas: Bordas | null,
  tolerancia: number): Trecho {
  const r = arrastar(modo, orig, delta, total)
  if (!bordas) return r
  if (modo === 'fim') return arrastar('fim', orig, encaixar(r.fim, bordas.fins, tolerancia) - orig.fim, total)
  const ini = encaixar(r.inicio, bordas.inicios, tolerancia)
  return arrastar(modo, orig, ini - orig.inicio, total)
}

// Janela da trilha "de perto": o corte com folga dos dois lados para ver o que vem antes e depois.
export function janelaDePerto(t: Trecho, total: number): [number, number] {
  const dur = t.fim - t.inicio
  const folga = Math.max(15, dur * 0.6)
  let a = t.inicio - folga
  let b = t.fim + folga
  if (a < 0) {
    b = Math.min(total, b - a)
    a = 0
  }
  if (b > total) {
    a = Math.max(0, a - (b - total))
    b = total
  }
  return [a, b]
}

// Marcas de tempo da régua: um passo "redondo" que dá por volta de `alvo` marcas na janela.
export function marcas(a: number, b: number, alvo = 8): number[] {
  const passos = [0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600]
  const passo = passos.find((p) => (b - a) / p <= alvo) ?? 3600
  const out: number[] = []
  for (let t = Math.ceil(a / passo) * passo; t <= b; t += passo) out.push(arred(t))
  return out
}

// "1:02.5" (minutos, segundos e décimos) para o campo de tempo; aceita também "62.5" e "1:02,5".
export function mmss(t: number): string {
  const d = Math.round(Math.max(0, t) * 10) / 10
  const h = Math.floor(d / 3600)
  const m = Math.floor((d % 3600) / 60)
  const s = (d % 60).toFixed(1).padStart(4, '0')
  return h ? `${h}:${String(m).padStart(2, '0')}:${s}` : `${m}:${s}`
}
export function lerTempo(txt: string): number | null {
  const partes = txt.trim().replace(',', '.').split(':')
  if (!partes.length || partes.length > 3 || partes.some((p) => !/^\d+(\.\d+)?$/.test(p))) return null
  return partes.reduce((acc, p) => acc * 60 + Number(p), 0)
}
