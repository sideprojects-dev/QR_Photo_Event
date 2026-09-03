let stream = null
let facingMode = "environment"  // start with back camera
let mediaRecorder = null
let recordedChunks = []
let capturedFile = null
let isRecording = false

let selectedCameraId = null
let availableCameras = []

// Start camera when page loads
window.onload = () => startCamera()

async function getAvailableCameras() {
    const devices = await navigator.mediaDevices.enumerateDevices()

    return devices.filter(device => device.kind === 'videoinput')
}

function debugLog(message, data = null) {
    let panel = document.getElementById('debugPanel')

    if (!panel) {
        panel = document.createElement('pre')
        panel.id = 'debugPanel'
        panel.style.whiteSpace = 'pre-wrap'
        panel.style.fontSize = '12px'
        panel.style.background = '#111'
        panel.style.color = '#0f0'
        panel.style.padding = '10px'
        panel.style.marginTop = '10px'
        panel.style.borderRadius = '6px'

        document.body.appendChild(panel)
    }

    const text = data
        ? `${message}\n${JSON.stringify(data, null, 2)}`
        : message

    panel.textContent += text + '\n\n'
}

function getCameraDisplayName(camera, index) {
    const label = camera.label.trim()

    if (!label) {
        return `Camera ${index + 1}`
    }

    const normalizedLabel = label.toLowerCase()

    if (
        normalizedLabel.includes('ultra wide') ||
        normalizedLabel.includes('ultrawide')
    ) {
        return 'Ultra Wide'
    }

    if (
        normalizedLabel.includes('telephoto') ||
        normalizedLabel.includes('tele')
    ) {
        return 'Tele'
    }

    if (
        normalizedLabel.includes('front') ||
        normalizedLabel.includes('facetime')
    ) {
        return 'Front'
    }

    if (
        normalizedLabel.includes('back') ||
        normalizedLabel.includes('rear') ||
        normalizedLabel.includes('wide')
    ) {
        return 'Main'
    }

    return label
}function getCameraType(camera) {
    const label = camera.label
        .toLowerCase()
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .replace(/[\u2010-\u2015\u2212]/g, '-')

    // Front camera
    if (
        label.includes('fata') ||
        label.includes('front') ||
        label.includes('facetime')
    ) {
        return 'front'
    }

    // Logical/composite cameras
    if (
        label.includes('tripla') ||
        label.includes('triple') ||
        label.includes('dubla') ||
        label.includes('dual')
    ) {
        return 'composite'
    }

    // Ultra-wide / 0.5x
    if (
        label.includes('ultra-superangular') ||
        label.includes('ultra superangular') ||
        label.includes('ultra-wide') ||
        label.includes('ultra wide') ||
        label.includes('ultrawide')
    ) {
        return 'ultrawide'
    }

    // Telephoto
    if (
        label.includes('teleobiectiv') ||
        label.includes('telephoto') ||
        label.includes('tele')
    ) {
        return 'tele'
    }

    // Main rear camera
    if (
        label.includes('spate') ||
        label.includes('back') ||
        label.includes('rear')
    ) {
        return 'main'
    }

    return 'unknown'
}


function getCameraDisplayName(type) {
    switch (type) {
        case 'ultrawide':
            return '0.5x'

        case 'main':
            return '1x'

        case 'tele':
            return 'Tele'

        default:
            return 'Camera'
    }
}


