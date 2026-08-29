let stream = null
let facingMode = "environment"  // start with back camera
let mediaRecorder = null
let recordedChunks = []
let capturedFile = null
let isRecording = false

// Start camera when page loads
window.onload = () => startCamera()

async function startCamera() {
    // Stop existing stream if any
    if (stream) stream.getTracks().forEach(t => t.stop())

    //modificare rezolutie
    // 1080p, nu 4K: la 4K, encoder-ul hardware de pe telefoane mai slabe
    // se poate bloca după câteva secunde de înregistrare (video îngheață,
    // audio continuă). 1080p e suficient pentru fotografii/video de eveniment
    // și e suportat stabil de imensa majoritate a telefoanelor.
    try {
        stream = await navigator.mediaDevices.getUserMedia({
             video: {
                facingMode: { ideal: facingMode },
                width: { ideal: 1920 },
                height: { ideal: 1080 },
                frameRate: { ideal: 30, max: 30 }
            },
            audio: true
        })
        document.getElementById('viewfinder').srcObject = stream
    } catch (err) {
        document.getElementById('message').textContent = 'Nu am putut accesa camera: ' + err.message
    }
}

function flipCamera() {
    // Toggle between front and back camera
    facingMode = facingMode === "environment" ? "user" : "environment"
    startCamera()
}

function takePhoto() {
    // Draw current video frame onto a canvas, then convert to image
    const video = document.getElementById('viewfinder')
    const canvas = document.createElement('canvas')
    canvas.width = video.videoWidth
    canvas.height = video.videoHeight
    canvas.getContext('2d').drawImage(video, 0, 0)

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

        // Bitrate explicit: fără el, browserul alege un implicit prea mic
        // pe multe telefoane, ceea ce dădea o calitate vizibil sub 1080p.
        const recorderOptions = {
            videoBitsPerSecond: 8000000,
            audioBitsPerSecond: 128000
        }
        if (mimeType) recorderOptions.mimeType = mimeType

        mediaRecorder = new MediaRecorder(stream, recorderOptions)

        mediaRecorder.ondataavailable = e => {
            if (e.data.size > 0) recordedChunks.push(e.data)
        }

        // Dacă encoder-ul intern eșuează, browserul emite un eveniment
        // 'error' — înainte nu era tratat deloc, iar recorder-ul
        // "îngheța" silențios, fără niciun mesaj către utilizator.
        mediaRecorder.onerror = (event) => {
            document.getElementById('message').textContent =
                'Eroare la înregistrare: ' + (event.error?.message || 'eroare necunoscută') + '. Încearcă din nou.'
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

        // timeslice de 1000ms: primim chunk-uri periodice în loc de unul
        // singur la stop, ca să nu pierdem tot clipul dacă ceva eșuează
        mediaRecorder.start(1000)
        isRecording = true
        document.getElementById('btnRecord').textContent = '⏹ Stop'
        document.getElementById('btnRecord').style.background = '#ff6600'

    } else {
        // Stop recording
        mediaRecorder.stop()
        isRecording = false
        document.getElementById('btnRecord').textContent = '⏺ Înregistrează'
        document.getElementById('btnRecord').style.background = 'red'
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