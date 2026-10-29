import assert from 'node:assert/strict'
import test from 'node:test'

test('browser measurements are opt-in and contain no URL or access code', async () => {
    const originalWindow = globalThis.window
    const originalInfo = console.info
    const messages = []
    try {
        console.info = (...args) => messages.push(args)
        globalThis.window = { location: { search: '?access=private-example' } }
        const off = await import('../static/js/perf_monitor.js?test=off')
        assert.equal(off.perfStart(), null)
        off.perfRecord('gallery_start', null)
        assert.equal(messages.length, 0)

        globalThis.window = { location: { search: '?access=private-example&perf=1' } }
        const on = await import('../static/js/perf_monitor.js?test=on')
        const started = on.perfStart()
        on.perfRecord('gallery_start', started)
        assert.equal(messages.length, 1)
        assert.equal(messages[0][0], 'qr_photo_perf')
        const event = JSON.parse(messages[0][1])
        assert.equal(event.operation, 'gallery_start')
        assert.equal(event.outcome, 'ok')
        assert.ok(event.elapsed_ms >= 0)
        assert.ok(event.at_ms >= 0)
        assert.ok(!JSON.stringify(event).includes('private-example'))
        assert.deepEqual(Object.keys(event), [
            'event', 'operation', 'outcome', 'at_ms', 'elapsed_ms'
        ])

        console.info = () => { throw new Error('console unavailable') }
        assert.doesNotThrow(() => on.perfRecord('gallery_start', started))
    } finally {
        globalThis.window = originalWindow
        console.info = originalInfo
    }
})

test('XHR timings separate upload transfer from server response', async () => {
    const originalWindow = globalThis.window
    const originalDocument = globalThis.document
    const originalXhr = globalThis.XMLHttpRequest
    const originalInfo = console.info
    const messages = []
    const classes = new Set()
    const elements = Object.fromEntries([
        'message', 'btnSend', 'btnRetake', 'btnUploadFromGallery',
        'uploadProgress', 'uploadProgressBar', 'uploadProgressPercent',
        'uploadProgressLabel'
    ].map(id => [id, { style: {}, hidden: false, disabled: false, textContent: '' }]))
    try {
        globalThis.window = {
            EVENT_SLUG: 'private-event', EVENT_ACCESS: 'private-access',
            location: { search: '?access=private-access&perf=1' }
        }
        globalThis.document = {
            body: { classList: {
                add: name => classes.add(name),
                remove: name => classes.delete(name),
                contains: name => classes.has(name)
            } },
            getElementById: id => elements[id]
        }
        console.info = (...args) => messages.push(args)
        globalThis.XMLHttpRequest = class {
            upload = {}
            open() {}
            send() {
                queueMicrotask(() => {
                    this.upload.onload()
                    this.status = 429
                    this.responseText = '{}'
                    this.onload()
                })
            }
        }
        const { state } = await import('../static/js/state.js?v=6')
        const { sendFile } = await import('../static/js/upload.js?test=metrics')
        state.selectedPhotos = []
        state.capturedFile = new File(['photo'], 'private-photo.jpg', { type: 'image/jpeg' })
        await sendFile()
        const measured = messages.map(([label, data]) => {
            assert.equal(label, 'qr_photo_perf')
            return JSON.parse(data)
        })
        assert.deepEqual(measured.map(item => item.operation), [
            'upload_transfer', 'upload_after_transfer', 'upload_total'
        ])
        assert.equal(measured[1].outcome, 'http_error')
        assert.ok(measured.every(item => item.elapsed_ms >= 0))
        assert.ok(!JSON.stringify(measured).includes('private-access'))
        assert.ok(!JSON.stringify(measured).includes('private-photo.jpg'))
        assert.equal(state.capturedFile.name, 'private-photo.jpg')
    } finally {
        const { state } = await import('../static/js/state.js?v=6')
        state.capturedFile = null
        globalThis.window = originalWindow
        globalThis.document = originalDocument
        globalThis.XMLHttpRequest = originalXhr
        console.info = originalInfo
    }
})
