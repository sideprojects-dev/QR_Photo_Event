import { state } from './state.js?v=6'
import { startCamera, stopCamera } from './camera.js?v=9'
import { showVideoPreview } from './video.js?v=14'
import {
    createSelectionPreviewUrl,
    revokeSelectionPreviewUrl,
    clearSelectionPreviewUrls
} from './preview_urls.js?v=2'

const IMAGE_LIMIT = 25 * 1024 * 1024
const VIDEO_LIMIT = 250 * 1024 * 1024
const MAX_PHOTOS = 10
let nextPhotoId = 1
let enlargedPhotoId = null

const ALLOWED_EXTENSIONS = {
    'image/jpeg': ['jpg', 'jpeg'],
    'image/png': ['png'],
    'image/webp': ['webp'],
    'video/mp4': ['mp4'],
    'video/webm': ['webm']
}

export function validateGalleryFile(file) {
    const extension = file.name
        .split('.')
        .pop()
        .toLowerCase()

    const type = file.type.toLowerCase()

    if (
        ['heic', 'heif'].includes(extension) ||
        ['image/heic', 'image/heif'].includes(type)
    ) {
        return {
            error: 'Fotografiile HEIC/HEIF nu sunt acceptate. Alege un fișier JPEG, PNG sau WebP.'
        }
    }

    if (
        extension === 'mov' ||
        type === 'video/quicktime'
    ) {
        return {
            error: 'Videoclipurile MOV nu sunt acceptate. Alege un fișier MP4 sau WebM.'
        }
    }

    const extensions = ALLOWED_EXTENSIONS[type]

    if (
        !extensions ||
        !extensions.includes(extension)
    ) {
        return {
            error: 'Format neacceptat. Alege o fotografie JPEG, PNG sau WebP ori un videoclip MP4 sau WebM.'
        }
    }

    if (file.size === 0) {
        return { error: 'Fișierul selectat este gol.' }
    }

    const isImage = type.startsWith('image/')
    const limit = isImage ? IMAGE_LIMIT : VIDEO_LIMIT

    if (file.size > limit) {
        return {
            error: isImage
                ? 'Fotografia depășește limita de 25 MB.'
                : 'Videoclipul depășește limita de 250 MB.'
        }
    }

    return { kind: isImage ? 'image' : 'video' }
}

export function openGalleryPicker() {
    if (
        state.isRecording ||
        state.capturedFile ||
        state.selectedPhotos.length ||
        document.body.classList.contains('uploading')
    ) {
        return
    }

    const input = document.getElementById('galleryFileInput')
    input.value = ''
    input.click()
}

export function handleGalleryFileChange(event) {
    const input = event.currentTarget
    const files = Array.from(input.files || [])
    input.value = ''

    if (
        files.length === 0 ||
        state.isRecording ||
        state.capturedFile ||
        state.selectedPhotos.length ||
        document.body.classList.contains('uploading')
    ) {
        return
    }

    if (files.length === 1) {
        const result = validateGalleryFile(files[0])
        if (result.error) {
            showSelectionMessage(result.error)
            return
        }
        if (result.kind === 'video') {
            state.capturedFile = files[0]
            stopCamera()
            showVideoPreview(files[0])
            return
        }
    }

    if (files.some(file =>
        file.type.startsWith('video/') ||
        /\.(mp4|webm|mov)$/i.test(file.name)
    )) {
        showSelectionMessage('Selectează un singur videoclip, separat de fotografii.')
        return
    }

    if (files.length > MAX_PHOTOS) {
        showSelectionMessage('Poți selecta maximum 10 fotografii simultan.')
        return
    }

    const accepted = []
    const rejected = []
    for (const file of files) {
        const result = validateGalleryFile(file)
        if (result.error) {
            rejected.push(`${file.name}: ${result.error}`)
        } else if (result.kind === 'image') {
            accepted.push(file)
        }
    }

    if (accepted.length === 0) {
        showSelectionMessage(rejected.join(' '))
        return
    }

    state.selectedPhotos = accepted.map(file => ({
        id: nextPhotoId++,
        name: file.name,
        file,
        previewUrl: createSelectionPreviewUrl(file),
        status: 'pending',
        progress: 0,
        error: ''
    }))

    stopCamera()
    document.getElementById('viewfinder').style.display = 'none'
    document.body.classList.add('capture-ready', 'photo-selection-ready')
    document.getElementById('btnRetake').textContent = 'Anulează selecția'
    renderSelectedPhotos()
    showSelectionMessage(rejected.length
        ? `Au fost respinse ${rejected.length} fișiere: ${rejected.join(' ')}`
        : accepted.length === 1
            ? 'O fotografie gata de trimis.'
            : `${accepted.length} fotografii gata de trimis.`)
}

function showSelectionMessage(text) {
    const message = document.getElementById('message')
    message.hidden = false
    message.textContent = text
}

export function updateSelectedPhotoStatus(photo) {
    const elements = photo.elements
    if (!elements) return

    const labels = {
        pending: 'Gata de trimis',
        uploading: `Se transmite: ${photo.progress}%`,
        processing: 'Fișier trimis. Se procesează...',
        success: 'Încărcată cu succes',
        error: `Eroare: ${photo.error}`
    }
    elements.status.textContent = labels[photo.status]
    elements.progress.value = photo.progress
    elements.progress.hidden = photo.status === 'pending'
    elements.remove.disabled = document.body.classList.contains('uploading')
    if (!photo.previewUrl) {
        elements.image.removeAttribute('src')
        elements.open.hidden = true
        elements.done.hidden = false
    }
}

