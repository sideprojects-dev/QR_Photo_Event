import { state } from './state.js?v=6'
import { withEventAccess } from './guest_access.js?v=1'

let loadedItems = []
let currentModalItem = null

export async function loadGallery(
    reset = false
) {
    const eventSlug =
        window.EVENT_SLUG

    if (
        !eventSlug ||
        state.galleryLoading
    ) {
        return
    }

    const grid =
        document.getElementById(
            'galleryGrid'
        )

    const emptyState =
        document.getElementById(
            'galleryEmpty'
        )

    const message =
        document.getElementById(
            'galleryMessage'
        )

    const loadMoreButton =
        document.getElementById(
            'btnLoadMore'
        )

    if (
        !grid ||
        !emptyState ||
        !message ||
        !loadMoreButton
    ) {
        return
    }

    if (reset) {
        state.galleryOffset = 0
        state.galleryHasMore = false
        grid.innerHTML = ''
        loadedItems = []
    }

    state.galleryLoading = true
    loadMoreButton.disabled = true
    message.textContent =
        'Se încarcă galeria...'

    try {
        const response =
            await fetch(
                withEventAccess(`/api/events/${
                    encodeURIComponent(
                        eventSlug
                    )
                }/media?limit=${
                    state.galleryPageSize
                }&offset=${
                    state.galleryOffset
                }`)
            )

        const data =
            await response.json()

        if (!response.ok) {
            throw new Error(
                data.detail ||
                data.error ||
                'Nu am putut încărca galeria.'
            )
        }

        const items =
            Array.isArray(data.items)
                ? data.items
                : []

        renderGalleryItems(items)

        state.galleryHasMore =
            Boolean(
                data.pagination?.has_more
            )

        state.galleryOffset =
            data.pagination?.next_offset ??
            (
                state.galleryOffset +
                items.length
            )

        emptyState.style.display =
            grid.children.length === 0
                ? 'block'
                : 'none'

        loadMoreButton.style.display =
            state.galleryHasMore
                ? 'block'
                : 'none'

        message.textContent = ''

    } catch (err) {
        message.textContent =
            'Nu am putut încărca galeria: ' +
            err.message

        loadMoreButton.style.display =
            'none'

    } finally {
        state.galleryLoading = false
        loadMoreButton.disabled = false
    }
}

function renderGalleryItems(items) {
    const grid =
        document.getElementById(
            'galleryGrid'
        )

    if (!grid) {
        return
    }

    loadedItems.push(...items)
    items.forEach(
        item => {
            grid.appendChild(
                createGalleryItem(item)
            )
        }
    )
}

function createGalleryItem(item) {
    const container =
        document.createElement('div')

    container.className =
        'gallery-item'

    const openButton =
        document.createElement('button')

    openButton.type = 'button'
    openButton.className =
        'gallery-open'

    const isVideo =
        item.content_type?.startsWith(
            'video/'
        )

    if (isVideo) {
        const videoPlaceholder =
            document.createElement('div')

        videoPlaceholder.className =
            'gallery-video-placeholder'

        const playIcon =
            document.createElement('span')

        playIcon.className =
            'gallery-play-icon'

        playIcon.textContent = '▶'

        const label =
            document.createElement('span')

        label.className =
            'gallery-video-label'

        label.textContent = 'Video'

        videoPlaceholder.appendChild(
            playIcon
        )

        videoPlaceholder.appendChild(
            label
        )

        openButton.appendChild(
            videoPlaceholder
        )
    } else {
        const image =
            document.createElement('img')

        image.src =
            withEventAccess(`/media/${
                encodeURIComponent(
                    item.id
                )
            }/thumbnail`)

        image.alt =
            'Fotografie din galerie'

        image.loading = 'lazy'

        openButton.appendChild(image)
    }

    openButton.addEventListener(
        'click',
        () => openGalleryModal(item)
    )

    const downloadLink =
        document.createElement('a')

    downloadLink.className =
        'gallery-item-download'

    downloadLink.href =
        withEventAccess(`/media/${
            encodeURIComponent(
                item.id
            )
        }/download`)

    downloadLink.setAttribute(
        'aria-label',
        isVideo
            ? 'Descarcă videoclipul'
            : 'Descarcă fotografia'
    )

    downloadLink.title =
        'Descarcă'

    downloadLink.textContent = '↓'

    container.appendChild(
        openButton
    )

    container.appendChild(
        downloadLink
    )

    return container
}

