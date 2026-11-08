// node --test (o Node tira os tipos sozinho): npm run test
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { chavePasso, chavePassoAntiga, lerPasso, passoGuardado, passoPadrao } from './passos.ts'

class Armazem {
  dados = new Map<string, string>()
  getItem(k: string): string | null { return this.dados.has(k) ? this.dados.get(k)! : null }
  setItem(k: string, v: string): void { this.dados.set(k, v) }
  removeItem(k: string): void { this.dados.delete(k) }
}

test('o passo antigo cai na mesma tela com o número novo', () => {
  assert.equal(passoGuardado(null, '1'), 1)
  assert.equal(passoGuardado(null, '2'), 2)
  assert.equal(passoGuardado(null, '3'), 4) // clips gerados
  assert.equal(passoGuardado(null, '4'), 5) // publicação
  assert.equal(passoGuardado(null, '7'), null)
  assert.equal(passoGuardado(null, 'x'), null)
  assert.equal(passoGuardado('3', '3'), 3) // o novo (Estilo) vale mais que o antigo
  assert.equal(passoGuardado('9', '2'), 2)
  assert.equal(passoGuardado(null, null), null)
})

test('lerPasso migra a chave antiga uma vez', () => {
  const a = new Armazem()
  a.setItem(chavePassoAntiga('c', 'p'), '3')
  assert.equal(lerPasso(a, 'c', 'p'), 4)
  assert.equal(a.getItem(chavePasso('c', 'p')), '4')
  assert.equal(a.getItem(chavePassoAntiga('c', 'p')), null)
  assert.equal(lerPasso(a, 'c', 'p'), 4)
  assert.equal(lerPasso(a, 'c', 'outro'), null)
})

test('passo padrão', () => {
  assert.equal(passoPadrao(false, false, false), 1)
  assert.equal(passoPadrao(true, true, true), 4)
  assert.equal(passoPadrao(true, false, true), 2)
  assert.equal(passoPadrao(true, false, false), 1)
})
