#!/usr/bin/env node
/** Print the canonical self-contained article, including accessible navigation. */
import { createRequire } from 'node:module'
import { pathToFileURL } from 'node:url'
import { resolve } from 'node:path'
import { rename, rm, readFile, writeFile } from 'node:fs/promises'
import { createHash } from 'node:crypto'

const require = createRequire('/home/mahmud/recommendations-worker/package.json')
const { chromium } = require('playwright')
const hash = bytes => createHash('sha256').update(bytes).digest('hex')

// Portrait HTML: 24px body, 20px substantive, 17px supporting, 1.65 leading.
// Print: 18pt (24px) body, about 16pt substantive, 13pt supporting, 1.7 leading.
const READABILITY_FLOORS = {
  screen: { body: 24, substantive: 20, supporting: 17, leading: 1.65 },
  print: { body: 24, substantive: 21, supporting: 17, leading: 1.7 },
}
const TOLERANCE_PX = 0.25

function readabilityFailures(measured, floor) {
  const failures = []
  if (measured.body_font_px + TOLERANCE_PX < floor.body) failures.push(`body text ${measured.body_font_px}px is below ${floor.body}px`)
  if (measured.body_line_height_ratio + 0.01 < floor.leading) failures.push(`body leading ${measured.body_line_height_ratio} is below ${floor.leading}`)
  if (measured.substantive_min_px != null && measured.substantive_min_px + TOLERANCE_PX < floor.substantive)
    failures.push(`substantive text ${measured.substantive_min_px}px is below ${floor.substantive}px`)
  if (measured.supporting_min_px != null && measured.supporting_min_px + TOLERANCE_PX < floor.supporting)
    failures.push(`supporting text ${measured.supporting_min_px}px is below ${floor.supporting}px`)
  return failures
}

/** Runs in the page: classify visible text-bearing elements of the canonical article. */
function measureReadability() {
  const article = document.querySelector('article[data-canonical-content="true"]')
  const supporting = 'figcaption, caption, small, sub, sup, cite, footer, aside, pre, code, kbd, samp, [data-supporting]'
  const round = value => Math.round(value * 100) / 100
  const leading = style => {
    const size = parseFloat(style.fontSize)
    const height = parseFloat(style.lineHeight)
    return Number.isFinite(height) && size ? height / size : 1.2
  }
  const visible = element => {
    const rect = element.getBoundingClientRect()
    const style = getComputedStyle(element)
    return rect.width > 2 && rect.height > 2 && style.visibility !== 'hidden' && style.display !== 'none'
  }
  const textual = [...article.querySelectorAll('*')].filter(
    element => [...element.childNodes].some(node => node.nodeType === 3 && node.textContent.trim()) && visible(element),
  )
  const paragraphs = textual.filter(element => element.matches('p') && !element.closest(supporting))
  const bodySample = paragraphs.length ? paragraphs : [article]
  const sizes = bodySample.map(element => parseFloat(getComputedStyle(element).fontSize)).sort((a, b) => a - b)
  const body = sizes[Math.floor(sizes.length / 2)]
  const leadings = bodySample.map(element => leading(getComputedStyle(element)))
  const minimum = elements => (elements.length ? Math.min(...elements.map(element => parseFloat(getComputedStyle(element).fontSize))) : null)
  // Supporting text: captions, attributions, table headers and short labels such
  // as step numbers or kickers. Running prose, list items, cells, quotes and
  // headings are substantive whatever their length.
  const prose = 'p, li, td, dd, dt, blockquote, h1, h2, h3, h4, h5, h6'
  const ownText = element =>
    [...element.childNodes].filter(node => node.nodeType === 3).map(node => node.textContent).join('').trim()
  const isSupporting = element =>
    Boolean(element.closest(supporting)) ||
    element.matches('th, [class*="attribution"], [class*="caption"]') ||
    (!element.matches(prose) && ownText(element).length <= 40)
  const supportingElements = textual.filter(isSupporting)
  const substantiveElements = textual.filter(element => !isSupporting(element))
  const substantive = minimum(substantiveElements)
  const supportingMin = minimum(supportingElements)
  return {
    body_font_px: round(body),
    body_line_height_ratio: round(Math.min(...leadings)),
    substantive_min_px: substantive == null ? null : round(substantive),
    supporting_min_px: supportingMin == null ? null : round(supportingMin),
    text_elements: textual.length,
  }
}
// Leave the outer runner time to observe failure and reap the browser.
export function timeoutSeconds() {
  const value = Number(process.env.LITE_VISUAL_CHILD_TIMEOUT_SECONDS ?? process.env.LITE_VISUAL_STEP_TIMEOUT_SECONDS ?? 150)
  if (!Number.isFinite(value) || value <= 0 || value > 86400) throw new Error('LITE_VISUAL_STEP_TIMEOUT_SECONDS must be positive and at most 86400')
  return value
}

