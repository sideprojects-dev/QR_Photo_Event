import assert from 'node:assert/strict'
import test from 'node:test'

import {
    bindGalleryModalEvents,
    closeGalleryModal,
    loadGallery,
    navigateGalleryPhoto,
    openGalleryModal
} from '../static/js/gallery.js?v=9'
import { state } from '../static/js/state.js?v=6'

function element() {
    const classes = new Set()
    return {
        children: [],
        style: {},
        hidden: false,
        disabled: false,
        textContent: '',
        listeners: {},
        classList: {
            add: name => classes.add(name),
            remove: name => classes.delete(name),
            contains: name => classes.has(name)
        },
        appendChild(child) { this.children.push(child) },
        set innerHTML(value) { this.children = [] },
        setAttribute(name, value) { this[name] = value },
        removeAttribute(name) { delete this[name] },
        addEventListener(name, handler) { this.listeners[name] = handler },
        pause() {},
        load() {}
    }
}

test('gallery modal navigates loaded photos by buttons, keyboard, and swipe', async () => {
    const originalDocument = globalThis.document
    const originalWindow = globalThis.window
    const originalFetch = globalThis.fetch
    const originalAnimationFrame = globalThis.requestAnimationFrame
    const originalInfo = console.info
    const performanceLogs = []
    const items = [
        { id: 'photo-1', content_type: 'image/jpeg' },
        { id: 'video-1', content_type: 'video/mp4' },
        { id: 'photo-2', content_type: 'image/png' }
    ]
    const ids = [
        'galleryGrid', 'galleryEmpty', 'galleryMessage', 'btnLoadMore',
        'galleryModal', 'galleryModalImage', 'galleryModalVideo',
        'galleryModalLoading', 'galleryDownload',
        'galleryPrevious', 'galleryNext'
    ]
    const elements = Object.fromEntries(ids.map(id => [id, element()]))
    const documentListeners = {}

    globalThis.document = {
        body: { classList: element().classList },
        getElementById: id => elements[id],
        createElement: () => element(),
        addEventListener: (name, handler) => { documentListeners[name] = handler }
    }
    globalThis.window = { EVENT_SLUG: 'event', EVENT_ACCESS: 'code' }
    globalThis.fetch = async () => ({
        ok: true,
        json: async () => ({ items, pagination: { has_more: false } })
    })
    console.info = label => {
        if (label === 'qr_photo_perf') performanceLogs.push(label)
    }
    globalThis.requestAnimationFrame = () => {
        throw new Error('Monitoring disabled must not schedule a measurement frame')
    }

    try {
        await loadGallery(true)
        assert.equal(elements.galleryGrid.children.length, 3)
        elements.galleryGrid.children[0].children[0].children[0].onload()
        assert.equal(performanceLogs.length, 0)
        bindGalleryModalEvents()

        openGalleryModal(items[0])
        assert.equal(elements.galleryModal.classList.contains('is-open'), true)
        assert.equal(elements.galleryPrevious.disabled, true)
        assert.equal(elements.galleryNext.disabled, false)
        assert.match(elements.galleryModalImage.src, /photo-1\/preview/)
        elements.galleryModalImage.onload()
        assert.equal(elements.galleryModalImage.style.display, 'block')

        elements.galleryNext.listeners.click()
        assert.match(elements.galleryModalImage.src, /photo-2\/preview/)
        assert.match(elements.galleryDownload.href, /photo-2\/download/)
        assert.match(elements.galleryDownload.href, /access=code/)
        assert.equal(elements.galleryNext.disabled, true)
        navigateGalleryPhoto(1)
        assert.match(elements.galleryModalImage.src, /photo-2\/preview/)

        documentListeners.keydown({ key: 'ArrowLeft' })
        assert.match(elements.galleryModalImage.src, /photo-1\/preview/)
        elements.galleryModal.listeners.touchstart({
            touches: [{ clientX: 200, clientY: 80 }]
        })
        elements.galleryModal.listeners.touchend({
            changedTouches: [{ clientX: 80, clientY: 85 }]
        })
        assert.match(elements.galleryModalImage.src, /photo-2\/preview/)

        openGalleryModal(items[1])
        assert.equal(elements.galleryPrevious.hidden, true)
        assert.equal(elements.galleryNext.hidden, true)
        assert.match(elements.galleryModalVideo.src, /video-1/)
        closeGalleryModal()
        assert.equal(elements.galleryModal.classList.contains('is-open'), false)
        assert.equal(elements.galleryModal['aria-hidden'], 'true')

        openGalleryModal(items[0])
        elements.galleryModal.listeners.click({ target: elements.galleryModal })
        assert.equal(elements.galleryModal.classList.contains('is-open'), false)
    } finally {
        state.galleryLoading = false
        globalThis.document = originalDocument
        globalThis.window = originalWindow
        globalThis.fetch = originalFetch
        globalThis.requestAnimationFrame = originalAnimationFrame
        console.info = originalInfo
    }
})
