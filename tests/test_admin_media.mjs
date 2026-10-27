import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import vm from 'node:vm'

import { createAdminMediaManager } from '../static/js/admin_media.js'

test('existing Admin inline script remains syntactically valid', () => {
  const html = readFileSync(new URL('../static/admin.html', import.meta.url), 'utf8')
  const script = html.match(/<script>([\s\S]*?)<\/script>/)[1]
  assert.doesNotThrow(() => new vm.Script(script))
})

function setup(fetcher) {
  const elements = new Map()
  const document = {
    createElement(tag) {
      const classes = new Set()
      return {
        tagName: tag.toUpperCase(), children: [], style: {}, hidden: false,
        textContent: '', className: '', disabled: false, listeners: {},
        classList: {
          add(value) { classes.add(value) },
          remove(value) { classes.delete(value) },
          toggle(value, state) { if (state) classes.add(value); else classes.delete(value) },
          contains(value) { return classes.has(value) }
        },
        addEventListener(name, handler) { this.listeners[name] = handler },
        appendChild(child) { this.children.push(child) },
        replaceChildren(...children) { this.children = children },
        setAttribute(name, value) { this[name] = value },
        removeAttribute(name) { delete this[name] },
        pause() {}, load() {}, scrollIntoView() {}
      }
    },
    createTextNode(text) { return { textContent: text } },
    getElementById(id) {
      if (!elements.has(id)) elements.set(id, document.createElement('div'))
      return elements.get(id)
    },
    addEventListener() {},
    querySelectorAll() { return [] }
  }
  const window = { location: { origin: 'https://example.test' }, confirm: () => true }
  let statsRefreshed = 0
  const manager = createAdminMediaManager({
    document, window, fetcher,
    refreshStats: async () => { statsRefreshed += 1 }
  })
  return {
    manager, window, el: document.getElementById,
    get statsRefreshed() { return statsRefreshed }
  }
}

function response(items, next = null) {
  return {
    ok: true,
    json: async () => ({
      event: { id: 7, name: 'Petrecere', slug: 'party' }, items,
      pagination: { has_more: next !== null, next_offset: next }
    })
  }
}

const photo = {
  id: 'p1', file_name: 'photo.jpg', content_type: 'image/jpeg',
  created_at: '2025-01-01T00:00:00Z', size_bytes: 1024
}
const video = {
  id: 'v1', file_name: 'video.mp4', content_type: 'video/mp4',
  created_at: '2025-01-02T00:00:00Z', size_bytes: null
}

test('admin gallery keeps event-scoped pagination, filters and preview', async () => {
  const urls = []
  const app = setup(async url => {
    urls.push(url)
    return response(url.includes('offset=30') ? [video] : [photo],
      url.includes('offset=30') ? null : 30)
  })
  await app.manager.open('party', 'Petrecere', '/event/party?access=example', 'password')
  assert.equal(app.el('adminMediaGrid').children.length, 1)
  assert.match(urls[0], /kind=all.*sort=newest.*offset=0/)
  assert.match(app.el('adminMediaGrid').children[0].children[0].children[0].src,
    /\/media\/p1\/thumbnail\?access=example/)
  await app.manager.load(false)
  assert.match(urls[1], /offset=30/)
  assert.equal(app.el('adminMediaGrid').children.length, 2)
  app.el('adminMediaSort').value = 'oldest'
  app.el('adminMediaKind').value = 'video'
  await app.manager.load(true)
  assert.match(urls[2], /kind=video.*sort=oldest.*offset=0/)
  const preview = app.el('adminMediaGrid').children[0].children[0]
  preview.listeners.click()
  assert.equal(app.el('adminMediaModal').classList.contains('is-open'), true)
  app.el('adminMediaModalClose').listeners.click()
  assert.equal(app.el('adminMediaModal').classList.contains('is-open'), false)
})

test('multi-selection, cancellation, partial failures and stats refresh', async () => {
  const deletes = []
  let remaining = [photo, video]
  const app = setup(async (url, options) => {
    if (options?.method === 'DELETE') {
      deletes.push(url)
      if (url.endsWith('/p1')) {
        remaining = remaining.filter(item => item.id !== 'p1')
        return { ok: true, json: async () => ({ status: 'deleted' }) }
      }
      return { ok: false, json: async () => ({ detail: 'Drive indisponibil.' }) }
    }
    return response(remaining)
  })
  await app.manager.open('party', 'Petrecere', '/event/party?access=example', 'password')
  app.el('adminMediaSelectShown').listeners.click()
  assert.match(app.el('adminMediaSelectedCount').textContent, /^2 materiale/)
  app.window.confirm = () => false
  await app.el('adminMediaDeleteSelected').listeners.click()
  assert.equal(deletes.length, 0)
  app.window.confirm = text => {
    assert.match(text, /2 materiale/)
    assert.match(text, /Coșul Google Drive/)
    return true
  }
  await app.el('adminMediaDeleteSelected').listeners.click()
  assert.equal(deletes.length, 2)
  assert.equal(app.statsRefreshed, 1)
  assert.match(app.el('adminMediaResults').textContent, /photo.jpg: șters/)
  assert.match(app.el('adminMediaResults').textContent, /video.mp4: Drive indisponibil/)
  assert.equal(app.el('adminMediaGrid').children.length, 1)
  assert.match(app.el('adminMediaSelectedCount').textContent, /^1 materiale/)
  app.el('adminMediaClearSelection').listeners.click()
  assert.match(app.el('adminMediaSelectedCount').textContent, /^0 materiale/)
})
