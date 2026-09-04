import { state } from './state.js?v=5'
import {
    startCamera,
    stopCamera
} from './camera.js?v=7'

let frontCanvas = null
let frontCanvasStream = null
let frontCanvasAnimationId = null
let frontCanvasVideoTrack = null

function getSupportedVideoMimeType() {
    const types = [
        'video/mp4;codecs=h264,aac',
        'video/mp4',
        'video/webm;codecs=vp9,opus',
        'video/webm;codecs=vp8,opus',
        'video/webm'
    ]

    return (
        types.find(
            type =>
                MediaRecorder.isTypeSupported(
                    type
                )
        ) || ''
    )
}

export async function toggleVideo() {
    if (!state.isRecording) {
        await startRecording()
        return
    }

    stopRecording()
}

async function startRecording() {
    // Microfonul pornește numai când începe filmarea.
    await startCamera({
        withAudio: true
    })

    if (!state.stream) {
        document.getElementById(
            'message'
        ).textContent =
            'Camera nu este disponibilă.'
        return
    }

    state.recordedChunks = []

    const mimeType =
        getSupportedVideoMimeType()

    const recorderOptions = {
        videoBitsPerSecond:
            16000000,
        audioBitsPerSecond:
            128000
    }

    if (mimeType) {
        recorderOptions.mimeType =
            mimeType
    }

    let recordingStream =
        state.stream

    // Camera frontală:
    // înregistrăm un canvas desenat din același preview live și îl
    // oglindim exact o singură dată. Este aceeași regulă folosită de
    // captura foto care a funcționat corect pe Android și iOS.
    if (state.facingMode === 'user') {
        const normalizedFrontStream =
            createNormalizedFrontVideoStream()

        if (normalizedFrontStream) {
            recordingStream =
                normalizedFrontStream
        }
    }

    state.mediaRecorder =
        new MediaRecorder(
            recordingStream,
            recorderOptions
        )

    state.mediaRecorder.onerror =
        event => {
            console.error(
                'MediaRecorder error:',
                event.error
            )

            document.getElementById(
                'message'
            ).textContent =
                'A apărut o eroare la înregistrarea video: ' +
                (
                    event.error?.message ||
                    'eroare necunoscută'
                )

            state.isRecording = false
            stopFrontCanvasRecording()
            stopCamera()
            resetRecordingButtons()
        }

    state.mediaRecorder.ondataavailable =
        event => {
            if (event.data.size > 0) {
                state.recordedChunks.push(
                    event.data
                )
            }
        }

    state.mediaRecorder.onstop =
        buildRecordedVideo

    state.mediaRecorder.start(1000)
    state.isRecording = true

    const recordButton =
        document.getElementById(
            'btnRecord'
        )

    recordButton.textContent =
        'Oprește'

    recordButton.style.background =
        '#8f3720'

    document.getElementById(
        'btnCapture'
    ).disabled = true

    document.getElementById(
        'btnFlip'
    ).disabled = true

    document.getElementById(
        'message'
    ).textContent =
        'Se înregistrează...'
}

function createNormalizedFrontVideoStream() {
    const viewfinder =
        document.getElementById(
            'viewfinder'
        )

    if (
        !viewfinder ||
        !viewfinder.videoWidth ||
        !viewfinder.videoHeight ||
        typeof HTMLCanvasElement ===
            'undefined'
    ) {
        return null
    }

    frontCanvas =
        document.createElement(
            'canvas'
        )

    frontCanvas.width =
        viewfinder.videoWidth

    frontCanvas.height =
        viewfinder.videoHeight

    const ctx =
        frontCanvas.getContext(
            '2d',
            {
                alpha: false
            }
        )

    if (
        !ctx ||
        typeof frontCanvas.captureStream !==
            'function'
    ) {
        frontCanvas = null
        return null
    }

    const drawFrame = () => {
        if (!frontCanvas || !ctx) {
            return
        }

        ctx.save()

        // Oglindim exact o dată, identic cu fotografia frontală stabilă.
        ctx.translate(
            frontCanvas.width,
            0
        )

        ctx.scale(-1, 1)

        ctx.drawImage(
            viewfinder,
            0,
            0,
            frontCanvas.width,
            frontCanvas.height
        )

        ctx.restore()

        frontCanvasAnimationId =
            requestAnimationFrame(
                drawFrame
            )
    }

    drawFrame()

    frontCanvasStream =
        frontCanvas.captureStream(30)

    frontCanvasVideoTrack =
        frontCanvasStream
            .getVideoTracks()[0] ||
        null

    const combinedStream =
        new MediaStream()

    if (frontCanvasVideoTrack) {
        combinedStream.addTrack(
            frontCanvasVideoTrack
        )
    }

    // Audio-ul rămâne direct din stream-ul original al camerei.
    state.stream
        .getAudioTracks()
        .forEach(
            track =>
                combinedStream.addTrack(
                    track
                )
        )

    return combinedStream
}

