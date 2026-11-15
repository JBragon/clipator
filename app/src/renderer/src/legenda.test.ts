// node --test (o Node tira os tipos sozinho): npm run test
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { juntar, tempo, trocarEmTodas, type Frase } from './legenda.ts'

const f = (inicio: number, fim: number, texto: string): Frase => ({ inicio, fim, texto, palavras: [{ texto, inicio, fim }] })

test('trocar em todas acha sem diferenciar maiúsculas e conta as trocas', () => {
  const [out, n] = trocarEmTodas([f(0, 1, 'o Jao chegou'), f(1, 2, 'jao e Jao'), f(2, 3, 'nada')], 'jao', 'João')
  assert.equal(n, 3)
  assert.deepEqual(out.map((x) => x.texto), ['o João chegou', 'João e João', 'nada'])
})

test('trocar trata o texto como texto, não como expressão regular', () => {
  const [out, n] = trocarEmTodas([f(0, 1, 'custa R$ 5 (cinco)')], 'R$ 5 (cinco)', 'R$ 5')
  assert.equal(n, 1)
  assert.equal(out[0].texto, 'custa R$ 5')
  assert.deepEqual(trocarEmTodas([f(0, 1, 'a')], '  ', 'b')[1], 0)
})

test('juntar une texto, tempos e palavras com a próxima', () => {
  const out = juntar([f(0, 1, 'um'), f(1.2, 2, 'dois'), f(3, 4, 'três')], 0)
  assert.equal(out.length, 2)
  assert.deepEqual({ ...out[0], palavras: out[0].palavras.length }, { inicio: 0, fim: 2, texto: 'um dois', palavras: 2 })
  assert.equal(juntar(out, 1), out) // a última não tem com quem juntar
})

test('tempo em minutos e segundos com centésimos', () => {
  assert.equal(tempo(0), '0:00.00')
  assert.equal(tempo(75.456), '1:15.46')
})
