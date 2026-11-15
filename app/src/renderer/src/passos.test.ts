// node --test (o Node tira os tipos sozinho): npm run test
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { chavePasso, chavePassoAntiga, chavePassoV2, lerPasso, passoGuardado, passoLiberado, passoPadrao, passoPermitido, type EstadoPassos, type Passo } from './passos.ts'

class Armazem {
  dados = new Map<string, string>()
  getItem(k: string): string | null { return this.dados.has(k) ? this.dados.get(k)! : null }
  setItem(k: string, v: string): void { this.dados.set(k, v) }
  removeItem(k: string): void { this.dados.delete(k) }
}

test('o passo antigo cai na mesma tela com o número novo', () => {
  assert.equal(passoGuardado(null, '1'), 1)
  assert.equal(passoGuardado(null, '2'), 2)
  assert.equal(passoGuardado(null, '3'), 5) // clips gerados
  assert.equal(passoGuardado(null, '4'), 6) // publicação
  assert.equal(passoGuardado(null, '7'), null)
  assert.equal(passoGuardado(null, 'x'), null)
  assert.equal(passoGuardado('3', '3'), 3) // o novo (Estilo) vale mais que o antigo
  assert.equal(passoGuardado('4', null), 4) // checagem de fatos
  assert.equal(passoGuardado('9', '2'), 2)
  assert.equal(passoGuardado(null, null), null)
})

test('o passo da versão 2 (sem a checagem) também muda de número', () => {
  assert.equal(passoGuardado(null, null, '3'), 3) // estilo
  assert.equal(passoGuardado(null, null, '4'), 5) // clips gerados
  assert.equal(passoGuardado(null, null, '5'), 6) // publicação
  assert.equal(passoGuardado(null, '3', '4'), 5) // a v2 vale mais que a v1
  assert.equal(passoGuardado('4', null, '5'), 4)
})

test('lerPasso migra as chaves antigas uma vez', () => {
  const a = new Armazem()
  a.setItem(chavePassoAntiga('c', 'p'), '3')
  assert.equal(lerPasso(a, 'c', 'p'), 5)
  assert.equal(a.getItem(chavePasso('c', 'p')), '5')
  assert.equal(a.getItem(chavePassoAntiga('c', 'p')), null)
  assert.equal(lerPasso(a, 'c', 'p'), 5)
  assert.equal(lerPasso(a, 'c', 'outro'), null)
  a.setItem(chavePassoV2('c', 'q'), '4')
  assert.equal(lerPasso(a, 'c', 'q'), 5)
  assert.equal(a.getItem(chavePasso('c', 'q')), '5')
  assert.equal(a.getItem(chavePassoV2('c', 'q')), null)
})

const NADA: EstadoPassos = { analiseFeita: false, temCortes: false, temSelecao: false, temClips: false, temVideoGerado: false }
const abertos = (e: EstadoPassos): Passo[] => ([1, 2, 3, 4, 5, 6] as Passo[]).filter((p) => passoLiberado(p, e))

test('cada passo só abre com o anterior concluído', () => {
  assert.deepEqual(abertos(NADA), [1])
  assert.deepEqual(abertos({ ...NADA, analiseFeita: true }), [1]) // análise sem cortes
  assert.deepEqual(abertos({ ...NADA, temCortes: true }), [1]) // cortes antigos com a análise rodando de novo
  const comCortes = { ...NADA, analiseFeita: true, temCortes: true }
  assert.deepEqual(abertos(comCortes), [1, 2])
  assert.deepEqual(abertos({ ...comCortes, temSelecao: true }), [1, 2, 3, 4]) // a checagem é opcional
  assert.deepEqual(abertos({ ...comCortes, temClips: true }), [1, 2, 3, 4, 5]) // clips criados direto no passo 3
  assert.deepEqual(abertos({ ...comCortes, temClips: true, temVideoGerado: true }), [1, 2, 3, 4, 5, 6])
  assert.deepEqual(abertos({ ...NADA, temClips: true, temVideoGerado: true }), [1, 5, 6]) // análise refeita: os clips continuam
})

test('um passo guardado que ainda não abriu cai no último liberado antes dele', () => {
  const comCortes = { ...NADA, analiseFeita: true, temCortes: true }
  assert.equal(passoPermitido(6, comCortes), 2)
  assert.equal(passoPermitido(5, { ...comCortes, temSelecao: true }), 4)
  assert.equal(passoPermitido(3, NADA), 1)
  assert.equal(passoPermitido(5, { ...comCortes, temClips: true }), 5)
  assert.equal(passoPermitido(1, comCortes), 1)
})

test('passo padrão', () => {
  assert.equal(passoPadrao(false, false, false), 1)
  assert.equal(passoPadrao(true, true, true), 5)
  assert.equal(passoPadrao(true, false, true), 2)
  assert.equal(passoPadrao(true, false, false), 1)
})
