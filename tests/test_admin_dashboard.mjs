import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import vm from 'node:vm'

const html = readFileSync(new URL('../static/admin.html', import.meta.url), 'utf8')
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1]

function createPanel() {
  const elements = new Map()
  const buttons = []
  function element(id) {
    if (!elements.has(id)) {
      elements.set(id, {
        value: '', textContent: '', innerHTML: '', style: {}, disabled: false,
        addEventListener() {},
        querySelectorAll: () => [],
      })
    }
    return elements.get(id)
  }
  const document = {
    getElementById: element,
    querySelectorAll: selector => selector === '.activate-event-btn' ? buttons : [],
  }
  const context = vm.createContext({
    document, window: { location: { origin: 'https://example.test' }, confirm: () => true },
    navigator: { clipboard: { writeText: async () => {} } }, URL, console,
  })
  vm.runInContext(script, context)
  return { context, element, buttons }
}

test('admin filters locations and events and displays actual media counts', () => {
  const { context, element } = createPanel()
  vm.runInContext(`locationsCache = [{ name: 'Sala A', slug: 'a' }, { name: 'Gradina', slug: 'b' }];
    selectedLocationName = 'Sala A';
    eventsCache = [
      { name: 'Nunta', slug: 'nunta', status: 'active', guest_url: '/event/nunta', photo_count: 5, video_count: 2 },
      { name: 'Botez', slug: 'botez', status: 'archived', guest_url: '/event/botez', photo_count: 1, video_count: 0 }
    ];`, context)

  element('locationSearch').value = 'sala'
  context.renderLocations()
  assert.match(element('locationsList').innerHTML, /Sala A/)
  assert.doesNotMatch(element('locationsList').innerHTML, /Gradina/)

  element('eventStatusFilter').value = 'active'
  context.renderEvents()
  assert.match(element('eventsList').innerHTML, /Fotografii: 5 · Videoclipuri: 2/)
  assert.doesNotMatch(element('eventsList').innerHTML, /Botez/)

  element('eventStatusFilter').value = 'all'
  element('eventSearch').value = 'botez'
  context.renderEvents()
  assert.match(element('eventsList').innerHTML, /Botez/)
  assert.doesNotMatch(element('eventsList').innerHTML, /Nunta/)
})

test('activation asks for confirmation and ignores repeated submissions', async () => {
  const { context, element, buttons } = createPanel()
  let requests = 0
  let finishRequest
  buttons.push({ disabled: false })
  context.window.confirm = () => false
  await context.activateEvent('party')
  assert.equal(requests, 0)

  context.window.confirm = () => true
  context.fetch = async () => {
    requests += 1
    if (requests === 1) await new Promise(resolve => { finishRequest = resolve })
    return { ok: true, json: async () => ({
      locations: 1, active_events: 1, archived_events: 0, photos: 0, videos: 0,
    }) }
  }
  const pending = context.activateEvent('party')
  await context.activateEvent('party')
  assert.equal(requests, 1)
  assert.equal(buttons[0].disabled, true)
  finishRequest()
  await pending
  assert.equal(requests, 2) // statistics refresh
  assert.equal(buttons[0].disabled, false)
  assert.match(element('eventActionMessage').textContent, /activat/)
})

test('copy link confirms success without logging the access code', async () => {
  const { context, element } = createPanel()
  let copied
  context.navigator.clipboard.writeText = async value => { copied = value }
  const button = { disabled: false }
  await context.copyLink('/event/party?access=example', 'eventActionMessage', button)
  assert.equal(copied, 'https://example.test/event/party?access=example')
  assert.equal(button.disabled, false)
  assert.equal(element('eventActionMessage').textContent, 'Linkul a fost copiat.')
})