function renderCameraSelector() {
    const viewfinder = document.getElementById('viewfinder')

    let selector = document.getElementById('cameraSelector')

    if (!selector) {
        selector = document.createElement('div')
        selector.id = 'cameraSelector'

        selector.style.display = 'flex'
        selector.style.gap = '8px'
        selector.style.justifyContent = 'center'
        selector.style.flexWrap = 'wrap'
        selector.style.margin = '10px 0'

        viewfinder.insertAdjacentElement('afterend', selector)
    }

    selector.innerHTML = ''

    // Front camera is controlled through the existing flip button.
    if (facingMode === 'user') {
        selector.style.display = 'none'
        return
    }

    console.log(
    'Camere disponibile:',
    availableCameras.map(camera => ({
        label: camera.label,
        type: getCameraType(camera),
        deviceId: camera.deviceId
    }))
)

    debugLog(
    'Camere disponibile:',
    availableCameras.map(camera => ({
        label: camera.label,
        type: getCameraType(camera),
        deviceId: camera.deviceId
    }))
)

    const selectableCameras = availableCameras
        .map(camera => ({
            camera,
            type: getCameraType(camera)
        }))
        .filter(item =>
            item.type === 'ultrawide' ||
            item.type === 'main' ||
            item.type === 'tele'
        )

    if (selectableCameras.length <= 1) {
        selector.style.display = 'none'
        return
    }

    selector.style.display = 'flex'

    selectableCameras.forEach(({ camera, type }) => {
        const button = document.createElement('button')

        button.type = 'button'
        button.textContent = getCameraDisplayName(type)

        const isSelected = camera.deviceId === selectedCameraId

        button.style.fontWeight = isSelected ? 'bold' : 'normal'
        button.style.opacity = isSelected ? '1' : '0.7'

        button.addEventListener('click', () => {
            selectCamera(camera.deviceId)
        })

        selector.appendChild(button)
    })
}


async function selectCamera(deviceId) {
    if (isRecording) {
        document.getElementById('message').textContent =
            'Oprește înregistrarea înainte să schimbi camera.'
        return
    }

    const selectedCamera = availableCameras.find(
    camera => camera.deviceId === deviceId
)

debugLog('Camera selectată:', {
    label: selectedCamera?.label,
    deviceId: selectedCamera?.deviceId
})

    await startCamera()
}

async function startCamera() {
    if (stream) {
        stream.getTracks().forEach(track => track.stop())
    }

    try {
        const videoConstraints = {
            width: { ideal: 1920 },
            height: { ideal: 1080 },
            frameRate: { ideal: 30, max: 30 }
        }

        if (selectedCameraId) {
            videoConstraints.deviceId = {
                exact: selectedCameraId
            }
        } else {
            videoConstraints.facingMode = {
                ideal: facingMode
            }
        }

        stream = await navigator.mediaDevices.getUserMedia({
            video: videoConstraints,
            audio: true
        })

        const videoTrack = stream.getVideoTracks()[0]
        const settings = videoTrack.getSettings()

        if (settings.deviceId) {
            selectedCameraId = settings.deviceId
        }

        if (settings.facingMode) {
            facingMode = settings.facingMode
        }

        const viewfinder = document.getElementById('viewfinder')
        viewfinder.srcObject = stream

        viewfinder.classList.toggle(
            'unmirror',
            facingMode === 'user'
        )

        availableCameras = await getAvailableCameras()
        renderCameraSelector()

    } catch (err) {
        document.getElementById('message').textContent =
            'Nu am putut accesa camera: ' + err.message
    }
}

function flipCamera() {
    // Toggle between front and back camera
    if (isRecording) {
        document.getElementById('message').textContent =
            'Oprește înregistrarea înainte să schimbi camera.'
        return
    }

    facingMode = 
        facingMode === 'environment' 
            ? 'user' 
            : 'environment'

    selectedCameraId = null  // Reset selected camera to allow facingMode to take effect

    startCamera()
}

