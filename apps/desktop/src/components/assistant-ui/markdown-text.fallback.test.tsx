import type * as StreamdownModule from '@assistant-ui/react-streamdown'
import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@assistant-ui/react-streamdown', async () => {
  const actual = await vi.importActual<typeof StreamdownModule>('@assistant-ui/react-streamdown')

  return {
    ...actual,
    StreamdownTextPrimitive: () => {
      throw new Error('synthetic markdown renderer failure')
    }
  }
})

import { MarkdownTextContent } from './markdown-text'

describe('markdown renderer fallback', () => {
  beforeEach(() => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined)
  })

  it('keeps Markdown structure when the streaming renderer fails', async () => {
    const { container } = render(
      <MarkdownTextContent
        isRunning={false}
        text={'# Fallback heading\n\nA **formatted** paragraph with [Docs](https://example.com) and $x^2$.\n\n- One\n- Two'}
      />
    )

    expect(screen.getByRole('heading', { name: 'Fallback heading' })).toBeTruthy()
    expect(screen.getByText('formatted')).toBeTruthy()
    expect(screen.getByRole('list')).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Docs' }).getAttribute('href')).toBe('https://example.com/')
    await waitFor(() => expect(container.querySelector('.katex')).not.toBeNull())
    expect(screen.queryByText('**formatted**')).toBeNull()
  })
})