export function launchBrowser() {
  return chromium.launch({ headless: true, timeout: Math.min(30_000, timeoutSeconds() * 1000) })
}

/** Render one HTML file to a tagged A4 PDF in its own isolated context of a (possibly shared) browser. */
export async function renderPair(browser, html, pdf, receiptPath) {
  const input = pathToFileURL(resolve(html)).href
  const output = resolve(pdf)
  const temporary = `${output}.${process.pid}.${Math.random().toString(36).slice(2)}.tmp`
  const htmlHash = hash(await readFile(resolve(html)))
  const limit = timeoutSeconds()
  const started = performance.now()
  const context = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 820, height: 1180 } })
  let expired = false
  const watchdog = setTimeout(() => {
    expired = true
    process.stderr.write(`canonical PDF render timed out after ${limit}s: ${html}\n`)
    void context.close().catch(() => {})
  }, limit * 1000)
  try {
  const page = await context.newPage()
  const blocked = new Set()
  await page.route('**/*', async route => {
    const url = route.request().url()
    if (url === input || url.startsWith('data:')) await route.continue()
    else {
      blocked.add(url)
      await route.abort()
    }
  })
  await page.goto(input, { waitUntil: 'load', timeout: 30_000 })
  await page.evaluate(() => document.fonts.ready)
  if (!await page.locator('article[data-canonical-content="true"]').count()) {
    throw new Error('canonical article is missing')
  }
  // Mahmood reads every companion in portrait on the Huawei TGR-W09. This is a
  // targeted readability floor, not a design or accessibility audit.
  const screen = { media: 'screen', ...await page.evaluate(measureReadability) }
  const screenFailures = readabilityFailures(screen, READABILITY_FLOORS.screen)
  if (screenFailures.length) throw new Error(`tablet HTML readability check failed: ${screenFailures.join('; ')}`)
  await page.emulateMedia({ media: 'print' })
  const print = { media: 'print', ...await page.evaluate(measureReadability) }
  const printFailures = readabilityFailures(print, READABILITY_FLOORS.print)
  if (printFailures.length) throw new Error(`tablet PDF readability check failed: ${printFailures.join('; ')}`)
  const readability = { status: 'passed', ...print, screen }
  await page.pdf({
    path: temporary, format: 'A4', preferCSSPageSize: true,
    printBackground: true, displayHeaderFooter: false, tagged: true, outline: true,
  })
  if (blocked.size) throw new Error('Companion is not self-contained: external resource requests were blocked')
  if (expired) throw new Error('canonical PDF render exceeded its time limit')
  if (htmlHash !== hash(await readFile(resolve(html)))) throw new Error('HTML changed during rendering')
  const pdfHash = hash(await readFile(temporary))
  await rename(temporary, output)
  const receipt = { ok: true, schema_version: 'lite-visual-render/v1', html_sha256: htmlHash, pdf_sha256: pdfHash, pdf: output, tagged: true, outline_requested: true, quality_checks: 'not_run', readability, elapsed_ms: Math.round(performance.now() - started) }
  if (receiptPath) {
    await writeFile(`${receiptPath}.tmp`, JSON.stringify(receipt) + '\n')
    await rename(`${receiptPath}.tmp`, receiptPath)
  }
  return receipt
  } finally {
    clearTimeout(watchdog)
    await context.close().catch(() => {})
    await rm(temporary, { force: true })
  }
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  const [html, pdf, receiptPath] = process.argv.slice(2)
  if (!html || !pdf) {
    process.stderr.write('usage: render_pdf.mjs INPUT_HTML OUTPUT_PDF [RECEIPT_JSON]\n')
    process.exit(2)
  }
  const browser = await launchBrowser()
  try {
    process.stdout.write(JSON.stringify(await renderPair(browser, html, pdf, receiptPath)) + '\n')
  } finally {
    await browser.close()
  }
}

