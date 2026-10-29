import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import { state } from '../static/js/state.js?v=6'
import { coverVideoSize, flipCamera, selectCamera, startCamera, stopCamera } from '../static/js/camera.js?v=16'
import { retakeCapture } from '../static/js/upload.js'
import { takePhoto } from '../static/js/photo.js'

function classes() {
    const values = new Set()
    return {
        add: (...names) => names.forEach(name => values.add(name)),
        remove: (...names) => names.forEach(name => values.delete(name)),
        contains: name => values.has(name),
        toggle(name, force) { if (force) values.add(name); else values.delete(name) }
    }
}

function element() {
    const listeners = new Map()
    return {
        classList: classes(), style: {}, children: [], hidden: false,
        textContent: '', readyState: 0, videoWidth: 0, videoHeight: 0,
        addEventListener(name, callback) {
            if (!listeners.has(name)) listeners.set(name, new Set())
            listeners.get(name).add(callback)
        },
        removeEventListener(name, callback) { listeners.get(name)?.delete(callback) },
        emit(name) { for (const callback of [...(listeners.get(name) || [])]) callback() },
        appendChild(child) { this.children.push(child) },
        replaceChildren() { this.children = [] },
        set innerHTML(value) { this.children = [] },
        setAttribute(name, value) { this[name] = value },
        removeAttribute(name) { delete this[name] },
        pause() {}, load() {}, play: async () => {}
    }
}

function stream(deviceId, facingMode) {
    const track = {
        stopped: false,
        stop() { this.stopped = true },
        getSettings: () => ({ deviceId, facingMode })
    }
    return {
        track,
        getTracks: () => [track],
        getVideoTracks: () => [track]
    }
}

function setup(getUserMedia, useFrameCallback = false, ios = false) {
    const oldDocument = globalThis.document
    const oldWindow = globalThis.window
    const oldNavigator = Object.getOwnPropertyDescriptor(globalThis, 'navigator')
    const ids = [
        'viewfinder', 'cameraCanvas', 'cameraSelector', 'message', 'preview', 'previewVideo',
        'galleryFileInput', 'btnSend', 'btnRetake', 'photoSelectionGrid',
        'photoSelection', 'uploadProgress', 'uploadProgressBar',
        'uploadProgressPercent', 'uploadProgressLabel', 'selectedPhotoModal',
        'selectedPhotoPreviewImage', 'galleryModal'
    ]
    const elements = Object.fromEntries(ids.map(id => [id, element()]))
    elements.cameraCanvas.getBoundingClientRect = () => ({ width: 398, height: 531 })
    elements.cameraCanvas.draws = []
    elements.cameraCanvas.getContext = () => ({
        setTransform() {},
        drawImage: (...args) => elements.cameraCanvas.draws.push(args)
    })
    const viewfinder = elements.viewfinder
    let attachedStream = null
    Object.defineProperty(viewfinder, 'srcObject', {
        get: () => attachedStream,
        set(value) {
            attachedStream = value
            viewfinder.readyState = 0
            viewfinder.videoWidth = 0
            viewfinder.videoHeight = 0
        }
    })
    if (useFrameCallback) {
        viewfinder.requestVideoFrameCallback = callback => {
            viewfinder.frameCallback = callback
            return 1
        }
        viewfinder.cancelVideoFrameCallback = () => { viewfinder.frameCallback = null }
    }
    globalThis.document = {
        hidden: false,
        body: { classList: classes() },
        getElementById: id => elements[id],
        querySelector: selector => selector === '.media-frame'
            ? { getBoundingClientRect: () => ({ width: 398, height: 531 }) }
            : null,
        createElement: tag => {
            if (tag !== 'canvas') return element()
            return {
                getContext: () => ({ translate() {}, scale() {}, drawImage() {} }),
                toBlob: callback => callback(new Blob(['photo'], { type: 'image/jpeg' }))
            }
        }
    }
    globalThis.window = { devicePixelRatio: 1 }
    Object.defineProperty(globalThis, 'navigator', {
        configurable: true,
        value: { userAgent: ios ? 'iPhone Safari' : 'Desktop', mediaDevices: { getUserMedia, enumerateDevices: async () => [] } }
    })
    state.stream = null
    state.capturedFile = null
    state.selectedPhotos = []
    state.facingMode = 'environment'
    state.selectedCameraId = null
    state.availableCameras = []
    state.isRecording = false

    return {
        elements,
        ready(width = 640, height = 480) {
            viewfinder.readyState = 2
            viewfinder.videoWidth = width
            viewfinder.videoHeight = height
            viewfinder.emit('loadeddata')
        },
        restore() {
            stopCamera()
            state.capturedFile = null
            state.selectedPhotos = []
            globalThis.document = oldDocument
            globalThis.window = oldWindow
            if (oldNavigator) Object.defineProperty(globalThis, 'navigator', oldNavigator)
            else delete globalThis.navigator
        }
    }
}

