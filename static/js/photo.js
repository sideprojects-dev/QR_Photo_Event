import { state } from './state.js?v=5'
import { stopCamera } from './camera.js?v=7'

export async function takePhoto() {
    const currentVideoTrack = state.stream?.getVideoTracks()[0]

    if (!currentVideoTrack) {
        document.getElementById('message').textContent =
            'Camera nu este disponibilă.'
        return
    }

    const shouldMirror =
        state.facingMode === 'user'

    // Camera frontală:
    // folosim ImageCapture pentru calitate/exposure bune, apoi detectăm
    // automat dacă iOS a returnat fotografia deja oglindită sau nu.
    if (shouldMirror) {
        try {
            const imageCaptureBlob =
                await takePhotoWithImageCapture(
                    currentVideoTrack
                )

            if (imageCaptureBlob) {
                const normalizedBlob =
                    await normalizeFrontPhotoOrientation(
                        imageCaptureBlob,
                        document.getElementById(
                            'viewfinder'
                        )
                    )

                setCapturedPhoto(
                    normalizedBlob
                )

                stopCamera()
                return
            }
        } catch (err) {
            console.warn(
                'ImageCapture frontal a eșuat. Folosim cadrul din preview:',
                err
            )
        }

        // Fallback stabil: cadrul live, deja expus corect.
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

    // Camera din spate: păstrăm metoda high-resolution existentă.
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

async function mirrorImageBlob(blob) {
    const image =
        await loadImageFromBlob(blob)

    const canvas =
        document.createElement('canvas')

    canvas.width =
        image.naturalWidth ||
        image.width

    canvas.height =
        image.naturalHeight ||
        image.height

    const ctx =
        canvas.getContext('2d')

    ctx.translate(
        canvas.width,
        0
    )

    ctx.scale(-1, 1)

    ctx.drawImage(
        image,
        0,
        0,
        canvas.width,
        canvas.height
    )

    const contentType =
        blob.type &&
        blob.type.startsWith('image/')
            ? blob.type
            : 'image/jpeg'

    return canvasToBlob(
        canvas,
        contentType,
        0.95
    )
}

function loadImageFromBlob(blob) {
    return new Promise(
        (resolve, reject) => {
            const image =
                new Image()

            const objectUrl =
                URL.createObjectURL(blob)

            image.onload = () => {
                URL.revokeObjectURL(
                    objectUrl
                )

                resolve(image)
            }

            image.onerror = () => {
                URL.revokeObjectURL(
                    objectUrl
                )

                reject(
                    new Error(
                        'Nu am putut procesa fotografia făcută cu camera frontală.'
                    )
                )
            }

            image.src = objectUrl
        }
    )
}


async function normalizeFrontPhotoOrientation(
    blob,
    video
) {
    const image =
        await loadImageFromBlob(blob)

    const sampleSize = 64

    const previewCanvas =
        document.createElement('canvas')

    const normalPhotoCanvas =
        document.createElement('canvas')

    const mirroredPhotoCanvas =
        document.createElement('canvas')

    previewCanvas.width =
        previewCanvas.height =
        sampleSize

    normalPhotoCanvas.width =
        normalPhotoCanvas.height =
        sampleSize

    mirroredPhotoCanvas.width =
        mirroredPhotoCanvas.height =
        sampleSize

    // Preview-ul frontal este oglindit pentru utilizator.
    drawCoverSample(
        video,
        previewCanvas,
        true
    )

    drawCoverSample(
        image,
        normalPhotoCanvas,
        false
    )

    drawCoverSample(
        image,
        mirroredPhotoCanvas,
        true
    )

    const previewData =
        previewCanvas
            .getContext('2d')
            .getImageData(
                0,
                0,
                sampleSize,
                sampleSize
            )
            .data

    const normalData =
        normalPhotoCanvas
            .getContext('2d')
            .getImageData(
                0,
                0,
                sampleSize,
                sampleSize
            )
            .data

    const mirroredData =
        mirroredPhotoCanvas
            .getContext('2d')
            .getImageData(
                0,
                0,
                sampleSize,
                sampleSize
            )
            .data

    const normalScore =
        calculateImageDifference(
            previewData,
            normalData
        )

    const mirroredScore =
        calculateImageDifference(
            previewData,
            mirroredData
        )

    // Dacă blob-ul deja seamănă mai mult cu preview-ul oglindit,
    // îl păstrăm. Altfel îl oglindim o singură dată.
    if (normalScore <= mirroredScore) {
        return blob
    }

    return imageToMirroredBlob(
        image,
        blob.type || 'image/jpeg'
    )
}

function drawCoverSample(
    source,
    canvas,
    mirror
) {
    const ctx =
        canvas.getContext('2d')

    const sourceWidth =
        source.videoWidth ||
        source.naturalWidth ||
        source.width

    const sourceHeight =
        source.videoHeight ||
        source.naturalHeight ||
        source.height

    const sourceRatio =
        sourceWidth / sourceHeight

    const targetRatio =
        canvas.width / canvas.height

    let sx = 0
    let sy = 0
    let sw = sourceWidth
    let sh = sourceHeight

    if (sourceRatio > targetRatio) {
        sw =
            sourceHeight *
            targetRatio

        sx =
            (sourceWidth - sw) / 2
    } else {
        sh =
            sourceWidth /
            targetRatio

        sy =
            (sourceHeight - sh) / 2
    }

    ctx.save()

    if (mirror) {
        ctx.translate(
            canvas.width,
            0
        )

        ctx.scale(-1, 1)
    }

    ctx.drawImage(
        source,
        sx,
        sy,
        sw,
        sh,
        0,
        0,
        canvas.width,
        canvas.height
    )

    ctx.restore()
}

function calculateImageDifference(
    first,
    second
) {
    let difference = 0

    // Ignorăm alpha.
    for (
        let i = 0;
        i < first.length;
        i += 4
    ) {
        difference +=
            Math.abs(
                first[i] -
                second[i]
            )

        difference +=
            Math.abs(
                first[i + 1] -
                second[i + 1]
            )

        difference +=
            Math.abs(
                first[i + 2] -
                second[i + 2]
            )
    }

    return difference
}

function imageToMirroredBlob(
    image,
    contentType
) {
    const canvas =
        document.createElement('canvas')

    canvas.width =
        image.naturalWidth ||
        image.width

    canvas.height =
        image.naturalHeight ||
        image.height

    const ctx =
        canvas.getContext('2d')

    ctx.translate(
        canvas.width,
        0
    )

    ctx.scale(-1, 1)

    ctx.drawImage(
        image,
        0,
        0,
        canvas.width,
        canvas.height
    )

    return canvasToBlob(
        canvas,
        contentType,
        0.95
    )
}

function loadImageFromBlob(blob) {
    return new Promise(
        (resolve, reject) => {
            const image =
                new Image()

            const objectUrl =
                URL.createObjectURL(blob)

            image.onload = () => {
                URL.revokeObjectURL(
                    objectUrl
                )

                resolve(image)
            }

            image.onerror = () => {
                URL.revokeObjectURL(
                    objectUrl
                )

                reject(
                    new Error(
                        'Nu am putut procesa fotografia frontală.'
                    )
                )
            }

            image.src = objectUrl
        }
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
