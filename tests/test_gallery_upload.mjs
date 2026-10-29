import assert from 'node:assert/strict'
import test from 'node:test'

import { state } from '../static/js/state.js?v=6'
import {
    handleGalleryFileChange,
    openGalleryPicker,
    removeSelectedPhoto,
    bindSelectedPhotoPreviewEvents,
    validateGalleryFile
} from '../static/js/gallery_upload.js'
import { retakeCapture, sendFile } from '../static/js/upload.js'
import {
    clearPreviewObjectUrl,
    clearSelectionPreviewUrls
} from '../static/js/preview_urls.js?v=2'
import { startCamera } from '../static/js/camera.js?v=16'

function selectedFile(name, type, size = 1024) {
    return new File([new Uint8Array(size)], name, { type })
}

function mockElement() {
    const classes = new Set()
    return {
        children: [],
        files: [],
        value: 'previous selection',
        style: {},
        hidden: false,
        disabled: false,
        textContent: '',
        src: '',
        classList: {
            add: (...names) => names.forEach(name => classes.add(name)),
            remove: (...names) => names.forEach(name => classes.delete(name)),
            contains: name => classes.has(name)
        },
        append(...nodes) { this.children.push(...nodes) },
        appendChild(node) { this.children.push(node) },
        replaceChildren(...nodes) { this.children = [...nodes] },
        setAttribute(name, value) { this[name] = value },
        removeAttribute(name) { delete this[name] },
        addEventListener(name, handler) { this.listeners ||= {}; this.listeners[name] = handler },
        click() { this.clicks = (this.clicks || 0) + 1; this.listeners?.click?.() },
        pause() {},
        load() {},
        set innerHTML(value) { this.children = [] }
    }
}

function mockPage() {
    const classes = new Set()
    const elements = Object.fromEntries(
        [
            'galleryFileInput', 'btnUploadFromGallery',
            'btnSend', 'btnRetake', 'message',
            'viewfinder', 'preview', 'previewVideo',
            'photoSelection', 'photoSelectionGrid', 'photoSelectionCount',
            'selectedPhotoModal', 'selectedPhotoPreviewImage',
            'closeSelectedPhotoPreview',
            'uploadProgress', 'uploadProgressBar',
            'uploadProgressPercent', 'uploadProgressLabel',
            'galleryGrid', 'galleryEmpty', 'galleryMessage', 'btnLoadMore'
        ].map(id => [id, mockElement()])
    )

    const originalDocument = globalThis.document
    const originalUrl = globalThis.URL
    const documentListeners = {}
    const revoked = []
    let nextUrl = 1

    globalThis.document = {
        hidden: true,
        body: {
            classList: {
                add: (...names) => names.forEach(name => classes.add(name)),
                remove: (...names) => names.forEach(name => classes.delete(name)),
                contains: name => classes.has(name)
            }
        },
        getElementById: id => elements[id],
        createElement: () => mockElement(),
        addEventListener: (name, handler) => { documentListeners[name] = handler }
    }
    globalThis.URL = {
        createObjectURL: () => `blob:test-${nextUrl++}`,
        revokeObjectURL: url => revoked.push(url)
    }

    return {
        elements,
        classes,
        revoked,
        documentListeners,
        restore() {
            clearPreviewObjectUrl()
            clearSelectionPreviewUrls()
            state.capturedFile = null
            state.selectedPhotos = []
            state.stream = null
            state.isRecording = false
            globalThis.document = originalDocument
            globalThis.URL = originalUrl
        }
    }
}

