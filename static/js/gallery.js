import { state } from './state.js?v=5'

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
    }

    state.galleryLoading = true
    loadMoreButton.disabled = true
    message.textContent =
        'Se încarcă galeria...'

    try {
        const response =
            await fetch(
                `/api/events/${
                    encodeURIComponent(
                        eventSlug
                    )
                }/media?limit=${
                    state.galleryPageSize
                }&offset=${
                    state.galleryOffset
                }`
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
            `/media/${
                encodeURIComponent(
                    item.id
                )
            }/thumbnail`

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
        `/media/${
            encodeURIComponent(
                item.id
            )
        }/download`

    downloadLink.setAttribute(
        'aria-label',
        isVideo
            ? 'Descarcă videoclipul'
            : 'Descarcă fotografia'
    )

    downloadLink.title =
        'Descarcă originalul'

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
        `/media/${encodedId}`

    const previewUrl =
        `/media/${encodedId}/preview`

    const downloadUrl =
        `/media/${encodedId}/download`

    const isVideo =
        item.content_type?.startsWith(
            'video/'
        )

    if (downloadLink) {
        downloadLink.href =
            downloadUrl
    }

    if (loading) {
        loading.style.display =
            'block'
    }

    image.style.display = 'none'
    video.style.display = 'none'

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

        video.addEventListener(
            'loadedmetadata',
            onVideoReady,
            { once: true }
        )

        video.load()

    } else {
        video.pause()
        video.removeAttribute('src')
        video.load()

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

    document.addEventListener(
        'keydown',
        event => {
            if (event.key === 'Escape') {
                closeGalleryModal()
            }
        }
    )
}
