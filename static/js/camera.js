import { state } from './state.js?v=5'

export async function getAvailableCameras() {
    const devices = await navigator.mediaDevices.enumerateDevices()
    return devices.filter(device => device.kind === 'videoinput')
}

function normalizeCameraLabel(label) {
    return label
        .toLowerCase()
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .replace(/[\u2010-\u2015\u2212]/g, '-')
}

export function getCameraType(camera) {
    const label = normalizeCameraLabel(camera.label)

    if (
        label.includes('fata') ||
        label.includes('front') ||
        label.includes('facetime') ||
        label.includes('selfie')
    ) {
        return 'front'
    }

    // iOS exposes logical multi-camera devices as well as the physical lenses.
    // Keep them out of the selector so the browser is less likely to switch lenses itself.
    if (
        label.includes('tripla') ||
        label.includes('triple') ||
        label.includes('dubla') ||
        label.includes('dual')
    ) {
        return 'composite'
    }

    // iOS + common Android labels for the ultra-wide / wide-angle physical lens.
    // "wide" alone is included because some Android browsers expose the 0.5x lens
    // simply as "Wide Camera" instead of "Ultra Wide Camera".
    if (
        label.includes('ultra-superangular') ||
        label.includes('ultra superangular') ||
        label.includes('superangular') ||
        label.includes('ultra-wide') ||
        label.includes('ultra wide') ||
        label.includes('ultrawide') ||
        label.includes('super wide') ||
        label.includes('wide angle') ||
        label.includes('wide-angle') ||
        label.includes('grand angle') ||
        label.includes('grand-angle') ||
        /^wide camera\b/.test(label) ||
        /\bwide lens\b/.test(label)
    ) {
        return 'ultrawide'
    }

    if (
        label.includes('teleobiectiv') ||
        label.includes('telephoto') ||
        label.includes('tele') ||
        label.includes('zoom')
    ) {
        return 'tele'
    }

    if (
        label.includes('spate') ||
        label.includes('back') ||
        label.includes('rear') ||
        label.includes('environment')
    ) {
        return 'main'
    }

    return 'unknown'
}

export function getCameraDisplayName(type) {
    switch (type) {
        case 'ultrawide':
            return '0.5×'
        case 'main':
            return '1×'
        case 'tele':
            return '5×'
        default:
            return 'Camera'
    }
}

export function renderCameraSelector() {
    const selector = document.getElementById('cameraSelector')

    if (!selector) {
        return
    }

    selector.innerHTML = ''

    if (state.facingMode === 'user') {
        selector.hidden = true
        return
    }

    const selectableCameras = state.availableCameras
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
        selector.hidden = true
        return
    }

    selector.hidden = false

    selectableCameras.forEach(({ camera, type }) => {
        const button = document.createElement('button')
        const isSelected = camera.deviceId === state.selectedCameraId

        button.type = 'button'
        button.className = `camera-option${isSelected ? ' is-selected' : ''}`
        button.textContent = getCameraDisplayName(type)
        button.addEventListener('click', () => selectCamera(camera.deviceId))

        selector.appendChild(button)
    })
}

export async function selectCamera(deviceId) {
    if (state.isRecording) {
        document.getElementById('message').textContent =
            'Oprește înregistrarea înainte să schimbi camera.'
        return
    }

    if (deviceId === state.selectedCameraId) {
        return
    }

    state.selectedCameraId = deviceId
    await startCamera()
}

export async function startCamera() {
    if (state.stream) {
        state.stream.getTracks().forEach(track => track.stop())
    }

    try {
        const videoConstraints = {
            width: { ideal: 1920 },
            height: { ideal: 1080 },
            frameRate: { ideal: 30, max: 30 }
        }

        if (state.selectedCameraId) {
            videoConstraints.deviceId = { exact: state.selectedCameraId }
        } else {
            videoConstraints.facingMode = { ideal: state.facingMode }
        }

        state.stream = await navigator.mediaDevices.getUserMedia({
            video: videoConstraints,
            audio: true
        })

        const videoTrack = state.stream.getVideoTracks()[0]
        const settings = videoTrack.getSettings()

        if (settings.deviceId) {
            state.selectedCameraId = settings.deviceId
        }

        if (settings.facingMode) {
            state.facingMode = settings.facingMode
        }

        const viewfinder = document.getElementById('viewfinder')
        viewfinder.srcObject = state.stream
        viewfinder.classList.toggle('unmirror', state.facingMode === 'user')

        state.availableCameras = await getAvailableCameras()
        renderCameraSelector()
    } catch (err) {
        document.getElementById('message').textContent =
            'Nu am putut accesa camera: ' + err.message
    }
}

export async function flipCamera() {
    if (state.isRecording) {
        document.getElementById('message').textContent =
            'Oprește înregistrarea înainte să schimbi camera.'
        return
    }

    state.facingMode =
        state.facingMode === 'environment'
            ? 'user'
            : 'environment'

    state.selectedCameraId = null
    await startCamera()
}
