// Página do modo remoto do Clipator (celular). Sem framework nem build: o motor serve este arquivo como está.
// Tudo roda no PC; aqui só se mostra o andamento, aprova cortes, manda um link novo e assiste ao clip pronto.
'use strict'

const TEXTOS = {
  pt: {
    parearTitulo: 'Conectar ao seu PC',
    parearDica: 'No app do Clipator no PC, abra Configurações → Modo remoto e leia o QR code com a câmera deste celular.',
    parearCodigo: 'Ou digite o código que aparece embaixo do QR code',
    nomeAparelho: 'Nome deste celular (aparece no PC)',
    conectar: 'Conectar',
    conectando: 'Conectando…',
    rodando: 'Rodando agora',
    nadaRodando: 'Nada rodando no PC agora.',
    canal: 'Canal',
    novoVideo: 'Novo vídeo',
    linkVideo: 'Link do YouTube ou da Twitch',
    analisar: 'Analisar no PC',
    enviado: 'Pronto: o PC começou a analisar o vídeo.',
    videos: 'Vídeos',
    semVideos: 'Nenhum vídeo neste canal ainda.',
    semCanais: 'Crie um canal no app do PC para começar.',
    cortes: 'Cortes',
    clips: 'Clips',
    nCortes: (n) => (n === 1 ? '1 corte' : `${n} cortes`),
    nClips: (n) => (n === 1 ? '1 clip' : `${n} clips`),
    semCortes: 'Os cortes aparecem aqui quando a análise terminar.',
    semClips: 'Selecione cortes nas abas Shorts ou Longos e toque em Aprovar para gerar os clips.',
    aprovar: (n) => (n === 1 ? 'Aprovar 1 corte e gerar' : `Aprovar ${n} cortes e gerar`),
    estilo: 'Estilo',
    estiloPadrao: 'padrão do canal',
    aprovado: (n) => (n === 1 ? 'Pronto: o PC está gerando o clip.' : `Pronto: o PC está gerando ${n} clips.`),
    jaVirouClip: 'já é clip',
    baixar: 'Baixar',
    semVideo: 'O vídeo deste clip ainda não foi gerado.',
    cancelar: 'Cancelar',
    abrirVideo: 'Abrir o vídeo',
    sair: 'Desconectar este celular',
    sairConfirma: 'Desconectar este celular do PC? Para voltar, leia o QR code de novo.',
    semConexao: 'O PC não respondeu. Ele está ligado, com o Clipator aberto e na mesma rede (ou no Tailscale)?',
    tentarDeNovo: 'Tentar de novo',
    fases: { pendente: 'esperando', baixando: 'baixando', analisando: 'analisando', cortes: 'cortes prontos', clips: 'com clips', erro: 'com erro' },
    status: { na_fila: 'na fila', rodando: 'rodando', ok: 'pronto', erro: 'erro', cancelado: 'cancelado', interrompido: 'interrompido' },
    statusClip: { selecionado: 'na fila', renderizando: 'gerando', renderizado: 'pronto', erro: 'erro' },
    tipos: { analisar: 'Análise do vídeo', renderizar: 'Gerando clips', ranquear: 'Nota da IA', transcrever: 'Transcrição', candidatos: 'Achando cortes', thumbnail: 'Thumbnail', postagem: 'Textos da postagem', checagem: 'Checagem de fatos', acabamento: 'Acabamento' },
    recentes: 'Terminados há pouco',
    shorts: 'Shorts',
    longos: 'Longos 16:9',
    previa: 'Prévia',
    fecharPrevia: 'Fechar prévia',
    selecionar: 'Selecionar',
    selecionado: 'Selecionado',
    limpar: 'Limpar',
    nSelecionados: (n) => (n === 1 ? '1 selecionado' : `${n} selecionados`),
    semShorts: 'Nenhum corte de short neste vídeo.',
    semLongos: 'Nenhum corte longo neste vídeo (o vídeo precisa ter mais de 8 minutos).',
    semPrevia: 'O vídeo original ainda não foi baixado.',
    conectado: 'conectado'
  },
  en: {
    parearTitulo: 'Connect to your PC',
    parearDica: 'In the Clipator app on your PC, open Settings → Remote mode and scan the QR code with this phone’s camera.',
    parearCodigo: 'Or type the code shown under the QR code',
    nomeAparelho: 'Name of this phone (shown on the PC)',
    conectar: 'Connect',
    conectando: 'Connecting…',
    rodando: 'Running now',
    nadaRodando: 'Nothing running on the PC right now.',
    canal: 'Channel',
    novoVideo: 'New video',
    linkVideo: 'YouTube or Twitch link',
    analisar: 'Analyze on the PC',
    enviado: 'Done: the PC started analyzing the video.',
    videos: 'Videos',
    semVideos: 'No videos in this channel yet.',
    semCanais: 'Create a channel in the PC app to get started.',
    cortes: 'Cuts',
    clips: 'Clips',
    nCortes: (n) => (n === 1 ? '1 cut' : `${n} cuts`),
    nClips: (n) => (n === 1 ? '1 clip' : `${n} clips`),
    semCortes: 'Cuts show up here when the analysis finishes.',
    semClips: 'Select cuts in the Shorts or Long tabs and tap Approve to make clips.',
    aprovar: (n) => (n === 1 ? 'Approve 1 cut and render' : `Approve ${n} cuts and render`),
    estilo: 'Style',
    estiloPadrao: 'channel default',
    aprovado: (n) => (n === 1 ? 'Done: the PC is rendering the clip.' : `Done: the PC is rendering ${n} clips.`),
    jaVirouClip: 'already a clip',
    baixar: 'Download',
    semVideo: 'This clip’s video has not been rendered yet.',
    cancelar: 'Cancel',
    abrirVideo: 'Open the video',
    sair: 'Disconnect this phone',
    sairConfirma: 'Disconnect this phone from the PC? To come back, scan the QR code again.',
    semConexao: 'The PC did not answer. Is it on, with Clipator open and on the same network (or on Tailscale)?',
    tentarDeNovo: 'Try again',
    fases: { pendente: 'waiting', baixando: 'downloading', analisando: 'analyzing', cortes: 'cuts ready', clips: 'has clips', erro: 'error' },
    status: { na_fila: 'queued', rodando: 'running', ok: 'done', erro: 'error', cancelado: 'canceled', interrompido: 'interrupted' },
    statusClip: { selecionado: 'queued', renderizando: 'rendering', renderizado: 'ready', erro: 'error' },
    tipos: { analisar: 'Video analysis', renderizar: 'Rendering clips', ranquear: 'AI score', transcrever: 'Transcription', candidatos: 'Finding cuts', thumbnail: 'Thumbnail', postagem: 'Post texts', checagem: 'Fact check', acabamento: 'Finishing' },
    recentes: 'Recently finished',
    shorts: 'Shorts',
    longos: 'Long 16:9',
    previa: 'Preview',
    fecharPrevia: 'Close preview',
    selecionar: 'Select',
    selecionado: 'Selected',
    limpar: 'Clear',
    nSelecionados: (n) => (n === 1 ? '1 selected' : `${n} selected`),
    semShorts: 'No short cuts in this video.',
    semLongos: 'No long cuts in this video (it needs to be longer than 8 minutes).',
    semPrevia: 'The original video has not been downloaded yet.',
    conectado: 'connected'
  }
}
let t = TEXTOS[(navigator.language || 'pt').toLowerCase().startsWith('pt') ? 'pt' : 'en']

