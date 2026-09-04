import { state } from './state.js?v=3'

function getSupportedVideoMimeType() {
    const types = [
        'video/mp4;codecs=h264,aac',
        'video/mp4',
        'video/webm;codecs=vp9,opus',
        'video/webm;codecs=vp8,opus',
        'video/webm'
    ]

    return types.find(type => MediaRecorder.isTypeSupported(type)) || ''
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

    const mimeType = getSupportedVideoMimeType()
    const recorderOptions = {
        videoBitsPerSecond: 16000000,
        audioBitsPerSecond: 128000
    }

    if (mimeType) {
        recorderOptions.mimeType = mimeType
    }

    state.mediaRecorder = new MediaRecorder(state.stream, recorderOptions)

    state.mediaRecorder.onerror = event => {
        console.error('MediaRecorder error:', event.error)
        document.getElementById('message').textContent =
            'A apărut o eroare la înregistrarea video: ' +
            (event.error?.message || 'eroare necunoscută')
    }

    state.mediaRecorder.ondataavailable = event => {
        if (event.data.size > 0) {
            state.recordedChunks.push(event.data)
        }
    }

    state.mediaRecorder.onstop = buildRecordedVideo
    state.mediaRecorder.start(1000)

    state.isRecording = true

    const recordButton = document.getElementById('btnRecord')
    recordButton.textContent = 'Oprește'
    recordButton.style.background = '#8f3720'
}

function stopRecording() {
    state.mediaRecorder.stop()
    state.isRecording = false

    const recordButton = document.getElementById('btnRecord')
    recordButton.textContent = 'Video'
    recordButton.style.background = ''
}

function buildRecordedVideo() {
    const recorderMimeType =
        state.mediaRecorder.mimeType ||
        state.recordedChunks[0]?.type ||
        'video/webm'

    const fileMimeType = recorderMimeType.split(';')[0]
    const extension = fileMimeType === 'video/mp4' ? 'mp4' : 'webm'
    const blob = new Blob(state.recordedChunks, { type: fileMimeType })

    state.capturedFile = new File(
        [blob],
        `video.${extension}`,
        { type: fileMimeType }
    )

    const previewVideo = document.getElementById('previewVideo')
    previewVideo.src = URL.createObjectURL(blob)
    previewVideo.style.display = 'block'

    document.getElementById('preview').style.display = 'none'
    document.getElementById('btnSend').style.display = 'inline-block'
}
