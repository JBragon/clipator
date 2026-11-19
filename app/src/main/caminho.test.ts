import { test } from 'node:test'
import assert from 'node:assert/strict'
import { acharNoPath } from './caminho.ts'

const existeEm = (lista: string[]) => (p: string) => lista.includes(p)

test('no Windows, nunca devolve o executável do próprio app', () => {
  const app = 'C:\\Users\\a\\AppData\\Local\\Programs\\clipator-app\\Clipator.exe'
  const motor = 'C:\\Users\\a\\.local\\bin\\clipator.exe'
  const path = 'C:\\Users\\a\\AppData\\Local\\Programs\\clipator-app;C:\\Users\\a\\.local\\bin'
  assert.equal(acharNoPath('clipator', path, 'win32', existeEm([app, motor]), [app]), motor)
})

test('no Windows, compara o caminho proibido sem diferenciar maiúsculas', () => {
  const app = 'C:\\Programs\\Clipator\\clipator.exe'
  assert.equal(acharNoPath('clipator', 'C:\\Programs\\Clipator', 'win32', existeEm([app]), [app.toUpperCase()]), null)
})

test('ignora pastas relativas e o ponto, que apontariam para a pasta do app', () => {
  const p = acharNoPath('clipator', '.;bin;C:\\x', 'win32', (c) => !c.startsWith('C:'), [])
  assert.equal(p, null)
})

test('aceita .cmd no Windows e pastas entre aspas', () => {
  const alvo = 'C:\\Meu Bin\\clipator.cmd'
  assert.equal(acharNoPath('clipator', '"C:\\Meu Bin\\"', 'win32', existeEm([alvo])), alvo)
})

test('no Linux e no Mac, devolve o caminho completo sem extensão', () => {
  assert.equal(acharNoPath('clipator', '/usr/bin:/home/a/.local/bin', 'linux', existeEm(['/home/a/.local/bin/clipator'])), '/home/a/.local/bin/clipator')
  assert.equal(acharNoPath('clipator', '/usr/bin', 'darwin', existeEm([])), null)
})
