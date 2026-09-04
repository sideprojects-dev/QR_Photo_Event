import { state } from './state.js?v=5'

export async function takePhoto() {
    const currentVideoTrack = state.stream?.getVideoTracks()[0]

    if (!currentVideoTrack) {
        document.getElementById('message').textContent =
            'Camera nu este disponibilă.'
        return
    }

    // Chrome/Android usually exposes ImageCapture and can return a still image
    // at a much higher resolution than the 1080p preview stream.
    try {
        const imageCaptureBlob = await takePhotoWithImageCapture(currentVideoTrack)

        if (imageCaptureBlob) {
            setCapturedPhoto(imageCaptureBlob)
            return
        }
    } catch (err) {
        console.warn('ImageCapture a eșuat. Încercăm stream foto high-resolution:', err)
    }

    // This path is known to work on iOS Safari and produced 3024x4032 in testing.
    try {
        const highResolutionBlob = await takeHighResolutionPhoto()

        if (highResolutionBlob) {
            setCapturedPhoto(highResolutionBlob)
            return
        }
    } catch (err) {
        console.warn('Captura high-resolution a eșuat. Folosim fallback:', err)
    }

    takePhotoFromVideoFrame(document.getElementById('viewfinder'))
}

async function takePhotoWithImageCapture(videoTrack) {
    if (!('ImageCapture' in window)) {
        return null
    }

    const imageCapture = new ImageCapture(videoTrack)
    let photoSettings = undefined

    try {
        const capabilities = await imageCapture.getPhotoCapabilities()
        const maxWidth = capabilities?.imageWidth?.max
        const maxHeight = capabilities?.imageHeight?.max

        if (maxWidth && maxHeight) {
            photoSettings = {
                imageWidth: maxWidth,
                imageHeight: maxHeight
            }
        }
    } catch (err) {
        // Some browsers implement takePhoto() but not getPhotoCapabilities().
        console.warn('Nu am putut citi capabilitățile foto:', err)
    }

    return imageCapture.takePhoto(photoSettings)
}

async function takeHighResolutionPhoto() {
    const videoConstraints = {
        width: { ideal: 4032 },
        height: { ideal: 3024 }
    }

    if (state.selectedCameraId) {
        videoConstraints.deviceId = { exact: state.selectedCameraId }
    } else {
        videoConstraints.facingMode = { ideal: state.facingMode }
    }

    const photoStream = await navigator.mediaDevices.getUserMedia({
        video: videoConstraints,
        audio: false
    })

    try {
        const tempVideo = document.createElement('video')
        tempVideo.srcObject = photoStream
        tempVideo.playsInline = true
        tempVideo.muted = true

        await tempVideo.play()
        await waitForVideoReady(tempVideo)

        const canvas = document.createElement('canvas')
        canvas.width = tempVideo.videoWidth
        canvas.height = tempVideo.videoHeight

        drawVideoFrameToCanvas(tempVideo, canvas)

        return canvasToBlob(canvas, 'image/jpeg', 0.95)
    } finally {
        photoStream.getTracks().forEach(track => track.stop())
    }
}

function takePhotoFromVideoFrame(video) {
    const canvas = document.createElement('canvas')
    canvas.width = video.videoWidth
    canvas.height = video.videoHeight

    drawVideoFrameToCanvas(video, canvas)

    canvasToBlob(canvas, 'image/jpeg', 0.95)
        .then(setCapturedPhoto)
        .catch(err => {
            document.getElementById('message').textContent = err.message
        })
}

function drawVideoFrameToCanvas(video, canvas) {
    const ctx = canvas.getContext('2d')

    if (state.facingMode === 'user') {
        ctx.translate(canvas.width, 0)
        ctx.scale(-1, 1)
    }

    ctx.drawImage(video, 0, 0)
}

function waitForVideoReady(video) {
    return new Promise(resolve => {
        if (video.readyState >= 2 && video.videoWidth > 0) {
            resolve()
            return
        }

        video.addEventListener('loadeddata', () => resolve(), { once: true })
    })
}

function canvasToBlob(canvas, type, quality) {
    return new Promise((resolve, reject) => {
        canvas.toBlob(blob => {
            if (!blob) {
                reject(new Error('Nu am putut crea fotografia.'))
                return
            }

            resolve(blob)
        }, type, quality)
    })
}

function setCapturedPhoto(blob) {
    const contentType = blob.type || 'image/jpeg'
    const extension = contentType.includes('png') ? 'png' : 'jpg'

    state.capturedFile = new File(
        [blob],
        `photo.${extension}`,
        { type: contentType }
    )

    showPhotoPreview(blob)
}

function showPhotoPreview(blob) {
    const preview = document.getElementById('preview')
    const previewVideo = document.getElementById('previewVideo')

    preview.src = URL.createObjectURL(blob)
    preview.style.display = 'block'

    previewVideo.style.display = 'none'
    document.getElementById('btnSend').style.display = 'inline-block'
}
