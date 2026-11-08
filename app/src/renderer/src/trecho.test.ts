// node --test (o Node tira os tipos sozinho): npm run test
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { arrastar, arrastarEncaixado, bordasDasPalavras, encaixar, janelaDePerto, lerTempo, marcas, mmss } from './trecho.ts'

test('puxar o início para trás aumenta o corte e não passa do começo do vídeo', () => {
  assert.deepEqual(arrastar('inicio', { inicio: 20, fim: 50 }, -5, 120), { inicio: 15, fim: 50 })
  assert.deepEqual(arrastar('inicio', { inicio: 20, fim: 50 }, -40, 120), { inicio: 0, fim: 50 })
})

test('o início não cruza o fim (fica pelo menos 1 s)', () => {
  assert.deepEqual(arrastar('inicio', { inicio: 20, fim: 50 }, 60, 120), { inicio: 49, fim: 50 })
  assert.deepEqual(arrastar('fim', { inicio: 20, fim: 50 }, -60, 120), { inicio: 20, fim: 21 })
})

test('o fim para no fim do vídeo', () => {
  assert.deepEqual(arrastar('fim', { inicio: 20, fim: 50 }, 100, 120), { inicio: 20, fim: 120 })
})

test('arrastar a faixa inteira mantém a duração e para nas bordas', () => {
  assert.deepEqual(arrastar('faixa', { inicio: 20, fim: 50 }, 10, 120), { inicio: 30, fim: 60 })
  assert.deepEqual(arrastar('faixa', { inicio: 20, fim: 50 }, 500, 120), { inicio: 90, fim: 120 })
  assert.deepEqual(arrastar('faixa', { inicio: 20, fim: 50 }, -500, 120), { inicio: 0, fim: 30 })
})

test('encaixa na borda de palavra mais próxima dentro da tolerância', () => {
  const b = [1, 2, 3.5, 7]
  assert.equal(encaixar(3.3, b, 0.4), 3.5)
  assert.equal(encaixar(5, b, 0.4), 5)
  assert.equal(encaixar(0, b, 2), 1)
})

test('com encaixe o início vai para o começo de uma palavra e o fim para o fim de uma', () => {
  const bordas = bordasDasPalavras([{ palavras: [{ inicio: 14.8, fim: 15.3 }, { inicio: 15.4, fim: 16 }] }, { palavras: [{ inicio: 49.2, fim: 50.6 }] }])
  assert.deepEqual(arrastarEncaixado('inicio', { inicio: 20, fim: 50 }, -5.1, 120, bordas, 0.5), { inicio: 14.8, fim: 50 })
  assert.deepEqual(arrastarEncaixado('fim', { inicio: 20, fim: 50 }, 0.4, 120, bordas, 0.5), { inicio: 20, fim: 50.6 })
  assert.deepEqual(arrastarEncaixado('faixa', { inicio: 20, fim: 50 }, -5.1, 120, bordas, 0.5), { inicio: 14.8, fim: 44.8 })
})

test('a janela de perto dá folga e fica dentro do vídeo', () => {
  assert.deepEqual(janelaDePerto({ inicio: 60, fim: 90 }, 600), [42, 108])
  assert.deepEqual(janelaDePerto({ inicio: 2, fim: 12 }, 600), [0, 40])
  assert.deepEqual(janelaDePerto({ inicio: 590, fim: 600 }, 600), [560, 600])
})

test('régua com passo redondo', () => {
  assert.deepEqual(marcas(0, 40), [0, 5, 10, 15, 20, 25, 30, 35, 40])
  assert.equal(marcas(0, 3600).length <= 9, true)
})

test('tempo escrito e lido no campo', () => {
  assert.equal(mmss(62.54), '1:02.5')
  assert.equal(mmss(3725), '1:02:05.0')
  assert.equal(lerTempo('1:02,5'), 62.5)
  assert.equal(lerTempo('62.5'), 62.5)
  assert.equal(lerTempo('1:02:05'), 3725)
  assert.equal(lerTempo('abc'), null)
})