// ---- utilidades ---------------------------------------------------------------------------------
// Monta elementos sem innerHTML: todo texto que vem do PC entra como texto, nunca como HTML.
function el(tag, attrs, ...filhos) {
  const e = document.createElement(tag)
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue
    if (k.startsWith('on')) e.addEventListener(k.slice(2), v)
    else if (k === 'class') e.className = v
    else if (k === 'style') e.style.cssText = v // pelo CSSOM, que a CSP da página permite
    else if (k in e && typeof v !== 'string') e[k] = v
    else e.setAttribute(k, v === true ? '' : v)
  }
  for (const f of filhos.flat()) if (f !== null && f !== undefined && f !== false) e.append(f instanceof Node ? f : String(f))
  return e
}
const $ = (id) => document.getElementById(id)
const enc = encodeURIComponent
const mmss = (s) => {
  s = Math.max(0, Math.round(s || 0))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const ss = String(s % 60).padStart(2, '0')
  return h ? `${h}:${String(m).padStart(2, '0')}:${ss}` : `${m}:${ss}`
}
const duracao = (s) => (s >= 90 ? `${Math.round(s / 60)} min` : `${Math.round(s)} s`)
const corNota = (n) => (n >= 65 ? 'alta' : n >= 45 ? 'media' : 'baixa')