export function renderSelectedPhotos() {
    const section = document.getElementById('photoSelection')
    const grid = document.getElementById('photoSelectionGrid')
    const count = document.getElementById('photoSelectionCount')
    grid.replaceChildren()
    section.hidden = state.selectedPhotos.length === 0
    count.textContent = `${state.selectedPhotos.length} ${
        state.selectedPhotos.length === 1 ? 'fotografie selectată' : 'fotografii selectate'
    }`

    for (const photo of state.selectedPhotos) {
        const card = document.createElement('article')
        card.className = 'selected-photo'

        const image = document.createElement('img')
        image.alt = `Previzualizare: ${photo.name}`
        if (photo.previewUrl) image.src = photo.previewUrl

        const open = document.createElement('button')
        open.type = 'button'
        open.className = 'selected-photo-open'
        open.setAttribute('aria-label', `Mărește ${photo.name}`)
        open.appendChild(image)
        open.addEventListener('click', () => openSelectedPhotoPreview(photo))

        const done = document.createElement('div')
        done.className = 'selected-photo-done'
        done.textContent = '✓'
        done.hidden = true

        const name = document.createElement('p')
        name.className = 'selected-photo-name'
        name.textContent = photo.name

        const status = document.createElement('p')
        status.className = 'selected-photo-status'

        const progress = document.createElement('progress')
        progress.max = 100
        progress.setAttribute('aria-label', `Progres: ${photo.name}`)

        const remove = document.createElement('button')
        remove.type = 'button'
        remove.className = 'selected-photo-remove'
        remove.textContent = 'Elimină'
        remove.setAttribute('aria-label', `Elimină ${photo.name}`)
        remove.addEventListener('click', () => removeSelectedPhoto(photo.id))

        card.append(open, done, name, status, progress, remove)
        grid.appendChild(card)
        photo.elements = { open, image, done, status, progress, remove }
        updateSelectedPhotoStatus(photo)
    }
}

export function openSelectedPhotoPreview(photo) {
    if (!photo.previewUrl) return
    const modal = document.getElementById('selectedPhotoModal')
    const image = document.getElementById('selectedPhotoPreviewImage')
    enlargedPhotoId = photo.id
    image.src = photo.previewUrl
    image.alt = `Previzualizare mărită: ${photo.name}`
    modal.classList.add('is-open')
    modal.setAttribute('aria-hidden', 'false')
    document.body.classList.add('modal-open')
}

export function closeSelectedPhotoPreview() {
    const modal = document.getElementById('selectedPhotoModal')
    const image = document.getElementById('selectedPhotoPreviewImage')
    enlargedPhotoId = null
    image.removeAttribute('src')
    modal.classList.remove('is-open')
    modal.setAttribute('aria-hidden', 'true')
    if (!document.getElementById('galleryModal')?.classList.contains('is-open')) {
        document.body.classList.remove('modal-open')
    }
}

export function bindSelectedPhotoPreviewEvents() {
    const modal = document.getElementById('selectedPhotoModal')
    document.getElementById('closeSelectedPhotoPreview')?.addEventListener(
        'click', closeSelectedPhotoPreview
    )
    modal?.addEventListener('click', event => {
        if (event.target === modal) closeSelectedPhotoPreview()
    })
    document.addEventListener('keydown', event => {
        if (event.key === 'Escape' && modal?.classList.contains('is-open')) {
            closeSelectedPhotoPreview()
        }
    })
}

export function markSelectedPhotoUploaded(photo) {
    if (enlargedPhotoId === photo.id) closeSelectedPhotoPreview()
    revokeSelectionPreviewUrl(photo.previewUrl)
    photo.previewUrl = null
    photo.file = null
    photo.status = 'success'
    photo.progress = 100
    updateSelectedPhotoStatus(photo)
}

export function clearSelectedPhotos() {
    closeSelectedPhotoPreview()
    clearSelectionPreviewUrls()
    state.selectedPhotos = []
    document.getElementById('photoSelectionGrid').replaceChildren()
    document.getElementById('photoSelection').hidden = true
    document.body.classList.remove('photo-selection-ready', 'capture-ready')
    const sendButton = document.getElementById('btnSend')
    sendButton.textContent = 'Trimite'
    sendButton.disabled = false
    document.getElementById('btnRetake').textContent = 'Refă'
    document.getElementById('uploadProgress').hidden = true
}

export async function removeSelectedPhoto(id) {
    if (document.body.classList.contains('uploading')) return
    const index = state.selectedPhotos.findIndex(photo => photo.id === id)
    if (index < 0) return
    const [photo] = state.selectedPhotos.splice(index, 1)
    if (enlargedPhotoId === photo.id) closeSelectedPhotoPreview()
    revokeSelectionPreviewUrl(photo.previewUrl)
    if (state.selectedPhotos.length) {
        renderSelectedPhotos()
        document.getElementById('btnSend').disabled = !state.selectedPhotos.some(
            item => item.file && item.status !== 'success'
        )
    } else {
        clearSelectedPhotos()
        showSelectionMessage('')
        document.getElementById('viewfinder').style.display = 'block'
        await startCamera()
    }
}
