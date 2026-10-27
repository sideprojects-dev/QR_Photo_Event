export function createMirroredVideoStream(sourceStream, sourceVideo) {
    const canvas = document.createElement('canvas')

    if (typeof canvas.captureStream !== 'function') {
        throw new Error('Acest browser nu poate înregistra corect camera frontală.')
    }

    const settings = sourceStream.getVideoTracks()[0]?.getSettings() || {}
    const sourceWidth = sourceVideo.videoWidth || settings.width || 1280
    const sourceHeight = sourceVideo.videoHeight || settings.height || 720
    const scale = Math.min(1, 1920 / sourceWidth)

    canvas.width = Math.max(1, Math.round(sourceWidth * scale))
    canvas.height = Math.max(1, Math.round(sourceHeight * scale))

    const context = canvas.getContext('2d', { alpha: false })

    if (!context) {
        throw new Error('Nu am putut pregăti înregistrarea video.')
    }

    const drawFrame = () => {
        if (
            sourceVideo.readyState < 2 ||
            !sourceVideo.videoWidth ||
            !sourceVideo.videoHeight
        ) {
            return
        }

        context.save()
        context.translate(canvas.width, 0)
        context.scale(-1, 1)
        context.drawImage(
            sourceVideo,
            0,
            0,
            canvas.width,
            canvas.height
        )
        context.restore()
    }

    drawFrame()

    const stream = canvas.captureStream(30)

    sourceStream.getAudioTracks().forEach(track => {
        stream.addTrack(track)
    })

    let active = true
    let frameId = null

    const drawNextFrame = () => {
        if (!active) {
            return
        }

        drawFrame()
        frameId = requestAnimationFrame(drawNextFrame)
    }

    frameId = requestAnimationFrame(drawNextFrame)

    return {
        stream,
        stop() {
            active = false
            cancelAnimationFrame(frameId)
            stream.getVideoTracks().forEach(track => track.stop())
        }
    }
}