class SemPareamento extends Error {}

async function api(metodo, caminho, corpo) {
  let r
  try {
    r = await fetch(caminho, {
      method: metodo,
      credentials: 'same-origin',
      headers: { 'x-clipator': '1', ...(corpo !== undefined ? { 'content-type': 'application/json' } : {}) },
      body: corpo !== undefined ? JSON.stringify(corpo) : undefined
    })
  } catch {
    throw new Error(t.semConexao)
  }
  if (r.status === 401) throw new SemPareamento()
  const j = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : `${r.status}`)
  return j
}

let avisoTimer = 0
function avisar(msg) {
  const a = $('aviso')
  a.textContent = msg
  a.hidden = false
  clearTimeout(avisoTimer)
  avisoTimer = setTimeout(() => (a.hidden = true), 4500)
}

// ---- estado -------------------------------------------------------------------------------------
// A página busca os dados a cada poucos segundos, mas só redesenha um pedaço da tela quando o que ele
// mostra mudou, e nunca enquanto a pessoa está usando um campo, uma lista ou um vídeo daquele pedaço.
// (Redesenhar a cada busca fechava a lista de estilos e fazia a tela pular.)
const estado = {
  canal: localStorage.getItem('clipator.canal') || '',
  aba: null, // 'shorts' | 'longos' | 'clips' (null: escolhe sozinho)
  marcados: new Set(),
  estiloEscolhido: '',
  previa: null, // id do corte com a prévia aberta
  projetoAberto: '',
  dados: null, // o que a tela atual mostra
  erro: null
}
const assinaturas = { jobs: '', conteudo: '', rodape: '' }
let timer = 0

function rota() {
  const m = location.hash.match(/^#\/p\/([^/]+)\/([^/]+)$/)
  return m ? { canal: decodeURIComponent(m[1]), projeto: decodeURIComponent(m[2]) } : null
}

async function buscar() {
  const st = await api('GET', '/m/api/estado')
  if (st.idioma && TEXTOS[st.idioma]) t = TEXTOS[st.idioma]
  const r = rota()
  if (r) {
    const chave = `${r.canal}/${r.projeto}`
    if (chave !== estado.projetoAberto) {
      Object.assign(estado, { projetoAberto: chave, aba: null, marcados: new Set(), estiloEscolhido: '', previa: null })
    }
    const base = `/m/api/canais/${enc(r.canal)}/projetos/${enc(r.projeto)}`
    const anterior = estado.dados && estado.dados.tela === 'projeto' && estado.dados.canal === r.canal ? estado.dados.estilos : null
    const [projeto, estilos] = await Promise.all([
      api('GET', base),
      anterior ? Promise.resolve(anterior) : api('GET', `/m/api/canais/${enc(r.canal)}/estilos`).catch(() => [])
    ])
    return { tela: 'projeto', st, canal: r.canal, base, projeto, estilos }
  }
  estado.projetoAberto = ''
  const canais = await api('GET', '/m/api/canais')
  if (canais.length && !canais.some((c) => c.slug === estado.canal)) estado.canal = (canais.find((c) => c.projetos > 0) || canais[0]).slug
  const projetos = canais.length ? await api('GET', `/m/api/canais/${enc(estado.canal)}/projetos`) : []
  return { tela: 'inicio', st, canais, projetos }
}

async function atualizar() {
  clearTimeout(timer)
  try {
    estado.dados = await buscar()
    estado.erro = null
  } catch (e) {
    if (e instanceof SemPareamento) {
      estado.dados = null
      return telaParear()
    }
    estado.erro = e.message
  }
  desenhar()
  // mais rápido quando tem coisa rodando; parado quando a aba está escondida
  const ativos = estado.dados && estado.dados.st.ativos.length
  if (!document.hidden) timer = setTimeout(atualizar, ativos ? 3000 : 10000)
}

// Alguém está mexendo neste pedaço da tela? Então não troca nada nele agora.
function emUso(caixa) {
  const a = document.activeElement
  if (a && caixa.contains(a) && /^(INPUT|SELECT|TEXTAREA)$/.test(a.tagName)) return true
  return [...caixa.querySelectorAll('video')].some((v) => !v.paused && !v.ended)
}

function pintar(id, assinatura, montar, forcar) {
  const caixa = $(id)
  if (!forcar && assinatura === assinaturas[id]) return
  if (!forcar && emUso(caixa)) return // tenta de novo na próxima busca
  assinaturas[id] = assinatura
  caixa.replaceChildren(...[montar()].flat().filter(Boolean))
}

function desenhar(forcar = false) {
  const d = estado.dados
  $('voltar').hidden = !rota()
  if (estado.erro && !d) {
    $('jobs').replaceChildren()
    $('rodape').replaceChildren()
    assinaturas.jobs = assinaturas.rodape = ''
    pintar('conteudo', `erro:${estado.erro}`, () => el('div', { class: 'vazio' },
      el('p', { class: 'erro' }, estado.erro),
      el('button', { class: 'botao', onclick: atualizar }, t.tentarDeNovo)), true)
    return
  }
  if (!d) return
  $('pc').textContent = estado.erro ? `${d.st.pc} · ${t.semConexao}` : d.st.pc
  $('ponto').className = `ponto ${estado.erro ? 'off' : 'on'}`
  const jobs = d.tela === 'projeto' ? d.st.ativos.filter((j) => j.projeto === d.projeto.id) : d.st.ativos
  pintar('jobs', JSON.stringify([d.tela, jobs, t === TEXTOS.en]), () => blocoJobs(jobs, d.tela === 'inicio'), forcar)
  if (d.tela === 'inicio') {
    pintar('conteudo', JSON.stringify([d.tela, estado.canal, d.canais, d.projetos]), () => telaInicio(d), forcar)
    pintar('rodape', '', () => null, forcar)
  } else {
    const p = d.projeto
    pintar('conteudo', JSON.stringify([d.tela, p, estado.aba, [...estado.marcados], estado.previa]), () => telaProjeto(d), forcar)
    pintar('rodape', JSON.stringify([estado.marcados.size, estado.estiloEscolhido, d.estilos, estado.aba]), () => rodapeAprovar(d), forcar)
  }
}

// ---- pareamento ---------------------------------------------------------------------------------
function nomeAparelho() {
  const ua = navigator.userAgent
  if (/iPhone/.test(ua)) return 'iPhone'
  if (/iPad/.test(ua)) return 'iPad'
  const m = ua.match(/Android[^;]*;\s*([^;)]+?)(?:\s+Build|\))/)
  return m && m[1] && m[1] !== 'K' ? m[1].trim() : /Android/.test(ua) ? 'Android' : 'Celular'
}