async function tick() { await new Promise(resolve => setImmediate(resolve)) }

test('camera container has fixed geometry and video stays hidden until first frame', async () => {
    const css = readFileSync(new URL('../static/css/camera.css', import.meta.url), 'utf8')
    assert.match(css, /\.media-frame\s*\{[^}]*aspect-ratio:\s*3\s*\/\s*4/s)
    assert.match(css, /#viewfinder\s*\{[^}]*opacity:\s*0/s)
    assert.match(css, /#viewfinder\s*\{[^}]*object-fit:\s*cover/s)
    const source = stream('main', 'environment')
    const page = setup(async () => source, true)
    try {
        const starting = startCamera()
        await tick()
        assert.equal(page.elements.viewfinder.srcObject, source)
        assert.equal(document.body.classList.contains('camera-ready'), false)
        assert.equal(state.stream, null)
        page.ready(1080, 1920)
        assert.equal(document.body.classList.contains('camera-ready'), false)
        page.elements.viewfinder.frameCallback()
        await starting
        assert.equal(document.body.classList.contains('camera-ready'), true)
        assert.equal(state.stream, source)
        assert.equal(page.elements.viewfinder.style.width, '100%')
        assert.ok(parseFloat(page.elements.viewfinder.style.height) > 100)
        page.elements.viewfinder.videoWidth = 1920
        page.elements.viewfinder.videoHeight = 1080
        page.elements.viewfinder.emit('resize')
        assert.ok(parseFloat(page.elements.viewfinder.style.width) > 100)
        assert.equal(page.elements.viewfinder.style.height, '100%')
    } finally { page.restore() }
})

test('explicit video geometry covers portrait and landscape streams without distortion', () => {
    const portrait = coverVideoSize(398, 531, 1080, 1920)
    assert.equal(portrait.width, 100)
    assert.ok(portrait.height > 133 && portrait.height < 134)
    assert.ok(Math.abs((portrait.width * 398) / (portrait.height * 531) - 1080 / 1920) < 0.001)
    const landscape = coverVideoSize(398, 531, 1920, 1080)
    assert.equal(landscape.height, 100)
    assert.ok(landscape.width > 237 && landscape.width < 238)
    assert.ok(Math.abs((landscape.width * 398) / (landscape.height * 531) - 1920 / 1080) < 0.001)
})

test('iPhone camera presents a proportionally cropped canvas before it becomes visible', async () => {
    const source = stream('front', 'user')
    const page = setup(async () => source, true, true)
    try {
        const starting = startCamera()
        await tick()
        page.ready(1080, 1920)
        page.elements.viewfinder.frameCallback()
        await starting
        assert.equal(document.body.classList.contains('camera-ready'), false)
        assert.equal(document.body.classList.contains('camera-canvas-ready'), true)
        assert.equal(page.elements.cameraCanvas.draws.length, 1)
        assert.equal(page.elements.cameraCanvas.width, 398)
        assert.equal(page.elements.cameraCanvas.height, 531)
        stopCamera()
        assert.equal(document.body.classList.contains('camera-canvas-ready'), false)
        assert.equal(source.track.stopped, true)
    } finally { page.restore() }
})

test('recording camera restart receives audio and keeps cover geometry', async () => {
    const source = stream('main', 'environment')
    let requested
    const page = setup(async constraints => { requested = constraints; return source })
    try {
        const starting = startCamera({ withAudio: true })
        await tick(); page.ready(1080, 1920); await starting
        assert.equal(requested.audio, true)
        assert.ok(parseFloat(page.elements.viewfinder.style.height) > 100)
        assert.equal(state.stream, source)
    } finally { page.restore() }
})

test('switching front and rear cameras hides the old frame and preserves mirroring', async () => {
    const sources = [stream('main', 'environment'), stream('front', 'user'), stream('main', 'environment')]
    let index = 0
    const page = setup(async () => sources[index++])
    try {
        const first = startCamera()
        await tick(); page.ready(); await first
        const front = flipCamera()
        await tick()
        assert.equal(document.body.classList.contains('camera-ready'), false)
        assert.equal(sources[0].track.stopped, true)
        page.ready(); await front
        assert.equal(page.elements.viewfinder.classList.contains('unmirror'), true)
        const rear = flipCamera()
        await tick(); page.ready(); await rear
        assert.equal(page.elements.viewfinder.classList.contains('unmirror'), false)
        assert.equal(state.stream, sources[2])
    } finally { page.restore() }
})

test('camera selection and photography work after the new frame is ready', async () => {
    const sources = [stream('main', 'environment'), stream('wide', 'environment')]
    const calls = []
    const page = setup(async constraints => {
        calls.push(constraints)
        return sources[calls.length - 1]
    })
    const oldImageCapture = globalThis.ImageCapture
    try {
        const first = startCamera()
        await tick(); page.ready(); await first
        const switching = selectCamera('wide')
        await tick()
        assert.equal(document.body.classList.contains('camera-ready'), false)
        assert.deepEqual(calls[1].video.deviceId, { exact: 'wide' })
        page.ready(); await switching
        assert.equal(state.stream, sources[1])
        globalThis.window.ImageCapture = true
        globalThis.ImageCapture = class {
            async getPhotoCapabilities() { return {} }
            async takePhoto() { return new Blob(['photo'], { type: 'image/jpeg' }) }
        }
        await takePhoto()
        assert.equal(state.capturedFile.type, 'image/jpeg')
        assert.equal(state.stream, null)
    } finally {
        page.restore()
        if (oldImageCapture === undefined) delete globalThis.ImageCapture
        else globalThis.ImageCapture = oldImageCapture
    }
})

test('rapid switches discard stale streams and permission errors leave a retry path', async () => {
    let resolveFirst
    const stale = stream('wide', 'environment')
    const latest = stream('tele', 'environment')
    let call = 0
    const page = setup(() => {
        call += 1
        return call === 1
            ? new Promise(resolve => { resolveFirst = resolve })
            : Promise.resolve(latest)
    })
    try {
        const first = selectCamera('wide')
        const second = selectCamera('tele')
        resolveFirst(stale)
        await first
        assert.equal(stale.track.stopped, true)
        await tick()
        page.ready(); await second
        assert.equal(state.stream, latest)
        assert.equal(state.selectedCameraId, 'tele')
    } finally { page.restore() }

    let attempts = 0
    const recovered = stream('main', 'environment')
    const retryPage = setup(async () => {
        attempts += 1
        if (attempts === 1) throw new Error('Permission denied')
        return recovered
    })
    try {
        await startCamera()
        assert.equal(state.stream, null)
        assert.equal(document.body.classList.contains('camera-ready'), false)
        assert.match(retryPage.elements.message.textContent, /Permission denied/)
        const retry = startCamera()
        await tick(); retryPage.ready(); await retry
        assert.equal(state.stream, recovered)
    } finally { retryPage.restore() }
})

test('switching during frame wait cancels the old preview; playback failure releases hardware', async () => {
    const firstStream = stream('main', 'environment')
    const secondStream = stream('front', 'user')
    let calls = 0
    const page = setup(async () => (++calls === 1 ? firstStream : secondStream))
    try {
        const first = startCamera()
        await tick()
        assert.equal(state.stream, null)
        const second = flipCamera()
        await first
        assert.equal(firstStream.track.stopped, true)
        assert.equal(document.body.classList.contains('camera-ready'), false)
        await tick(); page.ready(); await second
        assert.equal(state.stream, secondStream)
    } finally { page.restore() }

    const failedStream = stream('main', 'environment')
    const failedPage = setup(async () => failedStream)
    failedPage.elements.viewfinder.play = async () => { throw new Error('Playback blocked') }
    try {
        await startCamera()
        assert.equal(failedStream.track.stopped, true)
        assert.equal(state.stream, null)
        assert.equal(document.body.classList.contains('camera-ready'), false)
        assert.match(failedPage.elements.message.textContent, /Playback blocked/)
    } finally { failedPage.restore() }
})

test('Refă restarts preview only after a new frame exists', async () => {
    const source = stream('main', 'environment')
    const page = setup(async () => source)
    state.capturedFile = new File(['photo'], 'photo.jpg', { type: 'image/jpeg' })
    document.body.classList.add('capture-ready')
    try {
        const restarting = retakeCapture()
        await tick()
        assert.equal(state.capturedFile, null)
        assert.equal(document.body.classList.contains('camera-ready'), false)
        page.ready(); await restarting
        assert.equal(state.stream, source)
        assert.equal(document.body.classList.contains('camera-ready'), true)
    } finally { page.restore() }
})
