export function createAdminMediaManager({ document, window, fetcher, refreshStats }) {
  const el = id => document.getElementById(id)
  const pageSize = 30
  let current = null
  let items = []
  let selected = new Map()
  let offset = 0
  let hasMore = false
  let loading = false
  let deleting = false
  let version = 0

  function message(text) { el('adminMediaMessage').textContent = text }
  function headers(password) { return { 'x-admin-password': password } }
  function mediaUrl(item, suffix = '') {
    return `/media/${encodeURIComponent(item.id)}${suffix}?access=${encodeURIComponent(current.access)}`
  }
  function selectionCount() {
    el('adminMediaSelectedCount').textContent = `${selected.size} materiale selectate`
    el('adminMediaDeleteSelected').disabled = deleting || selected.size === 0
  }
  function detail(text) {
    const paragraph = document.createElement('p')
    paragraph.textContent = text
    return paragraph
  }
  function formatSize(size) {
    if (size == null) return null
    const number = Number(size)
    if (!Number.isFinite(number) || number < 0) return null
    if (number >= 1024 * 1024) return `${(number / (1024 * 1024)).toLocaleString('ro-RO', { maximumFractionDigits: 1 })} MB`
    if (number >= 1024) return `${(number / 1024).toLocaleString('ro-RO', { maximumFractionDigits: 1 })} KB`
    return `${number} B`
  }
  function formatDate(value) {
    if (!value) return null
    const date = new Date(value)
    return Number.isNaN(date.getTime()) ? null : date.toLocaleString('ro-RO')
  }
  function render() {
    const grid = el('adminMediaGrid')
    grid.replaceChildren()
    for (const item of items) {
      const card = document.createElement('div')
      card.className = `admin-media-card${selected.has(item.id) ? ' is-selected' : ''}`
      const isVideo = item.content_type?.startsWith('video/')
      const preview = document.createElement('button')
      preview.type = 'button'
      preview.className = 'admin-media-thumb'
      preview.setAttribute('aria-label', `Previzualizează ${isVideo ? 'videoclipul' : 'fotografia'}`)
      if (isVideo) {
        const icon = document.createElement('span')
        icon.textContent = '▶'
        preview.appendChild(icon)
      } else {
        const image = document.createElement('img')
        image.src = mediaUrl(item, '/thumbnail')
        image.alt = 'Miniatură fotografie'
        image.loading = 'lazy'
        preview.appendChild(image)
      }
      preview.addEventListener('click', () => openPreview(item))
      card.appendChild(preview)

      const label = document.createElement('label')
      const checkbox = document.createElement('input')
      checkbox.type = 'checkbox'
      checkbox.checked = selected.has(item.id)
      checkbox.disabled = deleting
      checkbox.addEventListener('change', () => {
        if (deleting) return
        if (checkbox.checked) selected.set(item.id, item)
        else selected.delete(item.id)
        card.classList.toggle('is-selected', checkbox.checked)
        selectionCount()
      })
      label.appendChild(checkbox)
      label.appendChild(document.createTextNode('Selectează'))
      card.appendChild(label)
      card.appendChild(detail(`Tip: ${isVideo ? 'Videoclip' : 'Fotografie'}`))
      const date = formatDate(item.created_at)
      if (date) card.appendChild(detail(`Încărcat: ${date}`))
      const size = formatSize(item.size_bytes)
      if (size) card.appendChild(detail(`Dimensiune: ${size}`))
      card.appendChild(detail(`Eveniment: ${current.name}`))

      const download = document.createElement('a')
      download.className = 'small-btn admin-media-download'
      download.href = mediaUrl(item, '/download')
      download.textContent = 'Descarcă'
      card.appendChild(download)
      const remove = document.createElement('button')
      remove.type = 'button'
      remove.className = 'small-btn admin-media-delete'
      remove.textContent = 'Șterge'
      remove.disabled = deleting
      remove.addEventListener('click', () => deleteItems([item]))
      card.appendChild(remove)
      grid.appendChild(card)
    }
    el('adminMediaMore').hidden = !hasMore
    el('adminMediaMore').disabled = loading || deleting
    selectionCount()
  }

  async function load(reset = false) {
    if (!current || loading || deleting) return
    if (reset) {
      offset = 0
      hasMore = false
      items = []
      render()
    }
    loading = true
    const requestVersion = version
    const active = current
    message('Se încarcă materialele...')
    el('adminMediaMore').disabled = true
    try {
      const params = new URLSearchParams({
        kind: el('adminMediaKind').value,
        sort: el('adminMediaSort').value,
        limit: String(pageSize), offset: String(offset)
      })
      const response = await fetcher(
        `/api/admin/events/${encodeURIComponent(active.slug)}/media?${params}`,
        { headers: headers(active.password) }
      )
      if (!response.ok) throw new Error('Materialele nu au putut fi încărcate.')
      const data = await response.json()
      if (requestVersion !== version) return
      items.push(...data.items)
      offset = data.pagination.next_offset ?? offset + data.items.length
      hasMore = data.pagination.has_more
      el('adminMediaEventName').textContent = data.event.name
      message(items.length ? '' : 'Acest eveniment nu are materiale pentru filtrul ales.')
      render()
    } catch (error) {
      if (requestVersion === version) message(error.message)
    } finally {
      if (requestVersion === version) {
        loading = false
        el('adminMediaMore').disabled = deleting
      }
    }
  }

  function reload() {
    version += 1
    loading = false
    return load(true)
  }

  function closePreview() {
    const modal = el('adminMediaModal')
    const image = el('adminMediaModalImage')
    const video = el('adminMediaModalVideo')
    video.pause()
    video.removeAttribute('src')
    video.load()
    image.removeAttribute('src')
    image.hidden = true
    video.hidden = true
    modal.classList.remove('is-open')
    modal.setAttribute('aria-hidden', 'true')
  }
  function openPreview(item) {
    if (!current) return
    closePreview()
    const isVideo = item.content_type?.startsWith('video/')
    const target = el(isVideo ? 'adminMediaModalVideo' : 'adminMediaModalImage')
    target.hidden = false
    target.src = mediaUrl(item, isVideo ? '' : '/preview')
    if (isVideo) target.load()
    el('adminMediaModalMessage').textContent = ''
    target.onerror = () => { el('adminMediaModalMessage').textContent = 'Previzualizarea nu a putut fi încărcată.' }
    el('adminMediaModal').classList.add('is-open')
    el('adminMediaModal').setAttribute('aria-hidden', 'false')
  }

  async function deleteItems(toDelete) {
    if (deleting || !current || !toDelete.length) return
    const amount = toDelete.length
    if (!window.confirm(
      `Ștergi ${amount} ${amount === 1 ? 'material' : 'materiale'}? Vor dispărea din galerii. Fișierele sunt mutate în Coșul Google Drive, de unde pot fi recuperate în cel mult 30 de zile; eliminarea înregistrărilor din Supabase este definitivă.`
    )) return
    deleting = true
    version += 1
    loading = false
    const active = current
    const results = []
    el('adminMediaDeleteSelected').disabled = true
    el('adminMediaMore').disabled = true
    el('adminMediaKind').disabled = true
    el('adminMediaSort').disabled = true
    el('adminMediaClose').disabled = true
    document.querySelectorAll('.admin-media-delete, .admin-media-card input').forEach(control => {
      control.disabled = true
    })
    for (const [index, item] of toDelete.entries()) {
      message(`Se șterge materialul ${index + 1} din ${amount}...`)
      try {
        const response = await fetcher(
          `/api/admin/events/${encodeURIComponent(active.slug)}/media/${encodeURIComponent(item.id)}`,
          { method: 'DELETE', headers: headers(active.password) }
        )
        const data = await response.json().catch(() => ({}))
        if (response.ok) {
          selected.delete(item.id)
          results.push(`${index + 1}. ${item.file_name || item.id}: ${data.status === 'already_deleted' ? 'deja eliminat' : 'șters'}`)
        } else {
          results.push(`${index + 1}. ${item.file_name || item.id}: ${typeof data.detail === 'string' ? data.detail : 'Ștergerea a eșuat.'}`)
        }
      } catch (error) {
        results.push(`${index + 1}. ${item.file_name || item.id}: Cererea a eșuat.`)
      }
      el('adminMediaResults').textContent = results.join('\n')
    }
    deleting = false
    el('adminMediaKind').disabled = false
    el('adminMediaSort').disabled = false
    el('adminMediaClose').disabled = false
    await refreshStats()
    if (current === active) await reload()
    message(`Procesate ${amount} ${amount === 1 ? 'material' : 'materiale'}. Vezi rezultatul fiecăruia mai jos.`)
    selectionCount()
  }

  async function open(slug, name, guestUrl, password) {
    if (deleting) return
    close()
    const access = new URL(guestUrl, window.location.origin).searchParams.get('access')
    current = { slug, name, access, password }
    el('adminMediaPanel').hidden = false
    el('adminMediaEventName').textContent = name
    el('adminMediaResults').textContent = ''
    el('adminMediaKind').value = 'all'
    el('adminMediaSort').value = 'newest'
    if (!access) {
      message('Linkul de acces al evenimentului lipsește. Reîncarcă lista de evenimente.')
      return
    }
    await reload()
    el('adminMediaPanel').scrollIntoView?.({ behavior: 'smooth', block: 'start' })
  }
  function close() {
    if (deleting) {
      message('Așteaptă finalizarea ștergerii înainte de a închide galeria.')
      return false
    }
    version += 1
    closePreview()
    current = null
    items = []
    selected.clear()
    loading = false
    el('adminMediaPanel').hidden = true
    selectionCount()
    return true
  }

  el('adminMediaKind').addEventListener('change', reload)
  el('adminMediaSort').addEventListener('change', reload)
  el('adminMediaMore').addEventListener('click', () => load(false))
  el('adminMediaSelectShown').addEventListener('click', () => {
    if (deleting) return
    items.forEach(item => selected.set(item.id, item))
    render()
  })
  el('adminMediaClearSelection').addEventListener('click', () => {
    if (deleting) return
    selected.clear()
    render()
  })
  el('adminMediaDeleteSelected').addEventListener('click', () => deleteItems([...selected.values()]))
  el('adminMediaClose').addEventListener('click', close)
  el('adminMediaModalClose').addEventListener('click', closePreview)
  el('adminMediaModal').addEventListener('click', event => {
    if (event.target === el('adminMediaModal')) closePreview()
  })
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') closePreview()
  })
  selectionCount()
  return { open, close, load, reload, deleteItems }
}
