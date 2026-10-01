#!/usr/bin/env node
/** Extract one untrusted HTML document with Mozilla Readability.
 *
 * The DOM is script-disabled and no subresources are loaded. Output is JSON so
 * the Python source router can validate completeness and write the immutable
 * plain-text extraction itself.
 */
import { readFile } from 'node:fs/promises'
import { createRequire } from 'node:module'

const require = createRequire('/home/mahmud/recommendations-worker/package.json')
const { JSDOM, VirtualConsole } = require('jsdom')
const { Readability } = require('@mozilla/readability')

const [htmlPath, sourceUrl = 'https://source.invalid/'] = process.argv.slice(2)
if (!htmlPath) {
  process.stderr.write('usage: extract_article.mjs HTML_PATH [SOURCE_URL]\n')
  process.exit(2)
}

const normalize = (value = '') => String(value)
  .replace(/\u00a0/g, ' ')
  .replace(/[ \t]+\n/g, '\n')
  .replace(/\n[ \t]+/g, '\n')
  .replace(/\n{3,}/g, '\n\n')
  .replace(/[ \t]{2,}/g, ' ')
  .trim()

const collectArticleBodies = (value, found = []) => {
  if (Array.isArray(value)) for (const item of value) collectArticleBodies(item, found)
  else if (value && typeof value === 'object') {
    if (typeof value.articleBody === 'string') found.push(normalize(value.articleBody))
    for (const child of Object.values(value)) collectArticleBodies(child, found)
  }
  return found
}

try {
  const html = await readFile(htmlPath, 'utf8')
  const virtualConsole = new VirtualConsole()
  const dom = new JSDOM(html, { url: sourceUrl, runScripts: 'outside-only', virtualConsole })
  const document = dom.window.document
  const canonical = document.querySelector('link[rel="canonical"]')?.getAttribute('href') || null
  const jsonLdBodies = []
  for (const node of document.querySelectorAll('script[type="application/ld+json"]')) {
    try { collectArticleBodies(JSON.parse(node.textContent || ''), jsonLdBodies) } catch {}
  }
  for (const node of document.querySelectorAll('script,style,noscript,template,form,nav[aria-label*="cookie" i],dialog')) node.remove()
  const parsed = new Readability(document, { charThreshold: 180, keepClasses: false }).parse()
  if (!parsed?.textContent) throw new Error('Mozilla Readability found no article body')
  const readabilityText = normalize(parsed.textContent)
  const contentDocument = new JSDOM(parsed.content || '').window.document
  const blockCount = [...contentDocument.querySelectorAll('p,li,blockquote,pre,table')].filter((node) => normalize(node.textContent).length >= 20).length
  const jsonLdText = jsonLdBodies.sort((a, b) => b.length - a.length)[0] || ''
  const text = jsonLdText.length > readabilityText.length * 1.15 ? jsonLdText : readabilityText
  process.stdout.write(JSON.stringify({
    engine: 'mozilla-readability',
    title: normalize(parsed.title || document.title),
    byline: normalize(parsed.byline || ''),
    site_name: normalize(parsed.siteName || ''),
    excerpt: normalize(parsed.excerpt || ''),
    language: normalize(parsed.lang || document.documentElement.lang || ''),
    canonical_url: canonical,
    text,
    readability_characters: readabilityText.length,
    jsonld_characters: jsonLdText.length,
    block_count: blockCount,
  }))
} catch (error) {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`)
  process.exit(1)
}
