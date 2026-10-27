import assert from 'node:assert/strict'
import test from 'node:test'

import { coverCrop, isIOSCamera, startCanvasPreview } from '../static/js/camera_canvas.js?v=1'

test('canvas crop fills portrait frame without changing source proportions', () => {
    const portrait = coverCrop(1080, 1920, 398, 531)
    assert.equal(portrait.x, 0)
    assert.ok(portrait.y > 0)
    assert.ok(Math.abs(portrait.width / portrait.height - 398 / 531) < 1e-10)
    const landscape = coverCrop(1920, 1080, 398, 531)
    assert.equal(landscape.y, 0)
    assert.ok(landscape.x > 0)
    assert.ok(Math.abs(landscape.width / landscape.height - 398 / 531) < 1e-10)
    assert.equal(coverCrop(0, 1920, 398, 531), null)
})

test('iPhone preview draws before display, mirrors selfie and cancels frame updates', () => {
    const oldWindow = globalThis.window
    const oldNavigator = Object.getOwnPropertyDescriptor(globalThis, 'navigator')
    globalThis.window = { devicePixelRatio: 2 }
    Object.defineProperty(globalThis, 'navigator', {
        configurable: true, value: { userAgent: 'iPhone Safari' }
    })
    const calls = []
    const context = {
        setTransform: (...args) => calls.push(['transform', ...args]),
        drawImage: (...args) => calls.push(['draw', ...args])
    }
    const canvas = {
        width: 0, height: 0,
        getContext: () => context,
        getBoundingClientRect: () => ({ width: 398, height: 531 })
    }
    const video = {
        videoWidth: 1080, videoHeight: 1920,
        requestVideoFrameCallback(callback) { this.nextFrame = callback; return 42 },
        cancelVideoFrameCallback(id) { this.cancelled = id }
    }
    try {
        assert.equal(isIOSCamera(), true)
        const stop = startCanvasPreview(video, canvas, true)
        assert.equal(canvas.width, 796)
        assert.equal(canvas.height, 1062)
        assert.deepEqual(calls[0], ['transform', -1, 0, 0, 1, 796, 0])
        assert.equal(calls[1][0], 'draw')
        assert.ok(Math.abs(calls[1][4] / calls[1][5] - 398 / 531) < 1e-10)
        video.nextFrame()
        assert.equal(calls.filter(call => call[0] === 'draw').length, 2)
        stop()
        assert.equal(video.cancelled, 42)
    } finally {
        globalThis.window = oldWindow
        if (oldNavigator) Object.defineProperty(globalThis, 'navigator', oldNavigator)
        else delete globalThis.navigator
    }
})
