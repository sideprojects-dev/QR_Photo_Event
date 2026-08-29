let stream = null
let facingMode = "environment"  // start with back camera
let mediaRecorder = null
let recordedChunks = []
let capturedFile = null
let isRecording = false
let recordingStartTime = null

// Diagnostic temporar: scrie într-un panou vizibil pe pagină, ca să putem
// citi ce se întâmplă direct de pe telefonul unde apare problema,
// fără console de la distanță.
function debugLog(msg) {
    const el = document.getElementById('debugLog')
    const time = new Date().toLocaleTimeString('ro-RO', { hour12: false })
    const line = `[${time}] ${msg}`
    console.log(line)
    if (el) {
        el.textContent += line + '\n'
        el.scrollTop = el.scrollHeight
    }
}

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

        const videoTrack = stream.getVideoTracks()[0]
        debugLog('Camera pornită. Setări reale: ' + JSON.stringify(videoTrack.getSettings()))

        // Semnalele astea ne spun dacă sistemul de operare oprește
        // alimentarea cu cadre video (de obicei motiv termic/resurse),
        // și exact la câte secunde de la începutul înregistrării.
        videoTrack.onmute = () => debugLog('⚠️ VIDEO TRACK MUTED (t=' + secondsSinceRecordingStart() + 's)')
        videoTrack.onunmute = () => debugLog('video track unmuted (t=' + secondsSinceRecordingStart() + 's)')
        videoTrack.onended = () => debugLog('⚠️ VIDEO TRACK ENDED (t=' + secondsSinceRecordingStart() + 's)')
    } catch (err) {
        document.getElementById('message').textContent = 'Nu am putut accesa camera: ' + err.message
        debugLog('Eroare getUserMedia: ' + err.message)
    }
}

function secondsSinceRecordingStart() {
    if (!recordingStartTime) return 'n/a'
    return ((performance.now() - recordingStartTime) / 1000).toFixed(1)
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

        recordingStartTime = performance.now()
        debugLog('Start înregistrare. mimeType=' + mimeType + ' settings=' + JSON.stringify(stream.getVideoTracks()[0].getSettings()))

        let chunkIndex = 0
        mediaRecorder.ondataavailable = e => {
            chunkIndex++
            debugLog(`chunk #${chunkIndex} @ t=${secondsSinceRecordingStart()}s, size=${e.data.size} bytes`)
            if (e.data.size > 0) recordedChunks.push(e.data)
        }

        // Handler care lipsea complet înainte: dacă encoder-ul intern
        // eșuează, browserul emite un eveniment 'error' pe care nu-l
        // vedeam niciodată — recorder-ul pur și simplu "îngheța" silențios.
        mediaRecorder.onerror = (event) => {
            debugLog('❌ MEDIARECORDER ERROR: ' + (event.error ? `${event.error.name} - ${event.error.message}` : JSON.stringify(event)))
        }

        mediaRecorder.onstop = () => {
            debugLog('Stop înregistrare. Total chunk-uri: ' + chunkIndex + ', durată: ' + secondsSinceRecordingStart() + 's')

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

        // timeslice de 1000ms: primim chunk-uri periodice, nu doar la stop,
        // ca să vedem exact la ce secundă se oprește fluxul de date
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