function takePhoto() {
    // Draw current video frame onto a canvas, then convert to image
    const video = document.getElementById('viewfinder')
    const canvas = document.createElement('canvas')
    canvas.width = video.videoWidth
    canvas.height = video.videoHeight
    const ctx = canvas.getContext('2d')

    const shouldFlip = facingMode === 'user'

    // Camera frontala este afisata si salvata in modul in modul oglindit
    // indiferent de platforma

    if (shouldFlip) {
        ctx.translate(canvas.width, 0)
        ctx.scale(-1, 1)
    }

    ctx.drawImage(video, 0, 0)

    canvas.toBlob(blob => {
        capturedFile = new File([blob], 'photo.jpg', { type: 'image/jpeg' })

        // Show preview
        const preview = document.getElementById('preview')
        preview.src = URL.createObjectURL(blob)
        preview.style.display = 'block'
        document.getElementById('previewVideo').style.display = 'none'
        document.getElementById('btnSend').style.display = 'inline-block'
    }, 'image/jpeg', 0.95)
}

//incarcam mp4, iar daca telefonul/browser ul nu il suporta, folosim WebM
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

async function toggleVideo() {
    if (!isRecording) {
        // Start recording
        recordedChunks = []

        const mimeType = getSupportedVideoMimeType()

        // Bitrate explicit: fara el, browserul alege un implicit prea mic
        // pe multe telefoane, ceea ce dadea o calitate vizibil sub 1080pgit
        const recorderOptions = {
            videoBitsPerSecond: 8000000,
            audioBitsPerSecond: 128000
        }
        if (mimeType) recorderOptions.mimeType = mimeType

        mediaRecorder = new MediaRecorder(stream, recorderOptions)

        mediaRecorder.onerror = e => {
            console.error('MediaRecorder error:', e.error)

            document.getElementById('message').textContent = 
            'A apărut o eroare la înregistrarea video: ' + e.error.message
        }

        mediaRecorder.ondataavailable = e => {
            if (e.data.size > 0) recordedChunks.push(e.data)
        }

        mediaRecorder.onstop = () => {
            const recorderMimeType = mediaRecorder.mimeType || recordedChunks[0]?.type || 'video/webm'

            const fileMimeType = recorderMimeType.split(';')[0]

            const extension = fileMimeType === 'video/mp4' ? 'mp4' : 'webm'

            const blob = new Blob(recordedChunks, { type: fileMimeType })

            capturedFile = new File(
                [blob],
                `video.${extension}`,
                { type: fileMimeType }
            )

            // Show video preview
            const previewVideo = document.getElementById('previewVideo')
            previewVideo.src = URL.createObjectURL(blob)
            previewVideo.style.display = 'block'
            document.getElementById('preview').style.display = 'none'
            document.getElementById('btnSend').style.display = 'inline-block'
        }

        mediaRecorder.start(1000)  // collect data in 1-second chunks
        isRecording = true
        document.getElementById('btnRecord').textContent = 'Oprește'
        document.getElementById('btnRecord').style.background = '#8f3720'

    } else {
        // Stop recording
        mediaRecorder.stop()
        isRecording = false
        document.getElementById('btnRecord').textContent = 'Video'
        document.getElementById('btnRecord').style.background = ''
    }
}

async function sendFile() {
    if (!capturedFile) return

    document.getElementById('message').textContent = 'Se trimite...'
    document.getElementById('btnSend').disabled = true

    const formData = new FormData()
    formData.append('file', capturedFile)

    try {
        const response = await fetch(`/upload/${window.EVENT_SLUG || 'default'}`, {
            method: 'POST',
            body: formData
        })
        const data = await response.json()
        document.getElementById('message').textContent = data.mesaj

        // Reset everything so user can take another photo/video
        capturedFile = null
        // Re-enable send button for next upload
        document.getElementById('btnSend').disabled = false
        document.getElementById('btnSend').style.display = 'none'
        document.getElementById('preview').style.display = 'none'
        document.getElementById('previewVideo').style.display = 'none'
        document.getElementById('previewVideo').src = ''
        document.getElementById('preview').src = ''

        // Restart camera stream
        startCamera()
    } catch (err) {
        document.getElementById('message').textContent = 'Eroare: ' + err.message
        document.getElementById('btnSend').disabled = false
    }
}