test('gallery selection accepts supported types and enforces size limits', () => {
    for (const [name, type, kind] of [
        ['a.jpg', 'image/jpeg', 'image'],
        ['a.png', 'image/png', 'image'],
        ['a.webp', 'image/webp', 'image'],
        ['a.mp4', 'video/mp4', 'video'],
        ['a.webm', 'video/webm', 'video']
    ]) {
        assert.equal(validateGalleryFile(selectedFile(name, type)).kind, kind)
    }

    assert.equal(validateGalleryFile({
        name: 'large.jpg', type: 'image/jpeg', size: 25 * 1024 * 1024
    }).kind, 'image')
    assert.match(validateGalleryFile({
        name: 'large.jpg', type: 'image/jpeg', size: 25 * 1024 * 1024 + 1
    }).error, /25 MB/)
    assert.equal(validateGalleryFile({
        name: 'large.mp4', type: 'video/mp4', size: 250 * 1024 * 1024
    }).kind, 'video')
    assert.match(validateGalleryFile({
        name: 'large.mp4', type: 'video/mp4', size: 250 * 1024 * 1024 + 1
    }).error, /250 MB/)
    assert.match(validateGalleryFile(selectedFile('iphone.heic', 'image/heic')).error, /HEIC/)
    assert.match(validateGalleryFile(selectedFile('iphone.mov', 'video/quicktime')).error, /MOV/)
    assert.match(validateGalleryFile(selectedFile('wrong.gif', 'image/gif')).error, /Format neacceptat/)
    assert.match(validateGalleryFile(selectedFile('wrong.jpg', 'image/png')).error, /Format neacceptat/)
    assert.match(validateGalleryFile({ name: 'empty.jpg', type: 'image/jpeg', size: 0 }).error, /gol/)
})

test('cancel and invalid files leave the camera and selected media unchanged', () => {
    const page = mockPage()
    const input = page.elements.galleryFileInput
    const track = { stopped: false, stop() { this.stopped = true } }
    state.stream = { getTracks: () => [track] }

    try {
        openGalleryPicker()
        assert.equal(input.clicks, 1)
        assert.equal(input.value, '')

        input.value = 'old'
        handleGalleryFileChange({ currentTarget: input })
        assert.equal(input.value, '')
        assert.equal(state.capturedFile, null)
        assert.equal(track.stopped, false)

        input.files = [selectedFile('iphone.heic', 'image/heic')]
        handleGalleryFileChange({ currentTarget: input })
        assert.equal(state.capturedFile, null)
        assert.equal(track.stopped, false)
        assert.match(page.elements.message.textContent, /HEIC/)
    } finally {
        page.restore()
    }
})

test('selected photo has a removable preview and Refă permits reselecting it', async () => {
    const page = mockPage()
    const input = page.elements.galleryFileInput
    const file = selectedFile('photo.jpg', 'image/jpeg')
    const track = { stopped: false, stop() { this.stopped = true } }
    state.stream = { getTracks: () => [track] }

    try {
        input.files = [file]
        handleGalleryFileChange({ currentTarget: input })
        assert.equal(state.capturedFile, null)
        assert.equal(state.selectedPhotos[0].file, file)
        assert.equal(track.stopped, true)
        assert.equal(page.elements.photoSelectionGrid.children[0].children[0].children[0].src, 'blob:test-1')
        assert.equal(page.elements.viewfinder.style.display, 'none')
        assert.equal(page.classes.has('capture-ready'), true)
        assert.equal(page.classes.has('photo-selection-ready'), true)
        assert.equal(page.elements.btnRetake.textContent, 'Anulează selecția')
        assert.equal(input.value, '')

        await retakeCapture()
        assert.equal(state.capturedFile, null)
        assert.equal(state.selectedPhotos.length, 0)
        assert.deepEqual(page.revoked, ['blob:test-1'])
        assert.equal(page.classes.has('capture-ready'), false)
        assert.equal(page.elements.btnRetake.textContent, 'Refă')

        openGalleryPicker()
        assert.equal(input.clicks, 1)
        input.files = [file]
        handleGalleryFileChange({ currentTarget: input })
        assert.equal(state.selectedPhotos[0].file, file)
        assert.equal(page.elements.photoSelectionGrid.children[0].children[0].children[0].src, 'blob:test-2')
    } finally {
        page.restore()
    }
})