function telaParear(erro) {
  $('voltar').hidden = true
  $('jobs').replaceChildren()
  $('rodape').replaceChildren()
  Object.keys(assinaturas).forEach((k) => (assinaturas[k] = ''))
  const codigo = el('input', { name: 'codigo', autocomplete: 'one-time-code', autocapitalize: 'off', spellcheck: 'false', required: true })
  const nome = el('input', { name: 'nome', value: localStorage.getItem('clipator.nome') || nomeAparelho(), maxlength: '60' })
  const botao = el('button', { class: 'botao primario largo', type: 'submit' }, t.conectar)
  const form = el('form', {
    onsubmit: (ev) => {
      ev.preventDefault()
      botao.disabled = true
      botao.textContent = t.conectando
      parear(codigo.value, nome.value)
    }
  },
  el('label', { class: 'campo' }, t.parearCodigo, codigo),
  el('label', { class: 'campo' }, t.nomeAparelho, nome),
  botao)
  $('conteudo').replaceChildren(el('section', { class: 'pareamento' },
    el('img', { src: 'icone.svg', alt: '' }),
    el('h1', {}, t.parearTitulo),
    el('p', { class: 'dica' }, t.parearDica),
    erro ? el('p', { class: 'erro' }, erro) : null,
    form))
}

async function parear(codigo, nome) {
  try {
    localStorage.setItem('clipator.nome', nome)
    await api('POST', '/m/api/parear', { codigo: codigo.trim(), nome })
    atualizar()
  } catch (e) {
    telaParear(e instanceof SemPareamento ? (t === TEXTOS.en ? 'Invalid or expired code. Make a new one on the PC.' : 'Código inválido ou vencido. Gere outro no app do PC.') : e.message)
  }
}

