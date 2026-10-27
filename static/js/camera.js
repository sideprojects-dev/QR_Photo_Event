import { state } from './state.js?v=6'

let cameraGeneration = 0
let pendingStream = null
let pendingFrame = null

function waitForFirstFrame(video) {
    let finish
    const promise = new Promise(resolve => {
        let settled = false
        let frameRequested = false
        let frameId = null
        let fallbackTimer = null
        const timeout = setTimeout(() => complete(false), 10000)

        function complete(ready) {
            if (settled) return
            settled = true
            clearTimeout(timeout)
            clearTimeout(fallbackTimer)
            video.removeEventListener('loadeddata', check)
            video.removeEventListener('playing', check)
            if (frameId !== null && video.cancelVideoFrameCallback) {
                video.cancelVideoFrameCallback(frameId)
            }
            resolve(ready)
        }

        function check() {
            if (video.readyState < 2 || !video.videoWidth || !video.videoHeight) {
                return
            }
            if (typeof video.requestVideoFrameCallback !== 'function') {
                complete(true)
                return
            }
            if (frameRequested) return
            frameRequested = true
            frameId = video.requestVideoFrameCallback(() => complete(true))
            // loadeddata already guarantees a frame; this covers browsers where
            // requestVideoFrameCallback is exposed but does not fire while hidden.
            fallbackTimer = setTimeout(() => complete(true), 500)
        }

        finish = complete
        video.addEventListener('loadeddata', check)
        video.addEventListener('playing', check)
        check()
    })
    return { promise, cancel: () => finish(false) }
}

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

    if (
        label.includes('tripla') ||
        label.includes('triple') ||
        label.includes('dubla') ||
        label.includes('dual')
    ) {
        return 'composite'
    }

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

export function stopCamera() {
    cameraGeneration += 1
    pendingFrame?.cancel()
    pendingFrame = null
    document.body.classList.remove('camera-ready')

    if (pendingStream) {
        pendingStream.getTracks().forEach(track => track.stop())
        pendingStream = null
    }

    if (state.stream) {
        state.stream
            .getTracks()
            .forEach(track => track.stop())

        state.stream = null
    }

    const viewfinder = document.getElementById('viewfinder')

    if (viewfinder) {
        viewfinder.pause?.()
        viewfinder.srcObject = null
    }
}

export async function startCamera({ withAudio = false } = {}) {
    stopCamera()
    const generation = cameraGeneration

    // Nu repornim camera în background.
    if (document.hidden) {
        return
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

        const stream = await navigator.mediaDevices.getUserMedia({
            video: videoConstraints,
            audio: withAudio
        })

        // Selectorul de fișiere poate readuce pagina în prim-plan în timp
        // ce cererea pentru cameră este încă în curs.
        if (
            generation !== cameraGeneration ||
            state.capturedFile || state.selectedPhotos.length || document.hidden
        ) {
            stream.getTracks().forEach(track => track.stop())
            return
        }

        pendingStream = stream

        const videoTrack = stream.getVideoTracks()[0]
        const settings = videoTrack.getSettings()
        const facingMode = settings.facingMode || state.facingMode

        const viewfinder = document.getElementById('viewfinder')
        viewfinder.srcObject = stream

        // Selfie preview: intentionally mirrored, like a normal front-camera preview.
        viewfinder.classList.toggle(
            'unmirror',
            facingMode === 'user'
        )

        const frameWait = waitForFirstFrame(viewfinder)
        pendingFrame = frameWait
        const playback = Promise.resolve()
            .then(() => {
                if (generation === cameraGeneration) return viewfinder.play?.()
            })
            .then(() => frameWait.promise)
        const hasFrame = await Promise.race([frameWait.promise, playback])
        if (generation !== cameraGeneration) return
        pendingFrame = null
        if (!hasFrame) throw new Error('Camera nu a trimis un cadru video.')

        state.stream = stream
        pendingStream = null
        if (settings.deviceId) state.selectedCameraId = settings.deviceId
        if (settings.facingMode) state.facingMode = settings.facingMode
        document.body.classList.add('camera-ready')

        try {
            const cameras = await getAvailableCameras()
            if (generation === cameraGeneration) {
                state.availableCameras = cameras
                renderCameraSelector()
            }
        } catch {
            if (generation === cameraGeneration) {
                state.availableCameras = []
                renderCameraSelector()
            }
        }
    } catch (err) {
        if (generation !== cameraGeneration) return
        stopCamera()
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
