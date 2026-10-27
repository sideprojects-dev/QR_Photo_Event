export function isIOSCamera() {
    return /iPhone|iPad|iPod/.test(navigator.userAgent || '') ||
        (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)
}

export function coverCrop(sourceWidth, sourceHeight, targetWidth, targetHeight) {
    if (Math.min(sourceWidth, sourceHeight, targetWidth, targetHeight) <= 0) return null
    const sourceAspect = sourceWidth / sourceHeight
    const targetAspect = targetWidth / targetHeight
    if (sourceAspect > targetAspect) {
        const width = sourceHeight * targetAspect
        return { x: (sourceWidth - width) / 2, y: 0, width, height: sourceHeight }
    }
    const height = sourceWidth / targetAspect
    return { x: 0, y: (sourceHeight - height) / 2, width: sourceWidth, height }
}

export function startCanvasPreview(video, canvas, mirrored) {
    const context = canvas.getContext('2d', { alpha: false })
    if (!context) throw new Error('Previzualizarea camerei nu este disponibilă.')
    let stopped = false
    let callbackId = null
    let callbackType = null

    function draw() {
        if (stopped) return false
        const box = canvas.getBoundingClientRect()
        const crop = coverCrop(video.videoWidth, video.videoHeight, box.width, box.height)
        if (!crop) return false
        const ratio = Math.min(window.devicePixelRatio || 1, 2)
        const width = Math.max(1, Math.round(box.width * ratio))
        const height = Math.max(1, Math.round(box.height * ratio))
        if (canvas.width !== width || canvas.height !== height) {
            canvas.width = width
            canvas.height = height
        }
        context.setTransform(mirrored ? -1 : 1, 0, 0, 1, mirrored ? width : 0, 0)
        context.drawImage(
            video, crop.x, crop.y, crop.width, crop.height,
            0, 0, width, height
        )
        return true
    }

    function schedule() {
        if (stopped) return
        if (typeof video.requestVideoFrameCallback === 'function') {
            callbackType = 'video'
            callbackId = video.requestVideoFrameCallback(next)
        } else {
            callbackType = 'animation'
            callbackId = requestAnimationFrame(next)
        }
    }

    function next() {
        callbackId = null
        if (stopped) return
        draw()
        schedule()
    }

    // Draw into the hidden canvas before making its first frame visible.
    if (!draw()) throw new Error('Camera nu a trimis un cadru video valid.')
    schedule()
    return () => {
        stopped = true
        if (callbackId === null) return
        if (callbackType === 'video') video.cancelVideoFrameCallback?.(callbackId)
        else cancelAnimationFrame(callbackId)
        callbackId = null
    }
}
