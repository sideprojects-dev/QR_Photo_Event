import { startCamera, flipCamera } from './camera.js'
import { takePhoto } from './photo.js'
import { toggleVideo } from './video.js'
import { sendFile } from './upload.js'
import {
    loadGallery,
    loadMoreGallery,
    closeGalleryModal,
    bindGalleryModalEvents
} from './gallery.js'

function bindControls() {
    document.getElementById('btnFlip')?.addEventListener('click', flipCamera)
    document.getElementById('btnCapture')?.addEventListener('click', takePhoto)
    document.getElementById('btnRecord')?.addEventListener('click', toggleVideo)
    document.getElementById('btnSend')?.addEventListener('click', sendFile)
    document.getElementById('btnLoadMore')?.addEventListener('click', loadMoreGallery)
    document.getElementById('btnCloseGallery')?.addEventListener('click', closeGalleryModal)
}

async function init() {
    bindControls()
    bindGalleryModalEvents()

    await startCamera()
    await loadGallery(true)
}

init()
