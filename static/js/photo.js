import { state } from './state.js?v=5'
import { stopCamera } from './camera.js?v=7'

export async function takePhoto() {
    const currentVideoTrack = state.stream?.getVideoTracks()[0]

    if (!currentVideoTrack) {
        document.getElementById('message').textContent =
            'Camera nu este disponibilă.'
        return
    }

    // Reținem camera folosită chiar dacă stream-ul este oprit ulterior.
    const shouldMirror =
        state.facingMode === 'user'

    // Pentru camera frontală evităm ImageCapture, deoarece pe unele
    // versiuni iOS rezultatul poate veni deja oglindit, iar pe altele nu.
    //
    // În schimb pornim temporar aceeași cameră la rezoluție cât mai mare,
    // desenăm cadrul în canvas și îl oglindim exact o singură dată.
    // Astfel păstrăm orientarea corectă și o calitate mult mai bună decât
    // dacă am captura doar cadrul din preview-ul 1920x1080.
    if (shouldMirror) {
        try {
            const highResolutionFrontBlob =
                await takeHighResolutionPhoto(
                    true
                )

            if (highResolutionFrontBlob) {
                setCapturedPhoto(
                    highResolutionFrontBlob
                )

                stopCamera()
                return
            }
        } catch (err) {
            console.warn(
                'Captura frontală high-resolution a eșuat. Folosim cadrul din preview:',
                err
            )
        }

        try {
            const frontCameraBlob =
                await takePhotoFromVideoFrame(
                    document.getElementById(
                        'viewfinder'
                    ),
                    true
                )

            setCapturedPhoto(
                frontCameraBlob
            )
        } catch (err) {
            document.getElementById(
                'message'
            ).textContent = err.message
        } finally {
            stopCamera()
        }

        return
    }

    // Pentru camera din spate păstrăm captură high-resolution / ImageCapture.
    try {
        const imageCaptureBlob =
            await takePhotoWithImageCapture(
                currentVideoTrack
            )

        if (imageCaptureBlob) {
            setCapturedPhoto(
                imageCaptureBlob
            )

            stopCamera()
            return
        }
    } catch (err) {
        console.warn(
            'ImageCapture a eșuat. Încercăm stream foto high-resolution:',
            err
        )
    }

    try {
        const highResolutionBlob =
            await takeHighResolutionPhoto(
                false
            )

        if (highResolutionBlob) {
            setCapturedPhoto(
                highResolutionBlob
            )

            stopCamera()
            return
        }
    } catch (err) {
        console.warn(
            'Captura high-resolution a eșuat. Folosim fallback:',
            err
        )
    }

    try {
        const fallbackBlob =
            await takePhotoFromVideoFrame(
                document.getElementById(
                    'viewfinder'
                ),
                false
            )

        setCapturedPhoto(fallbackBlob)
    } catch (err) {
        document.getElementById(
            'message'
        ).textContent = err.message
    } finally {
        stopCamera()
    }
}

async function takePhotoWithImageCapture(videoTrack) {
    if (!('ImageCapture' in window)) {
        return null
    }

    const imageCapture =
        new ImageCapture(videoTrack)

    let photoSettings = undefined

    try {
        const capabilities =
            await imageCapture.getPhotoCapabilities()

        const maxWidth =
            capabilities?.imageWidth?.max

        const maxHeight =
            capabilities?.imageHeight?.max

        if (maxWidth && maxHeight) {
            photoSettings = {
                imageWidth: maxWidth,
                imageHeight: maxHeight
            }
        }
    } catch (err) {
        console.warn(
            'Nu am putut citi capabilitățile foto:',
            err
        )
    }

    return imageCapture.takePhoto(
        photoSettings
    )
}

async function takeHighResolutionPhoto(
    shouldMirror
) {
    const videoConstraints = {
        width: { ideal: 4032 },
        height: { ideal: 3024 }
    }

    if (state.selectedCameraId) {
        videoConstraints.deviceId = {
            exact: state.selectedCameraId
        }
    } else {
        videoConstraints.facingMode = {
            ideal: state.facingMode
        }
    }

    const photoStream =
        await navigator.mediaDevices.getUserMedia({
            video: videoConstraints,
            audio: false
        })

    try {
        const tempVideo =
            document.createElement('video')

        tempVideo.srcObject =
            photoStream

        tempVideo.playsInline = true
        tempVideo.muted = true

        await tempVideo.play()
        await waitForVideoReady(tempVideo)

        const canvas =
            document.createElement('canvas')

        canvas.width =
            tempVideo.videoWidth

        canvas.height =
            tempVideo.videoHeight

        drawVideoFrameToCanvas(
            tempVideo,
            canvas,
            shouldMirror
        )

        return canvasToBlob(
            canvas,
            'image/jpeg',
            0.95
        )
    } finally {
        photoStream
            .getTracks()
            .forEach(track => track.stop())
    }
}

async function takePhotoFromVideoFrame(
    video,
    shouldMirror
) {
    const canvas =
        document.createElement('canvas')

    canvas.width =
        video.videoWidth

    canvas.height =
        video.videoHeight

    drawVideoFrameToCanvas(
        video,
        canvas,
        shouldMirror
    )

    return canvasToBlob(
        canvas,
        'image/jpeg',
        0.95
    )
}

function drawVideoFrameToCanvas(
    video,
    canvas,
    shouldMirror
) {
    const ctx =
        canvas.getContext('2d')

    if (shouldMirror) {
        ctx.translate(
            canvas.width,
            0
        )

        ctx.scale(-1, 1)
    }

    ctx.drawImage(
        video,
        0,
        0,
        canvas.width,
        canvas.height
    )
}

function waitForVideoReady(video) {
    return new Promise(resolve => {
        if (
            video.readyState >= 2 &&
            video.videoWidth > 0
        ) {
            resolve()
            return
        }

        video.addEventListener(
            'loadeddata',
            () => resolve(),
            { once: true }
        )
    })
}

function canvasToBlob(
    canvas,
    type,
    quality
) {
    return new Promise(
        (resolve, reject) => {
            canvas.toBlob(
                blob => {
                    if (!blob) {
                        reject(
                            new Error(
                                'Nu am putut crea fotografia.'
                            )
                        )
                        return
                    }

                    resolve(blob)
                },
                type,
                quality
            )
        }
    )
}

function setCapturedPhoto(blob) {
    const contentType =
        blob.type || 'image/jpeg'

    const extension =
        contentType.includes('png')
            ? 'png'
            : 'jpg'

    state.capturedFile =
        new File(
            [blob],
            `photo.${extension}`,
            { type: contentType }
        )

    showPhotoPreview(blob)
}

function showPhotoPreview(blob) {
    const viewfinder =
        document.getElementById(
            'viewfinder'
        )

    const preview =
        document.getElementById(
            'preview'
        )

    const previewVideo =
        document.getElementById(
            'previewVideo'
        )

    preview.src =
        URL.createObjectURL(blob)

    preview.style.display =
        'block'

    previewVideo.pause()
    previewVideo.removeAttribute(
        'src'
    )
    previewVideo.load()
    previewVideo.style.display =
        'none'

    viewfinder.style.display =
        'none'

    document.body.classList.add(
        'capture-ready'
    )

    document.getElementById(
        'message'
    ).textContent =
        'Fotografia este gata. O poți trimite sau reface.'
}
