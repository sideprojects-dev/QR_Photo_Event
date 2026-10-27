import { state } from './state.js?v=6'
import { startCamera } from './camera.js?v=15'
import { loadGallery } from './gallery.js?v=8'
import { clearPreviewObjectUrl } from './preview_urls.js?v=2'
import { withEventAccess } from './guest_access.js?v=1'
import {
    clearSelectedPhotos,
    markSelectedPhotoUploaded,
    renderSelectedPhotos,
    updateSelectedPhotoStatus
} from './gallery_upload.js?v=2'

export async function sendFile() {
    const pendingPhotos = state.selectedPhotos.some(
        photo => photo.file && photo.status !== 'success'
    )
    if (
        (!state.capturedFile && !pendingPhotos) ||
        document.body.classList.contains('uploading')
    ) {
        return
    }

    const eventSlug = window.EVENT_SLUG

    const message =
        document.getElementById('message')

    if (!eventSlug) {
        message.hidden = false
        message.textContent =
            'Evenimentul nu a fost identificat. Scanează din nou codul QR.'
        return
    }

    if (pendingPhotos) {
        await sendSelectedPhotos(eventSlug, message)
        return
    }

    const sendButton =
        document.getElementById('btnSend')

    const retakeButton =
        document.getElementById('btnRetake')

    const galleryButton =
        document.getElementById('btnUploadFromGallery')

    message.hidden = true
    message.textContent = ''

    sendButton.disabled = true
    retakeButton.disabled = true
    galleryButton.disabled = true
    document.body.classList.add('uploading')

    showUploadProgress(
        0,
        'Se pregătește upload-ul...'
    )

    const formData = new FormData()

    formData.append(
        'file',
        state.capturedFile
    )

    try {
        const result =
            await uploadWithProgress(
                withEventAccess(`/upload/${
                    encodeURIComponent(eventSlug)
                }`),
                formData,
                percent => {
                    if (percent >= 100) {
                        showUploadProgress(
                            100,
                            'Fișier trimis. Se procesează...'
                        )
                        return
                    }

                    showUploadProgress(
                        percent,
                        'Se încarcă...'
                    )
                }
            )

        if (!result.ok) {
            throw new Error(uploadErrorMessage(result))
        }

        showUploadProgress(
            100,
            'Gata'
        )

        message.hidden = false
        message.textContent =
            result.data?.mesaj ||
            'Fișier încărcat cu succes.'

        resetCapturedMedia()
        await startCamera()
        await loadGallery(true)

    } catch (err) {
        message.hidden = false
        message.textContent =
            'Eroare: ' + err.message

        sendButton.disabled = false
        retakeButton.disabled = false

        showUploadProgress(
            getCurrentProgress(),
            'Upload eșuat'
        )
    } finally {
        document.body.classList.remove(
            'uploading'
        )
        galleryButton.disabled = false
    }
}

async function sendSelectedPhotos(eventSlug, message) {
    const sendButton = document.getElementById('btnSend')
    const retakeButton = document.getElementById('btnRetake')
    const galleryButton = document.getElementById('btnUploadFromGallery')
    const pending = state.selectedPhotos.filter(photo =>
        photo.file && photo.status !== 'success'
    )
    let succeeded = 0
    let failed = 0

    sendButton.disabled = true
    retakeButton.disabled = true
    galleryButton.disabled = true
    document.body.classList.add('uploading')
    renderSelectedPhotos()
    message.hidden = false
    message.textContent = `Se încarcă ${pending.length} fotografii...`

    try {
        for (const [index, photo] of pending.entries()) {
            photo.status = 'uploading'
            photo.progress = 0
            photo.error = ''
            updateSelectedPhotoStatus(photo)
            showUploadProgress(0, `Fotografia ${index + 1}/${pending.length}: se transmite...`)

            try {
                const formData = new FormData()
                formData.append('file', photo.file)
                const result = await uploadWithProgress(
                    withEventAccess(`/upload/${encodeURIComponent(eventSlug)}`),
                    formData,
                    percent => {
                        photo.progress = percent
                        photo.status = percent >= 100 ? 'processing' : 'uploading'
                        updateSelectedPhotoStatus(photo)
                        showUploadProgress(
                            percent,
                            percent >= 100
                                ? `Fotografia ${index + 1}/${pending.length}: trimisă, se procesează...`
                                : `Fotografia ${index + 1}/${pending.length}: se transmite...`
                        )
                    }
                )
                if (!result.ok) throw new Error(uploadErrorMessage(result))
                markSelectedPhotoUploaded(photo)
                succeeded++
            } catch (err) {
                photo.status = 'error'
                photo.error = err.message || 'Încărcarea a eșuat.'
                updateSelectedPhotoStatus(photo)
                failed++
            }
        }

        message.textContent = failed
            ? `${succeeded} fotografii încărcate, ${failed} eșuate. Poți reîncerca doar fotografiile eșuate.`
            : `${succeeded} fotografii încărcate cu succes.`
        showUploadProgress(100, failed ? 'Finalizat cu erori' : 'Gata')
        if (succeeded) await loadGallery(true)
    } finally {
        document.body.classList.remove('uploading')
        galleryButton.disabled = false
        retakeButton.disabled = false
        sendButton.disabled = !state.selectedPhotos.some(photo => photo.file)
        sendButton.textContent = failed ? 'Reîncearcă eșuate' : 'Trimite'
        renderSelectedPhotos()
    }
}

