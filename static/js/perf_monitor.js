// Opt-in measurements only. Never include URLs, filenames or access codes.
const enabled = typeof window !== 'undefined' &&
    new URLSearchParams(window.location?.search || '').get('perf') === '1'

export function perfStart() {
    return enabled ? performance.now() : null
}

export function perfRecord(operation, started, outcome = 'ok') {
    if (started === null) return
    try {
        const now = performance.now()
        console.info('qr_photo_perf', JSON.stringify({
            event: 'performance',
            operation,
            outcome,
            at_ms: Math.round(now * 100) / 100,
            elapsed_ms: Math.round((now - started) * 100) / 100
        }))
    } catch {
        // Measurements must not interrupt camera, upload or gallery actions.
    }
}
