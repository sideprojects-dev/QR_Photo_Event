import { startCamera, flipCamera } from './camera.js?v=4'
import { takePhoto } from './photo.js?v=4'
import { toggleVideo } from './video.js?v=4'
import { sendFile } from './upload.js?v=4'

import {
    loadGallery,
    loadMoreGallery,
    closeGalleryModal,
    bindGalleryModalEvents
} from './gallery.js?v=4'

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