test('recording and upload prevent opening or replacing the selected file', () => {
    const page = mockPage()
    const input = page.elements.galleryFileInput

    try {
        state.isRecording = true
        openGalleryPicker()
        input.files = [selectedFile('photo.jpg', 'image/jpeg')]
        handleGalleryFileChange({ currentTarget: input })
        assert.equal(input.clicks, undefined)
        assert.equal(state.capturedFile, null)

        state.isRecording = false
        page.classes.add('uploading')
        openGalleryPicker()
        handleGalleryFileChange({ currentTarget: input })
        assert.equal(input.clicks, undefined)
        assert.equal(state.capturedFile, null)

        page.classes.delete('uploading')
        state.capturedFile = selectedFile('previous.png', 'image/png')
        openGalleryPicker()
        handleGalleryFileChange({ currentTarget: input })
        assert.equal(input.clicks, undefined)
        assert.equal(state.capturedFile.name, 'previous.png')
    } finally {
        page.restore()
    }
})

test('selected photo can be enlarged and closes before its URL is revoked', async () => {
    const page = mockPage()
    const input = page.elements.galleryFileInput
    try {
        input.files = [selectedFile('detail.jpg', 'image/jpeg')]
        handleGalleryFileChange({ currentTarget: input })
        bindSelectedPhotoPreviewEvents()
        page.elements.photoSelectionGrid.children[0].children[0].click()
        assert.equal(page.elements.selectedPhotoModal.classList.contains('is-open'), true)
        assert.equal(page.elements.selectedPhotoPreviewImage.src, 'blob:test-1')

        page.documentListeners.keydown({ key: 'Escape' })
        assert.equal(page.elements.selectedPhotoModal.classList.contains('is-open'), false)
        page.elements.photoSelectionGrid.children[0].children[0].click()
        await removeSelectedPhoto(state.selectedPhotos[0].id)
        assert.equal(page.elements.selectedPhotoModal.classList.contains('is-open'), false)
        assert.equal(page.elements.selectedPhotoPreviewImage.src, undefined)
        assert.deepEqual(page.revoked, ['blob:test-1'])
    } finally {
        page.restore()
    }
})

test('selection enforces ten photos, validates each file, and allows removal', async () => {
    const page = mockPage()
    const input = page.elements.galleryFileInput

    try {
        input.files = Array.from({ length: 11 }, (_, index) =>
            selectedFile(`photo-${index}.jpg`, 'image/jpeg')
        )
        handleGalleryFileChange({ currentTarget: input })
        assert.equal(state.selectedPhotos.length, 0)
        assert.match(page.elements.message.textContent, /maximum 10/)

        input.files = [
            selectedFile('good.jpg', 'image/jpeg'),
            selectedFile('bad.heic', 'image/heic')
        ]
        handleGalleryFileChange({ currentTarget: input })
        assert.equal(state.selectedPhotos.length, 1)
        assert.match(page.elements.message.textContent, /HEIC/)
        const selectedId = state.selectedPhotos[0].id
        await removeSelectedPhoto(selectedId)
        assert.equal(state.selectedPhotos.length, 0)
        assert.deepEqual(page.revoked, ['blob:test-1'])
        assert.equal(page.classes.has('capture-ready'), false)

        input.files = [
            selectedFile('good.jpg', 'image/jpeg'),
            selectedFile('movie.mp4', 'video/mp4')
        ]
        handleGalleryFileChange({ currentTarget: input })
        assert.equal(state.selectedPhotos.length, 0)
        assert.match(page.elements.message.textContent, /singur videoclip/)
    } finally {
        page.restore()
    }
})

