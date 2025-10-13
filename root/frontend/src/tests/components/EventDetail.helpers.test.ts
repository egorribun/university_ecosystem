import { describe, expect, it } from 'vitest'
import {
  applyOptimisticFileAction,
  isUploadErrorState,
  type FileOptimisticAction,
  type OptimisticEventFile,
  type UploadState
} from '@/components/EventDetail.helpers'

describe('applyOptimisticFileAction', () => {
  const baseFile: OptimisticEventFile = {
    id: 1,
    event_id: 1,
    file_url: 'https://example.com/file.pdf',
    description: 'file.pdf'
  }

  it('appends new files during optimistic upload', () => {
    const pendingFile: OptimisticEventFile = {
      id: 'pending-1',
      event_id: 1,
      file_url: '',
      description: 'uploading.pdf',
      pending: true
    }

    const action: FileOptimisticAction = { type: 'add', file: pendingFile }

    const result = applyOptimisticFileAction([baseFile], action)

    expect(result).toHaveLength(2)
    expect(result[1]).toMatchObject({ id: 'pending-1', pending: true })
  })

  it('removes files when upload completes', () => {
    const optimisticId = 'pending-2'
    const pending: OptimisticEventFile = {
      id: optimisticId,
      event_id: 7,
      file_url: '',
      description: 'processing.docx',
      pending: true
    }

    const action: FileOptimisticAction = { type: 'remove', id: optimisticId }
    const result = applyOptimisticFileAction([baseFile, pending], action)

    expect(result).toHaveLength(1)
    expect(result[0]).toEqual(baseFile)
  })
})

describe('isUploadErrorState', () => {
  it('narrows upload states to those with an error message', () => {
    const states: UploadState[] = [
      { status: 'idle' },
      { status: 'success' },
      { status: 'error', error: 'failed to upload' }
    ]

    const errors = states.filter(isUploadErrorState)

    expect(errors).toHaveLength(1)
    expect(errors[0].error).toBe('failed to upload')
  })
})
