let currentPreviewUrl = null
const selectionPreviewUrls = new Set()

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

export function createSelectionPreviewUrl(blob) {
    const url = URL.createObjectURL(blob)
    selectionPreviewUrls.add(url)
    return url
}

export function revokeSelectionPreviewUrl(url) {
    if (url && selectionPreviewUrls.delete(url)) {
        URL.revokeObjectURL(url)
    }
}

export function clearSelectionPreviewUrls() {
    for (const url of selectionPreviewUrls) {
        URL.revokeObjectURL(url)
    }
    selectionPreviewUrls.clear()
}