// ---- jobs ---------------------------------------------------------------------------------------
function cartaoJob(j, comLink) {
  const andando = j.status === 'rodando' || j.status === 'na_fila'
  const pct = Math.round((j.progresso || 0) * 100)
  return el('div', { class: 'job' },
    el('div', { class: 'linha' },
      el('span', { class: `girando ${j.status === 'rodando' ? '' : 'parado'}`, 'aria-hidden': 'true' }),
      el('div', { class: 'cresce' },
        el('div', { class: 'titulo' }, t.tipos[j.tipo] || j.tipo),
        el('div', { class: 'meta' }, j.erro || j.mensagem || t.status[j.status] || '')),
      el('span', { class: 'pct' }, andando ? `${pct}%` : t.status[j.status] || j.status)),
    andando ? el('div', { class: 'barra' }, el('div', { style: `width:${pct}%` })) : null,
    el('div', { class: 'linha acoes' },
      comLink && j.canal && j.projeto ? el('a', { class: 'link', href: `#/p/${enc(j.canal)}/${enc(j.projeto)}` }, `${t.abrirVideo} ›`) : null,
      el('span', { class: 'cresce' }),
      andando ? el('button', {
        class: 'link perigo',
        onclick: async (ev) => {
          ev.currentTarget.disabled = true
          await api('POST', `/m/api/jobs/${enc(j.id)}/cancelar`).catch((e) => avisar(e.message))
          atualizar()
        }
      }, t.cancelar) : null))
}

function blocoJobs(jobs, inicio) {
  if (!jobs.length) return inicio ? el('p', { class: 'dica nada' }, t.nadaRodando) : null
  return el('div', {}, el('h2', {}, t.rodando), jobs.map((j) => cartaoJob(j, inicio)))
}

// ---- início -------------------------------------------------------------------------------------
function seloFase(fase) {
  const tipo = fase === 'erro' ? 'erro' : fase === 'clips' ? 'ok' : fase === 'baixando' || fase === 'analisando' ? 'andando' : ''
  return el('span', { class: `selo ${tipo}` }, t.fases[fase] || fase)
}

function telaInicio(d) {
  if (!d.canais.length) return [el('p', { class: 'vazio' }, t.semCanais), rodapeSair()]
  const sel = el('select', {
    class: 'campo-solto',
    'aria-label': t.canal,
    onchange: (ev) => {
      estado.canal = ev.target.value
      localStorage.setItem('clipator.canal', estado.canal)
      ev.target.blur()
      atualizar()
    }
  }, d.canais.map((c) => el('option', { value: c.slug, selected: c.slug === estado.canal }, c.nome)))

  const link = el('input', { type: 'url', inputmode: 'url', placeholder: 'https://youtube.com/watch?v=…', required: true, autocomplete: 'off' })
  const enviar = el('button', { class: 'botao primario', type: 'submit' }, t.analisar)
  const novo = el('form', {
    class: 'cartao novo',
    onsubmit: async (ev) => {
      ev.preventDefault()
      enviar.disabled = true
      try {
        const r = await api('POST', `/m/api/canais/${enc(estado.canal)}/projetos`, { link: link.value })
        avisar(t.enviado)
        link.blur()
        location.hash = `#/p/${enc(estado.canal)}/${enc(r.id)}`
      } catch (e) {
        avisar(e.message)
        enviar.disabled = false
      }
    }
  }, el('label', { class: 'campo' }, t.linkVideo, link), enviar)

  const lista = d.projetos.length
    ? d.projetos.map((p) => el('a', { class: 'cartao projeto', href: `#/p/${enc(estado.canal)}/${enc(p.id)}` },
      el('div', { class: 'cresce' },
        el('div', { class: 'titulo' }, p.titulo),
        el('div', { class: 'meta' }, `${t.nCortes(p.cortes)} · ${t.nClips(p.clips)}`)),
      seloFase(p.fase),
      el('span', { class: 'seta', 'aria-hidden': 'true' }, '›')))
    : [el('p', { class: 'vazio' }, t.semVideos)]

  return [
    el('h2', {}, t.canal), sel,
    el('h2', {}, t.novoVideo), novo,
    el('h2', {}, t.videos), ...lista,
    rodapeSair()
  ]
}

function rodapeSair() {
  return el('div', { style: 'margin-top:32px' }, el('button', {
    class: 'botao perigo largo',
    onclick: async () => {
      if (!confirm(t.sairConfirma)) return
      await api('POST', '/m/api/sair').catch(() => {})
      telaParear()
    }
  }, t.sair))
}