test('exactly ten photos can be selected without starting an upload', async () => {
    const page = mockPage()
    const input = page.elements.galleryFileInput
    try {
        input.files = Array.from({ length: 10 }, (_, index) =>
            selectedFile(`photo-${index}.jpg`, 'image/jpeg')
        )
        handleGalleryFileChange({ currentTarget: input })
        assert.equal(state.selectedPhotos.length, 10)
        assert.equal(page.elements.photoSelectionGrid.children.length, 10)
        await retakeCapture()
        assert.equal(page.revoked.length, 10)
    } finally {
        page.restore()
    }
})

test('batch upload continues after errors and retries only failed photos', async () => {
    const page = mockPage()
    const originalWindow = globalThis.window
    const originalXhr = globalThis.XMLHttpRequest
    const originalFetch = globalThis.fetch
    const files = ['one.jpg', 'two.png', 'three.webp'].map((name, index) =>
        selectedFile(name, ['image/jpeg', 'image/png', 'image/webp'][index])
    )
    const statuses = [201, 500, 201, 201]
    const requests = []
    const processingSnapshots = []

    globalThis.window = { EVENT_SLUG: 'event', EVENT_ACCESS: 'access-code' }
    globalThis.fetch = async () => ({
        ok: true,
        json: async () => ({ items: [], pagination: { has_more: false } })
    })
    globalThis.XMLHttpRequest = class {
        upload = {}
        open(method, url) {
            assert.equal(method, 'POST')
            this.url = url
        }
        send(formData) {
            requests.push({ url: this.url, name: formData.get('file').name })
            const status = statuses.shift()
            queueMicrotask(() => {
                this.upload.onprogress({ lengthComputable: true, loaded: 50, total: 100 })
                this.upload.onprogress({ lengthComputable: true, loaded: 100, total: 100 })
                processingSnapshots.push(
                    state.selectedPhotos.find(photo => photo.name === formData.get('file').name).status
                )
                this.status = status
                this.responseText = status === 500 ? '{"detail":"failure"}' : '{}'
                this.onload()
            })
        }
    }

    try {
        page.elements.galleryFileInput.files = files
        handleGalleryFileChange({ currentTarget: page.elements.galleryFileInput })
        assert.equal(state.selectedPhotos.length, 3)
        assert.equal(page.elements.photoSelectionGrid.children.length, 3)
        assert.equal(requests.length, 0)

        const firstSend = sendFile()
        await sendFile()
        await firstSend

        assert.equal(requests.length, 3)
        assert.deepEqual(processingSnapshots, ['processing', 'processing', 'processing'])
        assert.deepEqual(requests.map(request => request.name), files.map(file => file.name))
        assert.ok(requests.every(request => request.url === '/upload/event?access=access-code'))
        assert.deepEqual(state.selectedPhotos.map(photo => photo.status), [
            'success', 'error', 'success'
        ])
        assert.equal(state.selectedPhotos[0].file, null)
        assert.equal(state.selectedPhotos[1].file, files[1])
        assert.equal(state.selectedPhotos[2].file, null)
        assert.deepEqual(page.revoked, ['blob:test-1', 'blob:test-3'])
        assert.equal(page.elements.btnSend.textContent, 'Reîncearcă eșuate')
        assert.match(state.selectedPhotos[1].elements.status.textContent, /Eroare/)

        await sendFile()
        assert.equal(requests.length, 4)
        assert.equal(requests[3].name, files[1].name)
        assert.ok(state.selectedPhotos.every(photo => photo.status === 'success'))
        assert.ok(state.selectedPhotos.every(photo => photo.file === null))
        assert.equal(page.elements.btnSend.disabled, true)
        assert.deepEqual(page.revoked, ['blob:test-1', 'blob:test-3', 'blob:test-2'])

        await retakeCapture()
        assert.equal(state.selectedPhotos.length, 0)
        assert.equal(page.elements.btnSend.disabled, false)
    } finally {
        page.restore()
        globalThis.window = originalWindow
        globalThis.XMLHttpRequest = originalXhr
        globalThis.fetch = originalFetch
    }
})

