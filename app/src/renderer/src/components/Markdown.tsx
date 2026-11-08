// Markdown simples para as mensagens da conversa com a IA: títulos, listas, citações, blocos de
// código, código inline, negrito, itálico e links. Monta elementos React (nunca HTML cru), então
// nada do que a IA escreve vira código na página.

import { Fragment } from 'react'

type Bloco =
  | { t: 'codigo'; lang: string; texto: string }
  | { t: 'titulo'; nivel: number; texto: string }
  | { t: 'lista'; ordenada: boolean; itens: string[] }
  | { t: 'citacao'; texto: string }
  | { t: 'regua' }
  | { t: 'paragrafo'; texto: string }

function blocos(md: string): Bloco[] {
  const out: Bloco[] = []
  const linhas = md.replace(/\r\n/g, '\n').split('\n')
  let i = 0
  while (i < linhas.length) {
    const l = linhas[i]
    const cerca = /^\s*(```|~~~)\s*([\w+-]*)/.exec(l)
    if (cerca) {
      const fim = cerca[1]
      const corpo: string[] = []
      i++
      while (i < linhas.length && !linhas[i].trimStart().startsWith(fim)) corpo.push(linhas[i++])
      i++
      out.push({ t: 'codigo', lang: cerca[2], texto: corpo.join('\n') })
      continue
    }
    const tit = /^(#{1,6})\s+(.*)$/.exec(l)
    if (tit) {
      out.push({ t: 'titulo', nivel: tit[1].length, texto: tit[2] })
      i++
      continue
    }
    if (/^\s*([-*_])\s*\1\s*\1[\s\-*_]*$/.test(l)) {
      out.push({ t: 'regua' })
      i++
      continue
    }
    if (/^\s*([-*+]|\d+[.)])\s+/.test(l)) {
      const ordenada = /^\s*\d/.test(l)
      const itens: string[] = []
      while (i < linhas.length && /^\s*([-*+]|\d+[.)])\s+/.test(linhas[i])) {
        let item = linhas[i].replace(/^\s*([-*+]|\d+[.)])\s+/, '')
        i++
        while (i < linhas.length && /^\s{2,}\S/.test(linhas[i]) && !/^\s*([-*+]|\d+[.)])\s+/.test(linhas[i])) item += ' ' + linhas[i++].trim()
        itens.push(item)
      }
      out.push({ t: 'lista', ordenada, itens })
      continue
    }
    if (/^\s*>/.test(l)) {
      const corpo: string[] = []
      while (i < linhas.length && /^\s*>/.test(linhas[i])) corpo.push(linhas[i++].replace(/^\s*>\s?/, ''))
      out.push({ t: 'citacao', texto: corpo.join('\n') })
      continue
    }
    if (!l.trim()) {
      i++
      continue
    }
    const par: string[] = []
    while (i < linhas.length && linhas[i].trim() && !/^\s*(```|~~~|#{1,6}\s|>|([-*+]|\d+[.)])\s+)/.test(linhas[i])) par.push(linhas[i++])
    out.push({ t: 'paragrafo', texto: par.join('\n') })
  }
  return out
}

// código inline, negrito, itálico e links, nessa ordem de prioridade
function inline(texto: string): React.ReactNode[] {
  const out: React.ReactNode[] = []
  const re = /(`[^`\n]+`)|(\*\*[^*\n]+\*\*|__[^_\n]+__)|(\*[^*\n]+\*|_[^_\n]+_)|(\[[^\]\n]+\]\([^)\s]+\))/g
  let fim = 0
  let m: RegExpExecArray | null
  let k = 0
  while ((m = re.exec(texto))) {
    if (m.index > fim) out.push(...quebras(texto.slice(fim, m.index), k++))
    const s = m[0]
    if (m[1]) out.push(<code key={k++}>{s.slice(1, -1)}</code>)
    else if (m[2]) out.push(<strong key={k++}>{inline(s.slice(2, -2))}</strong>)
    else if (m[3]) out.push(<em key={k++}>{inline(s.slice(1, -1))}</em>)
    else {
      const [, rotulo, url] = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(s) ?? []
      out.push(/^https:\/\//.test(url ?? '')
        ? <a key={k++} href={url} target="_blank" rel="noreferrer">{rotulo}</a>
        : <span key={k++} className="link-local" title={url}>{rotulo}</span>)
    }
    fim = m.index + s.length
  }
  if (fim < texto.length) out.push(...quebras(texto.slice(fim), k++))
  return out
}

function quebras(s: string, k: number): React.ReactNode[] {
  return s.split('\n').map((p, i) => <Fragment key={`${k}-${i}`}>{i > 0 && <br />}{p}</Fragment>)
}

export function Markdown(props: { texto: string }): React.JSX.Element {
  return (
    <div className="markdown">
      {blocos(props.texto).map((b, i) => {
        switch (b.t) {
          case 'codigo':
            return (
              <div key={i} className="bloco-codigo">
                <div className="barra">
                  <span>{b.lang || 'texto'}</span>
                  <button className="link" onClick={() => void navigator.clipboard?.writeText(b.texto)}>copiar</button>
                </div>
                <pre><code>{b.texto}</code></pre>
              </div>
            )
          case 'titulo': {
            const H = `h${Math.min(6, b.nivel + 2)}` as 'h3'
            return <H key={i}>{inline(b.texto)}</H>
          }
          case 'lista': {
            const L = b.ordenada ? 'ol' : 'ul'
            return <L key={i}>{b.itens.map((it, j) => <li key={j}>{inline(it)}</li>)}</L>
          }
          case 'citacao':
            return <blockquote key={i}>{inline(b.texto)}</blockquote>
          case 'regua':
            return <hr key={i} />
          case 'paragrafo':
            return <p key={i}>{inline(b.texto)}</p>
        }
      })}
    </div>
  )
}
