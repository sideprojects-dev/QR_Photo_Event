import assert from 'node:assert/strict'
import test from 'node:test'

import { createMirroredVideoStream } from '../static/js/mirrored_video.js'

test('front camera frames are mirrored and the canvas track is released', () => {
    const originalDocument = globalThis.document
    const originalRequest = globalThis.requestAnimationFrame
    const originalCancel = globalThis.cancelAnimationFrame

    const calls = []
    const videoTrack = { stop: () => calls.push('stop-video') }
    const audioTrack = { id: 'audio' }
    const recordedStream = {
        addTrack: track => calls.push(['add-audio', track]),
        getVideoTracks: () => [videoTrack]
    }
    const context = {
        save: () => calls.push('save'),
        translate: (x, y) => calls.push(['translate', x, y]),
        scale: (x, y) => calls.push(['scale', x, y]),
        drawImage: () => calls.push('draw'),
        restore: () => calls.push('restore')
    }
    const canvas = {
        width: 0,
        height: 0,
        getContext: () => context,
        captureStream: () => recordedStream
    }

    globalThis.document = { createElement: () => canvas }
    globalThis.requestAnimationFrame = () => 7
    globalThis.cancelAnimationFrame = id => calls.push(['cancel', id])

    try {
        const sourceStream = {
            getVideoTracks: () => [{ getSettings: () => ({ width: 640, height: 480 }) }],
            getAudioTracks: () => [audioTrack]
        }
        const sourceVideo = { readyState: 2, videoWidth: 640, videoHeight: 480 }
        const recording = createMirroredVideoStream(sourceStream, sourceVideo)

        assert.equal(recording.stream, recordedStream)
        assert.deepEqual(calls.slice(0, 5), [
            'save',
            ['translate', 640, 0],
            ['scale', -1, 1],
            'draw',
            'restore'
        ])
        assert.deepEqual(calls[5], ['add-audio', audioTrack])

        recording.stop()
        assert.deepEqual(calls.slice(-2), [['cancel', 7], 'stop-video'])
    } finally {
        globalThis.document = originalDocument
        globalThis.requestAnimationFrame = originalRequest
        globalThis.cancelAnimationFrame = originalCancel
    }
})
