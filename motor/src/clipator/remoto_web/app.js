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
    semClips: 'Aprove cortes na aba Cortes para gerar os clips.',
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
    recentes: 'Terminados há pouco'
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
    semClips: 'Approve cuts in the Cuts tab to make clips.',
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
    recentes: 'Recently finished'
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
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

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
const estado = {
  canal: localStorage.getItem('clipator.canal') || '',
  aba: 'cortes',
  marcados: new Set(),
  estiloEscolhido: '',
  ultimo: null // último /estado
}
let timer = 0

function rota() {
  const m = location.hash.match(/^#\/p\/([^/]+)\/([^/]+)$/)
  return m ? { canal: decodeURIComponent(m[1]), projeto: decodeURIComponent(m[2]) } : null
}

async function atualizar() {
  clearTimeout(timer)
  try {
    const st = await api('GET', '/m/api/estado')
    estado.ultimo = st
    if (st.idioma && TEXTOS[st.idioma]) t = TEXTOS[st.idioma]
    $('pc').textContent = st.pc
    const r = rota()
    $('voltar').hidden = !r
    if (r) await telaProjeto(r.canal, r.projeto, st)
    else await telaInicio(st)
  } catch (e) {
    if (e instanceof SemPareamento) return telaParear()
    telaErro(e.message)
  }
  // mais rápido quando tem coisa rodando; parado quando a aba está escondida
  if (!document.hidden) timer = setTimeout(atualizar, estado.ultimo && estado.ultimo.ativos.length ? 3000 : 10000)
}

function trocar(...nos) {
  const raiz = $('raiz')
  // guarda os vídeos tocando: recriar a tela a cada atualização faria o vídeo parar
  const tocando = [...raiz.querySelectorAll('video')].filter((v) => !v.paused || v.currentTime > 0)
  const manter = new Map(tocando.map((v) => [v.dataset.chave, v]))
  raiz.replaceChildren(...nos.flat().filter(Boolean))
  for (const v of raiz.querySelectorAll('video')) {
    const velho = manter.get(v.dataset.chave)
    if (velho) v.replaceWith(velho)
  }
}

// ---- telas --------------------------------------------------------------------------------------
function telaErro(msg) {
  $('voltar').hidden = !rota()
  trocar(el('div', { class: 'vazio' }, el('p', { class: 'erro' }, msg), el('button', { class: 'botao', onclick: atualizar }, t.tentarDeNovo)))
}

function nomeAparelho() {
  const ua = navigator.userAgent
  if (/iPhone/.test(ua)) return 'iPhone'
  if (/iPad/.test(ua)) return 'iPad'
  const m = ua.match(/Android[^;]*;\s*([^;)]+?)(?:\s+Build|\))/)
  return m && m[1] && m[1] !== 'K' ? m[1].trim() : /Android/.test(ua) ? 'Android' : 'Celular'
}

