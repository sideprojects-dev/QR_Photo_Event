import { state } from './state.js?v=5'
import {
    startCamera,
    stopCamera,
    flipCamera
} from './camera.js?v=7'

import { takePhoto } from './photo.js?v=11'

import {
    toggleVideo,
    stopRecordingForBackground
} from './video.js?v=9'

import {
    sendFile,
    retakeCapture
} from './upload.js?v=8'

import {
    loadGallery,
    loadMoreGallery,
    closeGalleryModal,
    bindGalleryModalEvents
} from './gallery.js?v=6'

function bindControls() {
    document.getElementById(
        'btnFlip'
    )?.addEventListener(
        'click',
        flipCamera
    )

    document.getElementById(
        'btnCapture'
    )?.addEventListener(
        'click',
        takePhoto
    )

    document.getElementById(
        'btnRecord'
    )?.addEventListener(
        'click',
        toggleVideo
    )

    document.getElementById(
        'btnRetake'
    )?.addEventListener(
        'click',
        retakeCapture
    )

    document.getElementById(
        'btnSend'
    )?.addEventListener(
        'click',
        sendFile
    )

    document.getElementById(
        'btnLoadMore'
    )?.addEventListener(
        'click',
        loadMoreGallery
    )

    document.getElementById(
        'btnCloseGallery'
    )?.addEventListener(
        'click',
        closeGalleryModal
    )
}

function bindMediaLifecycle() {
    document.addEventListener(
        'visibilitychange',
        async () => {
            if (document.hidden) {
                if (state.isRecording) {
                    stopRecordingForBackground()
                } else {
                    stopCamera()
                }

                return
            }

            // Dacă avem deja o poză/video făcut(ă), păstrăm preview-ul.
            if (
                state.capturedFile ||
                state.isRecording
            ) {
                return
            }

            await startCamera()
        }
    )

    window.addEventListener(
        'pagehide',
        () => {
            if (state.isRecording) {
                stopRecordingForBackground()
            } else {
                stopCamera()
            }
        }
    )

    window.addEventListener(
        'beforeunload',
        stopCamera
    )
}

async function init() {
    bindControls()
    bindGalleryModalEvents()
    bindMediaLifecycle()

    await startCamera()
    await loadGallery(true)
}

init()
