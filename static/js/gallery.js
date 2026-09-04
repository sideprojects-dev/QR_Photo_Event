import { state } from './state.js?v=4'

export async function loadGallery(reset = false) {
    const eventSlug = window.EVENT_SLUG

    if (!eventSlug || state.galleryLoading) {
        return
    }

    const grid = document.getElementById('galleryGrid')
    const emptyState = document.getElementById('galleryEmpty')
    const message = document.getElementById('galleryMessage')
    const loadMoreButton = document.getElementById('btnLoadMore')

    if (!grid || !emptyState || !message || !loadMoreButton) {
        return
    }

    if (reset) {
        state.galleryOffset = 0
        state.galleryHasMore = false
        grid.innerHTML = ''
    }

    state.galleryLoading = true
    loadMoreButton.disabled = true
    message.textContent = 'Se încarcă galeria...'

    try {
        const response = await fetch(
            `/api/events/${encodeURIComponent(eventSlug)}/media?limit=${state.galleryPageSize}&offset=${state.galleryOffset}`
        )

        const data = await response.json()

        if (!response.ok) {
            throw new Error(
                data.detail ||
                data.error ||
                'Nu am putut încărca galeria.'
            )
        }

        const items = Array.isArray(data.items) ? data.items : []
        renderGalleryItems(items)

        state.galleryHasMore = Boolean(data.pagination?.has_more)
        state.galleryOffset =
            data.pagination?.next_offset ??
            (state.galleryOffset + items.length)

        emptyState.style.display =
            grid.children.length === 0 ? 'block' : 'none'

        loadMoreButton.style.display =
            state.galleryHasMore ? 'block' : 'none'

        message.textContent = ''
    } catch (err) {
        message.textContent =
            'Nu am putut încărca galeria: ' + err.message
        loadMoreButton.style.display = 'none'
    } finally {
        state.galleryLoading = false
        loadMoreButton.disabled = false
    }
}

function renderGalleryItems(items) {
    const grid = document.getElementById('galleryGrid')

    if (!grid) {
        return
    }

    items.forEach(item => {
        grid.appendChild(createGalleryItem(item))
    })
}

function createGalleryItem(item) {
    const button = document.createElement('button')
    button.type = 'button'
    button.className = 'gallery-item'

    const isVideo = item.content_type?.startsWith('video/')

    if (isVideo) {
        const videoPlaceholder = document.createElement('div')
        videoPlaceholder.className = 'gallery-video-placeholder'

        const playIcon = document.createElement('span')
        playIcon.className = 'gallery-play-icon'
        playIcon.textContent = '▶'

        const label = document.createElement('span')
        label.className = 'gallery-video-label'
        label.textContent = 'Video'

        videoPlaceholder.appendChild(playIcon)
        videoPlaceholder.appendChild(label)
        button.appendChild(videoPlaceholder)
    } else {
        const image = document.createElement('img')
        image.src = `/media/${encodeURIComponent(item.id)}/thumbnail`
        image.alt = 'Fotografie din galerie'
        image.loading = 'lazy'
        button.appendChild(image)
    }

    button.addEventListener('click', () => openGalleryModal(item))
    return button
}

export function openGalleryModal(item) {
    const modal = document.getElementById('galleryModal')
    const image = document.getElementById('galleryModalImage')
    const video = document.getElementById('galleryModalVideo')
    const downloadLink = document.getElementById('galleryDownload')

    if (!modal || !image || !video) {
        return
    }

    const originalUrl = `/media/${encodeURIComponent(item.id)}`
    const previewUrl = `/media/${encodeURIComponent(item.id)}/preview`
    const downloadUrl = `/media/${encodeURIComponent(item.id)}/download`
    const isVideo = item.content_type?.startsWith('video/')

    if (downloadLink) {
        downloadLink.href = downloadUrl
    }

    image.style.display = isVideo ? 'none' : 'block'
    video.style.display = isVideo ? 'block' : 'none'

    if (isVideo) {
        image.src = ''
        video.src = originalUrl
        video.load()
    } else {
        video.pause()
        video.removeAttribute('src')
        video.load()
        image.src = previewUrl
    }

    modal.classList.add('is-open')
    modal.setAttribute('aria-hidden', 'false')
    document.body.classList.add('modal-open')
}

export function closeGalleryModal() {
    const modal = document.getElementById('galleryModal')
    const image = document.getElementById('galleryModalImage')
    const video = document.getElementById('galleryModalVideo')
    const downloadLink = document.getElementById('galleryDownload')

    if (!modal || !image || !video) {
        return
    }

    video.pause()
    video.removeAttribute('src')
    video.load()
    image.src = ''

    modal.classList.remove('is-open')
    modal.setAttribute('aria-hidden', 'true')
    document.body.classList.remove('modal-open')
}

export async function loadMoreGallery() {
    if (!state.galleryHasMore) {
        return
    }

    await loadGallery(false)
}

export function bindGalleryModalEvents() {
    const modal = document.getElementById('galleryModal')

    modal?.addEventListener('click', event => {
        if (event.target === modal) {
            closeGalleryModal()
        }
    })

    document.addEventListener('keydown', event => {
        if (event.key === 'Escape') {
            closeGalleryModal()
        }
    })
}
