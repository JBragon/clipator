import { test } from 'node:test'
import assert from 'node:assert/strict'
import { avaliarRelease, compararVersoes, fonteMotor, scriptUnix, scriptWindows, temPacote } from './atualizacao.ts'

const assets = [{ name: 'Clipator-Setup-0.1.2.exe' }, { name: 'Clipator-0.1.2-arm64.dmg' }, { name: 'Clipator-0.1.2.AppImage' }]

test('compara versões número a número, com ou sem o v', () => {
  assert.equal(compararVersoes('v0.1.10', '0.1.9'), 1)
  assert.equal(compararVersoes('0.1.1', 'v0.1.1'), 0)
  assert.equal(compararVersoes('0.2', '0.2.0'), 0)
  assert.equal(compararVersoes('0.1.1', '0.2.0'), -1)
  assert.equal(compararVersoes('1.0.0', '0.99.99'), 1)
})

test('só oferece a atualização quando a release é mais nova e tem o pacote do sistema', () => {
  const r = { tag_name: 'v0.1.2', html_url: 'https://github.com/JBragon/clipator/releases/tag/v0.1.2', assets }
  assert.deepEqual(avaliarRelease(r, '0.1.1', 'win32'), {
    atual: '0.1.1',
    nova: '0.1.2',
    tag: 'v0.1.2',
    pagina: 'https://github.com/JBragon/clipator/releases/tag/v0.1.2'
  })
  assert.equal(avaliarRelease(r, '0.1.2', 'win32'), null)
  assert.equal(avaliarRelease(r, '0.2.0', 'darwin'), null)
  // a release ainda está sendo montada: o .exe já subiu, o .dmg ainda não
  assert.equal(avaliarRelease({ ...r, assets: [assets[0]] }, '0.1.1', 'darwin'), null)
  assert.ok(avaliarRelease({ ...r, assets: [assets[0]] }, '0.1.1', 'win32'))
})

test('ignora rascunhos, pré-lançamentos e tags que não são versão', () => {
  assert.equal(avaliarRelease({ tag_name: 'v9.0.0', draft: true, assets }, '0.1.1', 'linux'), null)
  assert.equal(avaliarRelease({ tag_name: 'v9.0.0', prerelease: true, assets }, '0.1.1', 'linux'), null)
  assert.equal(avaliarRelease({ tag_name: 'v9.0.0-beta', assets }, '0.1.1', 'linux'), null)
  assert.equal(avaliarRelease({ tag_name: 'teste', assets }, '0.1.1', 'linux'), null)
  assert.equal(avaliarRelease({}, '0.1.1', 'linux'), null)
})

test('acha o pacote de cada sistema pela extensão', () => {
  assert.ok(temPacote(assets, 'linux'))
  assert.ok(!temPacote([{ name: 'latest.yml' }, { name: 'Clipator-Setup.exe.blockmap' }], 'win32'))
})

test('o motor vem do zip da mesma tag', () => {
  assert.equal(fonteMotor('v0.1.2'), 'clipator[visao] @ https://github.com/JBragon/clipator/archive/refs/tags/v0.1.2.zip#subdirectory=motor')
})

test('o script do Windows espera o app fechar, roda o install.ps1 da tag e reabre o app', () => {
  const s = scriptWindows({ tag: 'v0.1.2', pid: 4321, executavel: "C:\\Users\\D'Ávila\\AppData\\Local\\Programs\\clipator-app\\Clipator.exe" })
  assert.match(s, /Wait-Process -Id 4321/)
  assert.match(s, /raw\.githubusercontent\.com\/JBragon\/clipator\/v0\.1\.2\/install\.ps1/)
  assert.match(s, /\$env:CLIPATOR_SIM = '1'/)
  // aspas simples do caminho dobradas, como o PowerShell pede
  assert.ok(s.includes("$app = 'C:\\Users\\D''Ávila\\AppData\\Local\\Programs\\clipator-app\\Clipator.exe'"))
  assert.match(s, /Start-Process -FilePath \$app/)
})

test('o script do Mac e do Linux roda o install.sh da tag sem perguntas e reabre o app', () => {
  const mac = scriptUnix({ tag: 'v0.1.2', pid: 99, executavel: '/Applications/Clipator.app/Contents/MacOS/Clipator' }, 'darwin')
  assert.match(mac, /kill -0 99/)
  assert.match(mac, /clipator\/v0\.1\.2\/install\.sh' \| bash -s -- --sim/)
  assert.match(mac, /open "\$destino"; else open -a Clipator/)
  const linux = scriptUnix({ tag: 'v0.1.2', pid: 99, executavel: '/tmp/.mount_x/clipator-app', appImage: "/home/a/Apps/it's/Clipator.AppImage" }, 'linux')
  assert.ok(linux.includes("antigo='/home/a/Apps/it'\\''s/Clipator.AppImage'"))
  assert.match(linux, /nohup "\$destino"/)
  assert.ok(!linux.includes('open -a'))
})