export function openGalleryModal(item) {
    currentModalItem = item
    const modal =
        document.getElementById(
            'galleryModal'
        )

    const image =
        document.getElementById(
            'galleryModalImage'
        )

    const video =
        document.getElementById(
            'galleryModalVideo'
        )

    const loading =
        document.getElementById(
            'galleryModalLoading'
        )

    const downloadLink =
        document.getElementById(
            'galleryDownload'
        )

    if (
        !modal ||
        !image ||
        !video
    ) {
        return
    }

    const encodedId =
        encodeURIComponent(item.id)

    const originalUrl =
        withEventAccess(`/media/${encodedId}`)

    const previewUrl =
        withEventAccess(`/media/${encodedId}/preview`)

    const downloadUrl =
        withEventAccess(`/media/${encodedId}/download`)

    const isVideo =
        item.content_type?.startsWith(
            'video/'
        )

    if (downloadLink) {
        downloadLink.href =
            downloadUrl
    }

    if (loading) {
        loading.textContent = 'Se încarcă...'
        loading.style.display =
            'block'
    }

    image.style.display = 'none'
    video.style.display = 'none'
    video.onloadedmetadata = null

    if (isVideo) {
        image.removeAttribute('src')

        video.src =
            originalUrl

        const onVideoReady = () => {
            if (loading) {
                loading.style.display =
                    'none'
            }

            video.style.display =
                'block'
        }

        video.onloadedmetadata = onVideoReady

        video.load()

    } else {
        video.pause()
        video.removeAttribute('src')
        video.load()
        image.removeAttribute('src')

        image.onload = () => {
            if (loading) {
                loading.style.display =
                    'none'
            }

            image.style.display =
                'block'
        }

        image.onerror = () => {
            if (loading) {
                loading.textContent =
                    'Nu am putut încărca fotografia.'
            }
        }

        image.src =
            previewUrl
    }

    modal.classList.add('is-open')
    modal.setAttribute(
        'aria-hidden',
        'false'
    )

    document.body.classList.add(
        'modal-open'
    )
    updateGalleryNavigation()
}

function loadedPhotos() {
    return loadedItems.filter(item =>
        !item.content_type?.startsWith('video/')
    )
}

function updateGalleryNavigation() {
    const previous = document.getElementById('galleryPrevious')
    const next = document.getElementById('galleryNext')
    const photos = loadedPhotos()
    const index = photos.findIndex(item => item.id === currentModalItem?.id)
    const visible = index >= 0 && photos.length > 1
    previous.hidden = !visible
    next.hidden = !visible
    previous.disabled = index <= 0
    next.disabled = index < 0 || index >= photos.length - 1
}

export function navigateGalleryPhoto(direction) {
    if (!document.getElementById('galleryModal').classList.contains('is-open')) {
        return
    }
    const photos = loadedPhotos()
    const index = photos.findIndex(item => item.id === currentModalItem?.id)
    const nextPhoto = photos[index + direction]
    if (index >= 0 && nextPhoto) openGalleryModal(nextPhoto)
}

export function closeGalleryModal() {
    const modal =
        document.getElementById(
            'galleryModal'
        )

    const image =
        document.getElementById(
            'galleryModalImage'
        )

    const video =
        document.getElementById(
            'galleryModalVideo'
        )

    const loading =
        document.getElementById(
            'galleryModalLoading'
        )

    if (
        !modal ||
        !image ||
        !video
    ) {
        return
    }

    video.pause()
    video.onloadedmetadata = null
    video.removeAttribute('src')
    video.load()

    image.removeAttribute('src')
    image.onload = null
    image.onerror = null

    if (loading) {
        loading.textContent =
            'Se încarcă...'

        loading.style.display =
            'block'
    }

    modal.classList.remove(
        'is-open'
    )

    modal.setAttribute(
        'aria-hidden',
        'true'
    )

    document.body.classList.remove(
        'modal-open'
    )
    currentModalItem = null
}

export async function loadMoreGallery() {
    if (!state.galleryHasMore) {
        return
    }

    await loadGallery(false)
}

export function bindGalleryModalEvents() {
    const modal =
        document.getElementById(
            'galleryModal'
        )

    modal?.addEventListener(
        'click',
        event => {
            if (event.target === modal) {
                closeGalleryModal()
            }
        }
    )

    document.getElementById('galleryPrevious')?.addEventListener(
        'click', () => navigateGalleryPhoto(-1)
    )
    document.getElementById('galleryNext')?.addEventListener(
        'click', () => navigateGalleryPhoto(1)
    )

    let touchStart = null
    modal?.addEventListener('touchstart', event => {
        const touch = event.touches[0]
        touchStart = touch ? { x: touch.clientX, y: touch.clientY } : null
    }, { passive: true })
    modal?.addEventListener('touchend', event => {
        if (!touchStart) return
        const touch = event.changedTouches[0]
        if (!touch) return
        const dx = touch.clientX - touchStart.x
        const dy = touch.clientY - touchStart.y
        touchStart = null
        if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy) * 1.4) {
            navigateGalleryPhoto(dx < 0 ? 1 : -1)
        }
    }, { passive: true })

    document.addEventListener(
        'keydown',
        event => {
            if (!modal?.classList.contains('is-open')) return
            if (event.key === 'Escape') {
                closeGalleryModal()
            } else if (event.key === 'ArrowLeft') {
                navigateGalleryPhoto(-1)
            } else if (event.key === 'ArrowRight') {
                navigateGalleryPhoto(1)
            }
        }
    )
}
