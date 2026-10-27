let currentPreviewUrl = null

export function replacePreviewObjectUrl(blob) {
    clearPreviewObjectUrl()
    currentPreviewUrl = URL.createObjectURL(blob)
    return currentPreviewUrl
}

export function clearPreviewObjectUrl() {
    if (!currentPreviewUrl) {
        return
    }

    URL.revokeObjectURL(currentPreviewUrl)
    currentPreviewUrl = null
}
