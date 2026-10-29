import assert from 'node:assert/strict'
import test from 'node:test'

let fixtureId = 0

function element() {
    return {
        children: [], style: {}, hidden: false, disabled: false,
        classList: { add() {}, remove() {} },
        appendChild(child) { this.children.push(child) },
        addEventListener() {},
        setAttribute() {},
        set innerHTML(_) { this.children = [] }
    }
}

async function galleryFixture(t, pages) {
    const original = {
        window: globalThis.window,
        document: globalThis.document,
        fetch: globalThis.fetch,
        requestAnimationFrame: globalThis.requestAnimationFrame,
        info: console.info
    }
    t.after(() => {
        globalThis.window = original.window
        globalThis.document = original.document
        globalThis.fetch = original.fetch
        globalThis.requestAnimationFrame = original.requestAnimationFrame
        console.info = original.info
    })

    const images = []
    const frames = []
    const logs = []
    const elements = Object.fromEntries([
        'galleryGrid', 'galleryEmpty', 'galleryMessage', 'btnLoadMore'
    ].map(id => [id, element()]))
    globalThis.window = {
        EVENT_SLUG: 'example', EVENT_ACCESS: 'private-code',
        location: { search: '?access=private-code&perf=1' }
    }
    globalThis.document = {
        getElementById: id => elements[id],
        createElement: name => {
            const created = element()
            if (name === 'img') images.push(created)
            return created
        }
    }
    globalThis.requestAnimationFrame = callback => frames.push(callback)
    globalThis.fetch = async () => ({
        ok: true,
        json: async () => ({
            items: pages.shift().map(id => ({ id, content_type: 'image/jpeg' })),
            pagination: { has_more: false }
        })
    })
    console.info = (label, value) => {
        if (label === 'qr_photo_perf') logs.push(JSON.parse(value))
    }

    const { loadGallery } = await import(`../static/js/gallery.js?v=9&fixture=${++fixtureId}`)
    const firstThumbnailEvents = () => logs.filter(event => event.operation === 'gallery_first_thumbnail')
    return { loadGallery, images, frames, logs, elements, firstThumbnailEvents }
}

test('first thumbnail is recorded once after its animation frame', async t => {
    const page = await galleryFixture(t, [['first', 'second']])
    await page.loadGallery(true)
    assert.equal(page.elements.galleryGrid.children.length, 2)
    page.images[0].onload()
    page.images[1].onload()
    assert.equal(page.frames.length, 1)
    assert.equal(page.firstThumbnailEvents().length, 0)
    page.frames.shift()()
    page.images[1].onload()
    assert.equal(page.firstThumbnailEvents().length, 1)
    assert.ok(page.firstThumbnailEvents()[0].elapsed_ms >= 0)
    assert.ok(!JSON.stringify(page.logs).includes('private-code'))
})

test('old thumbnail onload after reset cannot record the new gallery', async t => {
    const page = await galleryFixture(t, [['old'], ['new']])
    await page.loadGallery(true)
    const oldImage = page.images[0]
    await page.loadGallery(true)
    assert.equal(page.elements.galleryGrid.children.length, 1)
    oldImage.onload()
    assert.equal(page.frames.length, 0)
    assert.equal(page.firstThumbnailEvents().length, 0)
    page.images[1].onload()
    page.frames.shift()()
    assert.equal(page.firstThumbnailEvents().length, 1)
})

test('old animation frame after reset cannot mark or measure the new gallery', async t => {
    const page = await galleryFixture(t, [['old'], ['new']])
    await page.loadGallery(true)
    page.images[0].onload()
    assert.equal(page.frames.length, 1)
    await page.loadGallery(true)
    page.frames.shift()()
    assert.equal(page.firstThumbnailEvents().length, 0)
    page.images[1].onload()
    page.images[1].onload()
    assert.equal(page.frames.length, 1)
    page.frames.shift()()
    assert.equal(page.firstThumbnailEvents().length, 1)
})