function uploadErrorMessage(result) {
    if (result.status === 413) return 'Fișierul depășește limita permisă.'
    if (result.status === 404) return 'Evenimentul sau codul de acces nu mai este valid.'
    if (result.status === 400) return 'Serverul nu a acceptat formatul fișierului.'
    return 'Încărcarea a eșuat pe server. Încearcă din nou.'
}

export async function retakeCapture() {
    if (document.body.classList.contains('uploading')) {
        return
    }

    resetCapturedMedia()

    const message =
        document.getElementById(
            'message'
        )

    message.hidden = false
    message.textContent = ''

    await startCamera()
}

function uploadWithProgress(
    url,
    formData,
    onProgress
) {
    return new Promise(
        (resolve, reject) => {
            const xhr =
                new XMLHttpRequest()

            xhr.open(
                'POST',
                url,
                true
            )

            xhr.upload.onprogress =
                event => {
                    if (
                        !event.lengthComputable ||
                        event.total <= 0
                    ) {
                        return
                    }

                    const percent =
                        Math.min(
                            100,
                            Math.round(
                                (
                                    event.loaded /
                                    event.total
                                ) * 100
                            )
                        )

                    onProgress(percent)
                }

            xhr.onload = () => {
                let data = {}

                try {
                    data =
                        xhr.responseText
                            ? JSON.parse(
                                xhr.responseText
                            )
                            : {}
                } catch {
                    data = {}
                }

                resolve({
                    ok:
                        xhr.status >= 200 &&
                        xhr.status < 300,
                    status: xhr.status,
                    data
                })
            }

            xhr.onerror = () => {
                reject(
                    new Error(
                        'Conexiunea s-a întrerupt în timpul upload-ului.'
                    )
                )
            }

            xhr.onabort = () => {
                reject(
                    new Error(
                        'Upload-ul a fost anulat.'
                    )
                )
            }

            xhr.send(formData)
        }
    )
}

function showUploadProgress(
    percent,
    label
) {
    const container =
        document.getElementById(
            'uploadProgress'
        )

    const bar =
        document.getElementById(
            'uploadProgressBar'
        )

    const percentLabel =
        document.getElementById(
            'uploadProgressPercent'
        )

    const textLabel =
        document.getElementById(
            'uploadProgressLabel'
        )

    const safePercent =
        Math.max(
            0,
            Math.min(100, percent)
        )

    container.hidden = false
    bar.style.width =
        `${safePercent}%`

    percentLabel.textContent =
        `${safePercent}%`

    textLabel.textContent =
        label
}

function getCurrentProgress() {
    const value =
        parseInt(
            document.getElementById(
                'uploadProgressPercent'
            )?.textContent ||
            '0',
            10
        )

    return Number.isFinite(value)
        ? value
        : 0
}

function hideUploadProgress() {
    const container =
        document.getElementById(
            'uploadProgress'
        )

    const bar =
        document.getElementById(
            'uploadProgressBar'
        )

    const percentLabel =
        document.getElementById(
            'uploadProgressPercent'
        )

    const textLabel =
        document.getElementById(
            'uploadProgressLabel'
        )

    container.hidden = true
    bar.style.width = '0%'
    percentLabel.textContent = '0%'
    textLabel.textContent =
        'Se încarcă...'
}

function resetCapturedMedia() {
    state.capturedFile = null
    state.recordedChunks = []
    clearSelectedPhotos()

    document.getElementById(
        'galleryFileInput'
    ).value = ''

    const sendButton =
        document.getElementById(
            'btnSend'
        )

    const retakeButton =
        document.getElementById(
            'btnRetake'
        )

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

    sendButton.disabled = false
    retakeButton.disabled = false

    preview.style.display = 'none'
    preview.removeAttribute('src')

    previewVideo.pause()
    previewVideo.removeAttribute('src')
    previewVideo.load()
    previewVideo.style.display = 'none'
    clearPreviewObjectUrl()

    viewfinder.style.display = 'block'

    document.body.classList.remove(
        'capture-ready'
    )

    hideUploadProgress()
}
