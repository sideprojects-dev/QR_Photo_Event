import { state } from './state.js?v=5'
import { stopCamera } from './camera.js?v=8'
import { showPhotoPreview } from './photo.js?v=13'
import { showVideoPreview } from './video.js?v=13'

const IMAGE_LIMIT = 25 * 1024 * 1024
const VIDEO_LIMIT = 250 * 1024 * 1024

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
    const file = input.files?.[0]
    input.value = ''

    if (
        !file ||
        state.isRecording ||
        state.capturedFile ||
        document.body.classList.contains('uploading')
    ) {
        return
    }

    const result = validateGalleryFile(file)

    if (result.error) {
        const message = document.getElementById('message')
        message.hidden = false
        message.textContent = result.error
        return
    }

    state.capturedFile = file
    stopCamera()

    if (result.kind === 'image') {
        showPhotoPreview(file)
    } else {
        showVideoPreview(file)
    }
}
