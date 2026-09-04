import { state } from './state.js'
import { startCamera } from './camera.js'
import { loadGallery } from './gallery.js'

export async function sendFile() {
    if (!state.capturedFile) {
        return
    }

    const message = document.getElementById('message')
    const sendButton = document.getElementById('btnSend')

    message.textContent = 'Se trimite...'
    sendButton.disabled = true

    const formData = new FormData()
    formData.append('file', state.capturedFile)

    try {
        const response = await fetch(
            `/upload/${window.EVENT_SLUG || 'default'}`,
            {
                method: 'POST',
                body: formData
            }
        )

        const data = await response.json()

        if (!response.ok) {
            throw new Error(
                data.detail ||
                data.error ||
                'Upload-ul a eșuat.'
            )
        }

        message.textContent =
            data.mesaj || 'Fișier încărcat cu succes.'

        resetCapturedMedia()
        await startCamera()
        await loadGallery(true)
    } catch (err) {
        message.textContent = 'Eroare: ' + err.message
        sendButton.disabled = false
    }
}

function resetCapturedMedia() {
    state.capturedFile = null

    const sendButton = document.getElementById('btnSend')
    const preview = document.getElementById('preview')
    const previewVideo = document.getElementById('previewVideo')

    sendButton.disabled = false
    sendButton.style.display = 'none'

    preview.style.display = 'none'
    preview.src = ''

    previewVideo.style.display = 'none'
    previewVideo.src = ''
}
