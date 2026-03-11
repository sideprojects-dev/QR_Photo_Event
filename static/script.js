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

    try {
        stream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: facingMode },
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
    }, 'image/jpeg', 0.9)
}

function toggleVideo() {
    if (!isRecording) {
        // Start recording
        recordedChunks = []
        mediaRecorder = new MediaRecorder(stream)

        mediaRecorder.ondataavailable = e => {
            if (e.data.size > 0) recordedChunks.push(e.data)
        }

        mediaRecorder.onstop = () => {
            const blob = new Blob(recordedChunks, { type: 'video/mp4' })
            capturedFile = new File([blob], 'video.mp4', { type: 'video/mp4' })

            // Show video preview
            const previewVideo = document.getElementById('previewVideo')
            previewVideo.src = URL.createObjectURL(blob)
            previewVideo.style.display = 'block'
            document.getElementById('preview').style.display = 'none'
            document.getElementById('btnSend').style.display = 'inline-block'
        }

        mediaRecorder.start()
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