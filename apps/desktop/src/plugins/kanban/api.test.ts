/** Throttle contract for board invalidation from live event frames — see
 *  onEventsFrame/invalidateBoardThrottled in api.ts. The server tails
 *  task_events every 300ms, so an active worker produces frames in bursts;
 *  the board query (the full ~0.3–1 MB payload) must refetch at most once
 *  per window (leading + trailing), per-task detail invalidation stays
 *  per-frame, and a disposed plugin must not fire a pending trailing
 *  invalidation. */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { invalidateQueries } = vi.hoisted(() => ({ invalidateQueries: vi.fn() }))

vi.mock('@hermes/plugin-sdk', () => {
  const atom = <T>(initial: T) => {
    let value = initial
    const listeners = new Set<(next: T) => void>()

    return {
      get: () => value,
      listen: (cb: (next: T) => void) => {
        listeners.add(cb)

        return () => listeners.delete(cb)
      },
      set: (next: T) => {
        value = next
        listeners.forEach(cb => cb(next))
      }
    }
  }

  return {
    atom,
    queryClient: { invalidateQueries }
  }
})

const boardInvalidations = () =>
  invalidateQueries.mock.calls.filter(
    ([arg]) => JSON.stringify((arg as { queryKey?: unknown }).queryKey) === JSON.stringify(['kanban', 'board'])
  ).length

/** Fresh module state per test (the throttle keeps module-level timers),
 *  with the plugin's doors stubbed: rest is never called here, storage
 *  echoes fallbacks, and the socket factory hands us its onMessage. */
async function bind() {
  vi.resetModules()
  const mod = await import('./api')
  const { bindApi } = mod

  let onMessage: ((data: unknown) => void) | null = null
  const dispose = bindApi(
    (() => Promise.reject(new Error('rest unused in this test'))) as never,
    { get: (_key: string, fallback: unknown) => fallback, set: () => undefined } as never,
    (_path: string, handler: (data: unknown) => void) => {
      onMessage = handler

      return () => undefined
    }
  )

  const frame = (taskId = 't_1') => onMessage?.({ events: [{ task_id: taskId }] })

  return { dispose, frame, switchBoard: (slug: string) => mod.$boardSlug.set(slug) }
}

describe('board invalidation throttle', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    invalidateQueries.mockClear()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('collapses a burst of frames into leading + one trailing refetch', async () => {
    const { dispose, frame } = await bind()

    frame()
    expect(boardInvalidations()).toBe(1) // leading edge, immediate

    frame()
    frame()
    frame()
    expect(boardInvalidations()).toBe(1) // burst inside the window coalesces

    vi.advanceTimersByTime(3_000)
    expect(boardInvalidations()).toBe(2) // one trailing refetch

    vi.advanceTimersByTime(10_000)
    expect(boardInvalidations()).toBe(2) // nothing left pending

    dispose()
  })

  it('fires leading again once the window has passed', async () => {
    const { dispose, frame } = await bind()

    frame()
    vi.advanceTimersByTime(3_000)
    frame()
    expect(boardInvalidations()).toBe(2)

    dispose()
  })

  it('still invalidates per-task detail on every frame', async () => {
    const { dispose, frame } = await bind()

    frame('t_a')
    frame('t_b')

    const detailKeys = invalidateQueries.mock.calls
      .map(([arg]) => (arg as { queryKey?: unknown[] }).queryKey)
      .filter(key => Array.isArray(key) && key[1] === 'task')

    expect(detailKeys).toHaveLength(2)
    expect(boardInvalidations()).toBe(1)

    dispose()
  })

  it('a board switch drops the pending trailing invalidation and reopens the window', async () => {
    const { dispose, frame, switchBoard } = await bind()

    frame()
    frame() // schedules the trailing edge for the current board
    expect(boardInvalidations()).toBe(1)

    switchBoard('other') // reopens the socket → throttle reset
    vi.advanceTimersByTime(10_000)
    expect(boardInvalidations()).toBe(1) // stale trailing never fired

    frame()
    expect(boardInvalidations()).toBe(2) // fresh board invalidates immediately

    dispose()
  })

  it('a disposed plugin never fires its pending trailing invalidation', async () => {
    const { dispose, frame } = await bind()

    frame()
    frame() // schedules the trailing edge
    expect(boardInvalidations()).toBe(1)

    dispose()
    vi.advanceTimersByTime(10_000)
    expect(boardInvalidations()).toBe(1)
  })
})