function telaParear(erro) {
  $('voltar').hidden = true
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
  trocar(el('section', { class: 'pareamento' },
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

function cartaoJob(j) {
  const andando = j.status === 'rodando' || j.status === 'na_fila'
  const pct = Math.round((j.progresso || 0) * 100)
  return el('div', { class: 'cartao' },
    el('div', { class: 'linha' },
      el('div', { class: 'cresce titulo' }, t.tipos[j.tipo] || j.tipo),
      el('span', { class: `selo ${j.status === 'ok' ? 'ok' : j.status === 'erro' ? 'erro' : andando ? 'andando' : ''}` }, t.status[j.status] || j.status)),
    andando ? el('div', { class: 'barra' }, el('div', { style: `width:${pct}%` })) : null,
    el('div', { class: 'meta' }, j.erro || j.mensagem || ''),
    andando ? el('div', { class: 'linha', style: 'margin-top:8px' },
      j.canal && j.projeto ? el('a', { class: 'botao', href: `#/p/${enc(j.canal)}/${enc(j.projeto)}` }, t.abrirVideo) : null,
      el('span', { class: 'cresce' }),
      el('button', {
        class: 'botao perigo',
        onclick: async (ev) => {
          ev.currentTarget.disabled = true
          await api('POST', `/m/api/jobs/${enc(j.id)}/cancelar`).catch((e) => avisar(e.message))
          atualizar()
        }
      }, t.cancelar)) : null)
}

async function telaInicio(st) {
  const canais = await api('GET', '/m/api/canais')
  if (!canais.length) return trocar(blocoJobs(st), el('p', { class: 'vazio' }, t.semCanais), rodapeSair())
  if (!canais.some((c) => c.slug === estado.canal)) estado.canal = (canais.find((c) => c.projetos > 0) || canais[0]).slug
  const projetos = await api('GET', `/m/api/canais/${enc(estado.canal)}/projetos`)

  const sel = el('select', {
    class: 'campo-solto',
    'aria-label': t.canal,
    onchange: (ev) => {
      estado.canal = ev.target.value
      localStorage.setItem('clipator.canal', estado.canal)
      atualizar()
    }
  }, canais.map((c) => el('option', { value: c.slug, selected: c.slug === estado.canal }, c.nome)))

  const link = el('input', { type: 'url', inputmode: 'url', placeholder: 'https://youtube.com/watch?v=…', required: true, autocomplete: 'off' })
  const enviar = el('button', { class: 'botao primario', type: 'submit' }, t.analisar)
  const novo = el('form', {
    onsubmit: async (ev) => {
      ev.preventDefault()
      enviar.disabled = true
      try {
        const r = await api('POST', `/m/api/canais/${enc(estado.canal)}/projetos`, { link: link.value })
        avisar(t.enviado)
        location.hash = `#/p/${enc(estado.canal)}/${enc(r.id)}`
      } catch (e) {
        avisar(e.message)
        enviar.disabled = false
      }
    }
  }, el('label', { class: 'campo' }, t.linkVideo, link), enviar)

  const lista = projetos.length
    ? projetos.map((p) => el('a', { class: 'cartao', href: `#/p/${enc(estado.canal)}/${enc(p.id)}` },
      el('div', { class: 'linha' },
        el('div', { class: 'cresce titulo' }, p.titulo),
        el('span', { class: `selo ${p.fase === 'erro' ? 'erro' : p.fase === 'clips' ? 'ok' : p.fase === 'baixando' || p.fase === 'analisando' ? 'andando' : ''}` }, t.fases[p.fase] || p.fase)),
      el('div', { class: 'meta' }, `${t.nCortes(p.cortes)} · ${t.nClips(p.clips)}`)))
    : [el('p', { class: 'vazio' }, t.semVideos)]

  trocar(blocoJobs(st),
    el('h2', {}, t.canal), sel,
    el('h2', {}, t.novoVideo), novo,
    el('h2', {}, t.videos), ...lista,
    rodapeSair())
}

function blocoJobs(st) {
  return el('div', {},
    el('h2', {}, t.rodando),
    st.ativos.length ? st.ativos.map(cartaoJob) : el('p', { class: 'dica' }, t.nadaRodando))
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

let projetoAberto = ''
let estilosCache = { canal: '', lista: [] }

async function telaProjeto(canal, projeto, st) {
  const chave = `${canal}/${projeto}`
  if (chave !== projetoAberto) {
    projetoAberto = chave
    estado.marcados = new Set()
    estado.aba = 'cortes'
    estado.estiloEscolhido = ''
  }
  const base = `/m/api/canais/${enc(canal)}/projetos/${enc(projeto)}`
  const p = await api('GET', base)
  if (estilosCache.canal !== canal) estilosCache = { canal, lista: await api('GET', `/m/api/canais/${enc(canal)}/estilos`).catch(() => []) }
  if (p.clips.length && !p.candidatos.some((c) => !c.clip) && estado.aba === 'cortes' && !estado.marcados.size && estado.trocouAba !== chave) estado.aba = 'clips'
  const jobsDaqui = st.ativos.filter((j) => j.projeto === projeto)

  const abas = el('div', { class: 'abas', role: 'tablist' },
    ['cortes', 'clips'].map((a) => el('button', {
      role: 'tab',
      'aria-selected': String(estado.aba === a),
      onclick: () => {
        estado.aba = a
        estado.trocouAba = chave
        atualizar()
      }
    }, a === 'cortes' ? `${t.cortes} (${p.candidatos.length})` : `${t.clips} (${p.clips.length})`)))

  const corpo = estado.aba === 'cortes' ? listaCortes(base, p) : listaClips(base, p)
  trocar(
    el('h1', {}, p.titulo),
    el('div', { class: 'linha', style: 'margin-bottom:8px' }, el('span', { class: `selo ${p.fase === 'erro' ? 'erro' : p.fase === 'clips' ? 'ok' : ''}` }, t.fases[p.fase] || p.fase)),
    jobsDaqui.length ? jobsDaqui.map(cartaoJob) : null,
    abas, ...corpo,
    estado.aba === 'cortes' && estado.marcados.size ? rodapeAprovar(base, canal) : null)
}

function listaCortes(base, p) {
  if (!p.candidatos.length) return [el('p', { class: 'vazio' }, t.semCortes)]
  const cor = (n) => (n >= 65 ? 'var(--nota-alta)' : n >= 45 ? 'var(--nota-media)' : 'var(--nota-baixa)')
  return p.candidatos.map((c) => {
    const marcado = estado.marcados.has(c.id)
    const caixa = el('input', {
      type: 'checkbox',
      checked: marcado,
      disabled: !!c.clip,
      'aria-label': c.titulo || c.id,
      onchange: () => {
        if (estado.marcados.has(c.id)) estado.marcados.delete(c.id)
        else estado.marcados.add(c.id)
        atualizar()
      }
    })
    return el('label', { class: `cartao corte ${marcado ? 'marcado' : ''}` },
      el('img', { class: 'quadro', loading: 'lazy', alt: '', src: `${base}/candidatos/${enc(c.id)}/quadro`, onerror: (ev) => (ev.target.style.visibility = 'hidden') }),
      el('div', { style: 'min-width:0' },
        el('div', { class: 'linha' },
          el('span', { class: 'nota', style: `color:${cor(c.nota || 0)}` }, Math.round(c.nota || 0)),
          el('span', { class: 'meta cresce' }, `${mmss(c.inicio)} · ${Math.round(c.duracao || c.fim - c.inicio)} s${c.modo === 'longo' ? ' · 16:9' : ''}`),
          c.clip ? el('span', { class: 'selo ok' }, t.jaVirouClip) : caixa),
        c.titulo ? el('div', { class: 'titulo' }, c.titulo) : null,
        el('div', { class: 'texto' }, c.motivo || c.texto)))
  })
}

function listaClips(base, p) {
  if (!p.clips.length) return [el('p', { class: 'vazio' }, t.semClips)]
  return p.clips.map((c) => {
    const pronto = c.saida || c.preview
    const src = `${base}/clips/${enc(c.id)}/video`
    return el('div', { class: 'cartao clip' },
      el('div', { class: 'linha' },
        el('div', { class: 'cresce titulo' }, c.titulo || c.id),
        el('span', { class: `selo ${c.status === 'renderizado' ? 'ok' : c.status === 'erro' ? 'erro' : 'andando'}` }, t.statusClip[c.status] || c.status)),
      el('div', { class: 'meta' }, `${c.formato} · ${Math.round(c.duracao)} s · ${c.estilo}`),
      pronto ? el('video', { src, controls: true, playsinline: true, preload: 'metadata', 'data-chave': c.id }) : el('p', { class: 'dica', style: 'margin-top:8px' }, t.semVideo),
      pronto ? el('a', { class: 'botao largo', href: `${src}?baixar=true`, download: `${c.id}.mp4` }, `⬇ ${t.baixar}`) : null)
  })
}

function rodapeAprovar(base, canal) {
  const n = estado.marcados.size
  const lista = estilosCache.lista
  const padrao = lista.find((e) => e.padrao)
  const sel = el('select', {
    class: 'campo-solto',
    'aria-label': t.estilo,
    onchange: (ev) => (estado.estiloEscolhido = ev.target.value)
  },
  el('option', { value: '' }, `${t.estilo}: ${padrao ? padrao.nome : ''} (${t.estiloPadrao})`),
  lista.filter((e) => !e.padrao).map((e) => el('option', { value: e.id, selected: e.id === estado.estiloEscolhido }, e.nome)))
  const botao = el('button', {
    class: 'botao primario largo',
    onclick: async () => {
      botao.disabled = true
      try {
        const r = await api('POST', `${base}/aprovar`, { ids: [...estado.marcados], estilo: estado.estiloEscolhido || null })
        estado.marcados = new Set()
        estado.aba = 'clips'
        avisar(t.aprovado(r.clips.length))
      } catch (e) {
        avisar(e.message)
      }
      atualizar()
    }
  }, t.aprovar(n))
  return el('div', { class: 'rodape' }, lista.length > 1 ? sel : null, botao)
}

// ---- partida ------------------------------------------------------------------------------------
$('voltar').addEventListener('click', () => {
  location.hash = '#/'
})
window.addEventListener('hashchange', () => {
  if (!lerCodigoDoQr()) atualizar()
})
document.addEventListener('visibilitychange', () => {
  if (!document.hidden) atualizar()
})

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
