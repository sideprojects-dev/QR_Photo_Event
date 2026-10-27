import assert from 'node:assert/strict'
import test from 'node:test'

import { state } from '../static/js/state.js?v=5'
import {
    handleGalleryFileChange,
    openGalleryPicker,
    validateGalleryFile
} from '../static/js/gallery_upload.js'
import { retakeCapture, sendFile } from '../static/js/upload.js'
import { clearPreviewObjectUrl } from '../static/js/preview_urls.js?v=1'
import { startCamera } from '../static/js/camera.js?v=8'

function selectedFile(name, type, size = 1024) {
    return new File([new Uint8Array(size)], name, { type })
}

function mockPage() {
    const classes = new Set()
    const elements = Object.fromEntries(
        [
            'galleryFileInput', 'btnUploadFromGallery',
            'btnSend', 'btnRetake', 'message',
            'viewfinder', 'preview', 'previewVideo',
            'uploadProgress', 'uploadProgressBar',
            'uploadProgressPercent', 'uploadProgressLabel'
        ].map(id => [id, {
            value: 'previous selection',
            files: [],
            style: {},
            hidden: false,
            disabled: false,
            textContent: '',
            src: '',
            click() { this.clicks = (this.clicks || 0) + 1 },
            pause() {},
            load() {},
            removeAttribute(name) { delete this[name] }
        }])
    )

    const originalDocument = globalThis.document
    const originalUrl = globalThis.URL
    const revoked = []
    let nextUrl = 1

    globalThis.document = {
        hidden: true,
        body: {
            classList: {
                add: name => classes.add(name),
                remove: name => classes.delete(name),
                contains: name => classes.has(name)
            }
        },
        getElementById: id => elements[id]
    }
    globalThis.URL = {
        createObjectURL: () => `blob:test-${nextUrl++}`,
        revokeObjectURL: url => revoked.push(url)
    }

    return {
        elements,
        classes,
        revoked,
        restore() {
            clearPreviewObjectUrl()
            state.capturedFile = null
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

test('selected photo uses the existing preview and Refă permits reselecting it', async () => {
    const page = mockPage()
    const input = page.elements.galleryFileInput
    const file = selectedFile('photo.jpg', 'image/jpeg')
    const track = { stopped: false, stop() { this.stopped = true } }
    state.stream = { getTracks: () => [track] }

    try {
        input.files = [file]
        handleGalleryFileChange({ currentTarget: input })
        assert.equal(state.capturedFile, file)
        assert.equal(track.stopped, true)
        assert.equal(page.elements.preview.src, 'blob:test-1')
        assert.equal(page.elements.viewfinder.style.display, 'none')
        assert.equal(page.classes.has('capture-ready'), true)
        assert.equal(input.value, '')

        await retakeCapture()
        assert.equal(state.capturedFile, null)
        assert.deepEqual(page.revoked, ['blob:test-1'])
        assert.equal(page.classes.has('capture-ready'), false)

        openGalleryPicker()
        assert.equal(input.clicks, 1)
        input.files = [file]
        handleGalleryFileChange({ currentTarget: input })
        assert.equal(state.capturedFile, file)
        assert.equal(page.elements.preview.src, 'blob:test-2')
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
        assert.match(page.elements.message.textContent, /Upload respins/)
        assert.deepEqual(page.revoked, [])
    } finally {
        page.restore()
        globalThis.window = originalWindow
        globalThis.XMLHttpRequest = originalXhr
    }
})
