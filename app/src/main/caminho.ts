// Acha um executável no PATH e devolve o caminho completo.
//
// No Windows, pedir só "clipator" ao spawn (ainda mais com shell) faz o cmd procurar
// primeiro na pasta atual e na pasta do próprio app, onde está o Clipator.exe. O app
// abria a si mesmo no lugar do motor, e cada cópia abria outra. Por isso o motor
// sempre sobe pelo caminho completo, e o executável do próprio app nunca conta.

export type Plataforma = 'win32' | 'darwin' | 'linux' | string

export function acharNoPath(
  nome: string,
  path: string,
  plataforma: Plataforma,
  existe: (p: string) => boolean,
  proibido: string[] = []
): string | null {
  const win = plataforma === 'win32'
  const sep = win ? ';' : ':'
  const barra = win ? '\\' : '/'
  const exts = win ? ['.exe', '.cmd', '.bat'] : ['']
  const igual = (a: string, b: string): boolean => (win ? a.toLowerCase() === b.toLowerCase() : a === b)
  for (const dir of path.split(sep)) {
    const d = dir.trim().replace(/^"(.*)"$/, '$1')
    // só pastas absolutas: "." ou pastas relativas apontariam para a pasta do app
    if (!d || !(win ? /^[a-zA-Z]:[\\/]|^\\\\/.test(d) : d.startsWith('/'))) continue
    for (const e of exts) {
      const p = d.replace(/[\\/]+$/, '') + barra + nome + e
      if (proibido.some((x) => igual(x, p))) continue
      if (existe(p)) return p
    }
  }
  return null
}
