import { state } from './state.js?v=5'
import { startCamera } from './camera.js?v=7'
import { loadGallery } from './gallery.js?v=6'

export async function sendFile() {
    if (!state.capturedFile) {
        return
    }

    const message =
        document.getElementById('message')

    const sendButton =
        document.getElementById('btnSend')

    const retakeButton =
        document.getElementById('btnRetake')

    message.hidden = true
    message.textContent = ''

    sendButton.disabled = true
    retakeButton.disabled = true
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
                `/upload/${
                    window.EVENT_SLUG ||
                    'default'
                }`,
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
            throw new Error(
                result.data?.detail ||
                result.data?.error ||
                'Upload-ul a eșuat.'
            )
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
    }
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

    viewfinder.style.display = 'block'

    document.body.classList.remove(
        'capture-ready'
    )

    hideUploadProgress()
}
