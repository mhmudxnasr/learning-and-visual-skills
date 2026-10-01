#!/usr/bin/env node
/** Render many canonical articles with one shared Chromium (default 2 at a time). */
import { readFile } from 'node:fs/promises'
import { launchBrowser, renderPair } from './render_pdf.mjs'

const [jobsPath, concurrencyArg] = process.argv.slice(2)
if (!jobsPath) {
  process.stderr.write('usage: render_batch.mjs JOBS_JSON [CONCURRENCY]\n  JOBS_JSON: [{"html": "/abs/a.html", "pdf": "/abs/a.pdf", "receipt": "/abs/a.render.json"}, ...]\n')
  process.exit(2)
}
const jobs = JSON.parse(await readFile(jobsPath, 'utf8'))
const concurrency = Math.max(1, Math.min(Number(concurrencyArg ?? 2) || 2, 4))
if (!Array.isArray(jobs) || !jobs.every(job => job?.html && job?.pdf)) throw new Error('every job needs html and pdf')

const browser = await launchBrowser()
const results = new Array(jobs.length)
let next = 0
async function worker() {
  while (next < jobs.length) {
    const index = next++
    const { html, pdf, receipt } = jobs[index]
    try {
      const done = await renderPair(browser, html, pdf, receipt)
      results[index] = { html, pdf, ok: true, pdf_sha256: done.pdf_sha256, elapsed_ms: done.elapsed_ms }
    } catch (error) {
      results[index] = { html, pdf, ok: false, error: String(error?.message ?? error) }
    }
  }
}
try {
  await Promise.all(Array.from({ length: Math.min(concurrency, jobs.length) }, worker))
} finally {
  await browser.close()
}
process.stdout.write(JSON.stringify({ ok: results.every(item => item.ok), results }) + '\n')
process.exit(results.every(item => item.ok) ? 0 : 1)