function stopFrontCanvasRecording() {
    if (
        frontCanvasAnimationId !==
        null
    ) {
        cancelAnimationFrame(
            frontCanvasAnimationId
        )

        frontCanvasAnimationId =
            null
    }

    if (frontCanvasStream) {
        frontCanvasStream
            .getVideoTracks()
            .forEach(
                track => track.stop()
            )
    }

    frontCanvasVideoTrack = null
    frontCanvasStream = null
    frontCanvas = null
}

export function stopRecording() {
    if (
        !state.mediaRecorder ||
        state.mediaRecorder.state ===
            'inactive'
    ) {
        state.isRecording = false
        stopFrontCanvasRecording()
        stopCamera()
        resetRecordingButtons()
        return
    }

    state.isRecording = false
    state.mediaRecorder.stop()
    resetRecordingButtons()
}

export function stopRecordingForBackground() {
    if (!state.isRecording) {
        stopFrontCanvasRecording()
        stopCamera()
        return
    }

    try {
        if (
            state.mediaRecorder &&
            state.mediaRecorder.state !==
                'inactive'
        ) {
            state.mediaRecorder.stop()
        }
    } finally {
        state.isRecording = false
        stopFrontCanvasRecording()

        // Oprim imediat hardware-ul când pagina ajunge în background.
        stopCamera()
        resetRecordingButtons()
    }
}

function resetRecordingButtons() {
    const recordButton =
        document.getElementById(
            'btnRecord'
        )

    if (recordButton) {
        recordButton.textContent =
            'Video'

        recordButton.style.background =
            ''
    }

    const captureButton =
        document.getElementById(
            'btnCapture'
        )

    const flipButton =
        document.getElementById(
            'btnFlip'
        )

    if (captureButton) {
        captureButton.disabled =
            false
    }

    if (flipButton) {
        flipButton.disabled =
            false
    }
}

function buildRecordedVideo() {
    stopFrontCanvasRecording()

    const recorderMimeType =
        state.mediaRecorder?.mimeType ||
        state.recordedChunks[0]?.type ||
        'video/webm'

    const fileMimeType =
        recorderMimeType.split(';')[0]

    const extension =
        fileMimeType === 'video/mp4'
            ? 'mp4'
            : 'webm'

    const blob =
        new Blob(
            state.recordedChunks,
            { type: fileMimeType }
        )

    if (blob.size === 0) {
        stopCamera()

        document.getElementById(
            'message'
        ).textContent =
            'Înregistrarea nu conține date. Încearcă din nou.'

        return
    }

    state.capturedFile =
        new File(
            [blob],
            `video.${extension}`,
            { type: fileMimeType }
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

    preview.style.display =
        'none'

    preview.src = ''

    previewVideo.src =
        URL.createObjectURL(blob)

    previewVideo.style.display =
        'block'

    viewfinder.style.display =
        'none'

    document.body.classList.add(
        'capture-ready'
    )

    stopCamera()

    document.getElementById(
        'message'
    ).textContent =
        'Videoclipul este gata. Îl poți trimite sau reface.'
}
