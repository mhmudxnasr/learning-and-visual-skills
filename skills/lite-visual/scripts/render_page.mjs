#!/usr/bin/env node
/** Render a JavaScript-dependent article without images, media, or fonts. */
import { writeFile } from 'node:fs/promises'
import { execFile } from 'node:child_process'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { promisify } from 'node:util'

const require = createRequire('/home/mahmud/recommendations-worker/package.json')
const { chromium } = require('playwright')
const run = promisify(execFile)
const validator = fileURLToPath(new URL('./validate_public_url.py', import.meta.url))

const [url, output] = process.argv.slice(2)
if (!url || !output) {
  process.stderr.write('usage: render_page.mjs URL OUTPUT_HTML\n')
  process.exit(2)
}

const browser = await chromium.launch({ headless: true })
try {
  const context = await browser.newContext({ javaScriptEnabled: true })
  const page = await context.newPage()
  let blockedError = null
  const validate = async (value) => {
    const parsed = new URL(value)
    if (!['http:', 'https:'].includes(parsed.protocol)) return
    if (parsed.username || parsed.password) throw new Error('browser request URL contains credentials')
    await run('python3', [validator, value], { timeout: 5000 }).catch((error) => {
      throw new Error(String(error.stderr || error.message || 'browser request URL is not public').trim())
    })
  }
  await page.route('**/*', async (route) => {
    const kind = route.request().resourceType()
    if (['image', 'media', 'font'].includes(kind)) {
      await route.abort()
      return
    }
    try {
      await validate(route.request().url())
      await route.continue()
    } catch (error) {
      blockedError ||= error
      await route.abort('blockedbyclient')
    }
  })
  try {
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 15_000 })
  } catch (error) {
    throw blockedError || error
  }
  await page.waitForTimeout(750)
  if (blockedError) throw blockedError
  await writeFile(output, await page.content(), 'utf8')
} finally {
  await browser.close()
}