// ---- projeto ------------------------------------------------------------------------------------
function abaAtual(p) {
  const shorts = p.candidatos.filter((c) => c.modo !== 'longo')
  const longos = p.candidatos.filter((c) => c.modo === 'longo')
  if (estado.aba === 'longos' && longos.length) return 'longos'
  if (estado.aba) return estado.aba === 'longos' ? 'shorts' : estado.aba
  return shorts.length ? 'shorts' : longos.length ? 'longos' : 'clips'
}

function trocarAba(a) {
  estado.aba = a
  estado.previa = null
  desenhar(true)
  window.scrollTo({ top: 0 })
}

function telaProjeto(d) {
  const p = d.projeto
  const shorts = p.candidatos.filter((c) => c.modo !== 'longo').sort((a, b) => (b.nota || 0) - (a.nota || 0))
  const longos = p.candidatos.filter((c) => c.modo === 'longo').sort((a, b) => (b.nota || 0) - (a.nota || 0))
  const aba = abaAtual(p)
  const opcoes = [['shorts', `${t.shorts} ${shorts.length}`], ...(longos.length ? [['longos', `${t.longos} ${longos.length}`]] : []), ['clips', `${t.clips} ${p.clips.length}`]]

  const abas = el('div', { class: 'abas', role: 'tablist' }, opcoes.map(([a, rotulo]) =>
    el('button', { role: 'tab', 'aria-selected': String(aba === a), onclick: () => trocarAba(a) }, rotulo)))

  let corpo
  if (aba === 'clips') corpo = listaClips(d.base, p)
  else {
    const lista = aba === 'longos' ? longos : shorts
    corpo = lista.length
      ? lista.map((c) => cartaoCorte(d.base, p, c))
      : [el('p', { class: 'vazio' }, p.candidatos.length ? (aba === 'longos' ? t.semLongos : t.semShorts) : t.semCortes)]
  }
  return [
    el('div', { class: 'cabecalho' },
      el('h1', {}, p.titulo),
      el('div', { class: 'linha' }, seloFase(p.fase),
        el('span', { class: 'meta' }, `${t.nCortes(p.candidatos.length)} · ${t.nClips(p.clips.length)}`))),
    abas,
    el('div', { class: 'lista' }, corpo)
  ]
}

function alternarMarcado(id) {
  if (estado.marcados.has(id)) estado.marcados.delete(id)
  else estado.marcados.add(id)
  desenhar(true)
}

function cartaoCorte(base, p, c) {
  const marcado = estado.marcados.has(c.id)
  const aberto = estado.previa === c.id
  const longo = c.modo === 'longo'
  let midia
  if (aberto) {
    const v = el('video', {
      class: 'previa',
      src: `${base}/video-original#t=${c.inicio.toFixed(2)},${c.fim.toFixed(2)}`,
      controls: true,
      autoplay: true,
      playsinline: true,
      preload: 'auto'
    })
    midia = el('div', { class: 'midia' }, v,
      el('button', { class: 'fechar', 'aria-label': t.fecharPrevia, onclick: () => { estado.previa = null; desenhar(true) } }, '×'))
  } else {
    midia = el('button', {
      class: 'midia',
      'aria-label': `${t.previa}: ${c.titulo || c.id}`,
      disabled: !p.tem_video,
      onclick: () => { estado.previa = c.id; desenhar(true) }
    },
    el('img', { loading: 'lazy', alt: '', src: `${base}/candidatos/${enc(c.id)}/quadro`, onerror: (ev) => ev.target.remove() }),
    p.tem_video ? el('span', { class: 'play' }, `▶ ${t.previa}`) : null,
    el('span', { class: 'tempo' }, duracao(c.duracao || c.fim - c.inicio)))
  }
  return el('article', { class: `cartao corte ${marcado ? 'marcado' : ''} ${longo ? 'longo' : ''}` },
    midia,
    el('div', { class: 'corpo' },
      el('div', { class: 'linha' },
        el('span', { class: `nota ${corNota(c.nota || 0)}` }, Math.round(c.nota || 0)),
        el('span', { class: 'meta cresce' }, `${mmss(c.inicio)} – ${mmss(c.fim)}`),
        c.clip
          ? el('span', { class: 'selo ok' }, `✓ ${t.jaVirouClip}`)
          : el('button', {
            class: `marcar ${marcado ? 'on' : ''}`,
            'aria-pressed': String(marcado),
            onclick: () => alternarMarcado(c.id)
          }, marcado ? `✓ ${t.selecionado}` : t.selecionar)),
      c.titulo ? el('div', { class: 'titulo' }, c.titulo) : null,
      el('div', { class: 'texto' }, c.motivo || c.texto)))
}

