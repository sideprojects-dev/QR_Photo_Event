export function withEventAccess(path) {
    const separator = path.includes('?') ? '&' : '?'
    return `${path}${separator}access=${encodeURIComponent(window.EVENT_ACCESS || '')}`
}
