import assert from 'node:assert/strict'
import test from 'node:test'

import {
    clearPreviewObjectUrl,
    replacePreviewObjectUrl
} from '../static/js/preview_urls.js'

test('preview URLs are revoked when replaced or cleared', () => {
    const originalUrl = globalThis.URL
    const revoked = []
    let nextId = 1

    globalThis.URL = {
        createObjectURL: () => `blob:test-${nextId++}`,
        revokeObjectURL: url => revoked.push(url)
    }

    try {
        const first = replacePreviewObjectUrl({})
        const second = replacePreviewObjectUrl({})

        assert.equal(first, 'blob:test-1')
        assert.equal(second, 'blob:test-2')
        assert.deepEqual(revoked, ['blob:test-1'])

        clearPreviewObjectUrl()
        clearPreviewObjectUrl()
        assert.deepEqual(revoked, ['blob:test-1', 'blob:test-2'])
    } finally {
        globalThis.URL = originalUrl
    }
})
