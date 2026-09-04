import { state } from './state.js?v=5'

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
                MediaRecorder.isTypeSupported(type)
        ) || ''
    )
}

export function toggleVideo() {
    if (!state.isRecording) {
        startRecording()
        return
    }

    stopRecording()
}

function startRecording() {
    if (!state.stream) {
        document.getElementById('message').textContent =
            'Camera nu este disponibilă.'
        return
    }

    state.recordedChunks = []

    const mimeType =
        getSupportedVideoMimeType()

    const recorderOptions = {
        videoBitsPerSecond: 16000000,
        audioBitsPerSecond: 128000
    }

    if (mimeType) {
        recorderOptions.mimeType =
            mimeType
    }

    state.mediaRecorder =
        new MediaRecorder(
            state.stream,
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
        document.getElementById('btnRecord')

    recordButton.textContent = 'Oprește'
    recordButton.style.background =
        '#8f3720'

    document.getElementById('btnCapture').disabled =
        true
    document.getElementById('btnFlip').disabled =
        true

    document.getElementById('message').textContent =
        'Se înregistrează...'
}

function stopRecording() {
    state.mediaRecorder.stop()
    state.isRecording = false

    const recordButton =
        document.getElementById('btnRecord')

    recordButton.textContent = 'Video'
    recordButton.style.background = ''

    document.getElementById('btnCapture').disabled =
        false
    document.getElementById('btnFlip').disabled =
        false
}

function buildRecordedVideo() {
    const recorderMimeType =
        state.mediaRecorder.mimeType ||
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

    state.capturedFile =
        new File(
            [blob],
            `video.${extension}`,
            { type: fileMimeType }
        )

    const viewfinder =
        document.getElementById('viewfinder')
    const preview =
        document.getElementById('preview')
    const previewVideo =
        document.getElementById('previewVideo')

    preview.style.display = 'none'
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

    document.getElementById(
        'message'
    ).textContent =
        'Videoclipul este gata. Îl poți trimite sau reface.'
}