function listaClips(base, p) {
  if (!p.clips.length) return [el('p', { class: 'vazio' }, t.semClips)]
  return p.clips.map((c) => {
    const pronto = c.saida || c.preview
    const src = `${base}/clips/${enc(c.id)}/video`
    const vertical = /^9:16|4:5/.test(c.formato || '')
    return el('article', { class: 'cartao clip' },
      pronto
        ? el('video', { class: vertical ? 'vertical' : '', src, controls: true, playsinline: true, preload: 'metadata', poster: c.capa ? `${base}/clips/${enc(c.id)}/capa` : null })
        : el('div', { class: 'sem-video' }, t.semVideo),
      el('div', { class: 'corpo' },
        el('div', { class: 'linha' },
          el('div', { class: 'cresce titulo' }, c.titulo || c.id),
          el('span', { class: `selo ${c.status === 'renderizado' ? 'ok' : c.status === 'erro' ? 'erro' : 'andando'}` }, t.statusClip[c.status] || c.status)),
        el('div', { class: 'meta' }, `${c.formato} · ${duracao(c.duracao)} · ${c.estilo}`),
        pronto ? el('a', { class: 'botao largo', href: `${src}?baixar=true`, download: `${c.id}.mp4` }, `⬇ ${t.baixar}`) : null))
  })
}

function rodapeAprovar(d) {
  const n = estado.marcados.size
  if (!n) return null
  const lista = d.estilos
  const padrao = lista.find((e) => e.padrao)
  const sel = lista.length > 1 ? el('select', {
    class: 'campo-solto',
    'aria-label': t.estilo,
    onchange: (ev) => {
      estado.estiloEscolhido = ev.target.value
      ev.target.blur()
    }
  },
  el('option', { value: '' }, `${t.estilo}: ${padrao ? padrao.nome : ''} (${t.estiloPadrao})`),
  lista.filter((e) => !e.padrao).map((e) => el('option', { value: e.id, selected: e.id === estado.estiloEscolhido }, e.nome))) : null
  const botao = el('button', {
    class: 'botao primario cresce',
    onclick: async () => {
      botao.disabled = true
      try {
        const r = await api('POST', `${d.base}/aprovar`, { ids: [...estado.marcados], estilo: estado.estiloEscolhido || null })
        estado.marcados = new Set()
        estado.aba = 'clips'
        avisar(t.aprovado(r.clips.length))
      } catch (e) {
        avisar(e.message)
      }
      await atualizar()
      desenhar(true)
    }
  }, t.aprovar(n))
  return el('div', { class: 'barra-aprovar' },
    el('div', { class: 'linha' },
      el('strong', { class: 'cresce' }, t.nSelecionados(n)),
      el('button', { class: 'link', onclick: () => { estado.marcados = new Set(); desenhar(true) } }, t.limpar)),
    sel,
    el('div', { class: 'linha' }, botao))
}

// ---- partida ------------------------------------------------------------------------------------
$('voltar').addEventListener('click', () => {
  location.hash = '#/'
})
window.addEventListener('hashchange', () => {
  if (lerCodigoDoQr()) return
  window.scrollTo({ top: 0 })
  atualizar()
})
document.addEventListener('visibilitychange', () => {
  if (!document.hidden) atualizar()
})
// quando a pessoa larga a lista ou o vídeo, aplica o que chegou enquanto ela usava
document.addEventListener('focusout', () => setTimeout(() => desenhar(), 0))
document.addEventListener('pause', () => setTimeout(() => desenhar(), 0), true)

// o QR code traz o código no fragmento (#parear=...), que nunca vai para o servidor nem para o histórico.
// Vale também quando a página já estava aberta e o celular lê o QR de novo (só muda o fragmento).
function lerCodigoDoQr() {
  const m = location.hash.match(/^#parear=([\w-]+)/)
  if (!m) return false
  history.replaceState(null, '', location.pathname)
  parear(m[1], localStorage.getItem('clipator.nome') || nomeAparelho())
  return true
}
if (!lerCodigoDoQr()) atualizar()

if ('serviceWorker' in navigator && window.isSecureContext) navigator.serviceWorker.register('sw.js').catch(() => {})