test('429 explains overload and keeps the photo for a manual retry', async () => {
    const page = mockPage()
    const originalWindow = globalThis.window
    const originalXhr = globalThis.XMLHttpRequest
    const originalFetch = globalThis.fetch
    const file = selectedFile('photo.jpg', 'image/jpeg')
    let requests = 0
    globalThis.window = { EVENT_SLUG: 'event', EVENT_ACCESS: 'access-code' }
    globalThis.fetch = async () => ({
        ok: true,
        json: async () => ({ items: [], pagination: { has_more: false } })
    })
    globalThis.XMLHttpRequest = class {
        upload = {}
        open() {}
        send() {
            requests++
            queueMicrotask(() => {
                this.status = requests === 1 ? 429 : 200
                this.responseText = '{}'
                this.onload()
            })
        }
    }
    try {
        page.elements.galleryFileInput.files = [file]
        handleGalleryFileChange({ currentTarget: page.elements.galleryFileInput })
        await sendFile()
        assert.equal(requests, 1)
        assert.equal(state.selectedPhotos[0].file, file)
        assert.equal(state.selectedPhotos[0].status, 'error')
        assert.match(state.selectedPhotos[0].error, /multe încărcări/)
        await sendFile()
        assert.equal(requests, 2)
        assert.equal(state.selectedPhotos[0].status, 'success')
    } finally {
        page.restore()
        globalThis.window = originalWindow
        globalThis.XMLHttpRequest = originalXhr
        globalThis.fetch = originalFetch
    }
})

test('camera request finishing after a file selection releases its stream', async () => {
    const page = mockPage()
    const originalNavigator = Object.getOwnPropertyDescriptor(globalThis, 'navigator')
    let provideStream
    const pendingStream = new Promise(resolve => { provideStream = resolve })
    const track = { stopped: false, stop() { this.stopped = true } }

    Object.defineProperty(globalThis, 'navigator', {
        configurable: true,
        value: { mediaDevices: { getUserMedia: () => pendingStream } }
    })
    globalThis.document.hidden = false

    try {
        const starting = startCamera()
        state.capturedFile = selectedFile('photo.jpg', 'image/jpeg')
        provideStream({ getTracks: () => [track] })
        await starting
        assert.equal(track.stopped, true)
        assert.equal(state.stream, null)
    } finally {
        page.restore()
        if (originalNavigator) {
            Object.defineProperty(globalThis, 'navigator', originalNavigator)
        } else {
            delete globalThis.navigator
        }
    }
})

test('video preview is shown and a failed upload retains the selected file', async () => {
    const page = mockPage()
    const originalWindow = globalThis.window
    const originalXhr = globalThis.XMLHttpRequest
    const input = page.elements.galleryFileInput
    const file = selectedFile('video.mp4', 'video/mp4')
    let requestUrl

    globalThis.window = { EVENT_SLUG: 'event', EVENT_ACCESS: 'access-code' }
    globalThis.XMLHttpRequest = class {
        upload = {}
        status = 500
        responseText = '{"detail":"Upload respins"}'
        open(method, url) { requestUrl = url; assert.equal(method, 'POST') }
        send() { this.onload() }
    }

    try {
        input.files = [file]
        handleGalleryFileChange({ currentTarget: input })
        assert.equal(page.elements.previewVideo.src, 'blob:test-1')
        assert.equal(page.elements.previewVideo.style.display, 'block')
        assert.equal(page.elements.viewfinder.style.display, 'none')

        await sendFile()
        assert.equal(requestUrl, '/upload/event?access=access-code')
        assert.equal(state.capturedFile, file)
        assert.equal(page.elements.btnSend.disabled, false)
        assert.equal(page.elements.btnRetake.disabled, false)
        assert.equal(page.classes.has('uploading'), false)
        assert.match(page.elements.message.textContent, /Încărcarea a eșuat/)
        assert.deepEqual(page.revoked, [])
    } finally {
        page.restore()
        globalThis.window = originalWindow
        globalThis.XMLHttpRequest = originalXhr
    }
})
