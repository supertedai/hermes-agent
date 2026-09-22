import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import type * as Nanostores from 'nanostores'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

import type { ProjectInfo } from '@/types/hermes'

import { ProjectContextMenu, ProjectMenu } from './project-menu'
import type { SidebarProjectTree } from './workspace-groups'

afterEach(cleanup)

// jsdom doesn't implement ResizeObserver; Radix's PopoverContent/Arrow use it
// (via @radix-ui/react-use-size) to measure the arrow once the popover is
// actually mounted. The kebab-only test above never opens a Popover, so it
// doesn't need this — only the appearance-popover test below does.
beforeAll(() => {
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
  )
  // Radix's ContextMenu coordinates through pointer capture + scrollIntoView,
  // which jsdom does not implement (same shims as statusbar-visibility.test.tsx).
  Element.prototype.hasPointerCapture ??= () => false
  Element.prototype.setPointerCapture ??= () => undefined
  Element.prototype.releasePointerCapture ??= () => undefined
  HTMLElement.prototype.scrollIntoView ??= () => undefined
})

vi.mock('@/i18n', () => ({
  useI18n: () => ({
    t: {
      common: { cancel: 'Cancel', confirm: 'Confirm', done: 'Done', loading: 'Loading…' },
      sidebar: {
        projects: {
          copyPath: 'Copy path',
          deleteConfirm: 'This cannot be undone.',
          menu: 'Actions',
          menuAddFolder: 'Add folder',
          menuAppearance: 'Appearance',
          menuDelete: 'Delete',
          menuRename: 'Rename',
          menuSetActive: 'Set active',
          noColor: 'No color',
          removeFolder: 'Remove folder',
          removeFromSidebar: 'Remove from sidebar',
          reveal: 'Reveal in file manager'
        }
      }
    }
  })
}))

vi.mock('@/store/layout', () => ({
  $panesFlipped: {
    get: () => false,
    listen: () => () => {},
    subscribe: (fn: (v: boolean) => void) => {
      fn(false)

      return () => {}
    }
  },
  dismissAutoProject: vi.fn()
}))

const { $projects } = vi.hoisted(() => {
  const { atom } = require('nanostores') as typeof Nanostores

  return { $projects: atom<ProjectInfo[]>([]) }
})

vi.mock('@/store/projects', () => ({
  $projects,
  copyPath: vi.fn(),
  deleteProject: vi.fn(),
  openProjectAddFolder: vi.fn(),
  openProjectRemoveFolder: vi.fn(),
  openProjectRename: vi.fn(),
  revealPath: vi.fn(),
  setActiveProject: vi.fn(),
  setProjectAppearance: vi.fn().mockResolvedValue(false)
}))

// The cached project list is a real atom in the app; recreate it so useStore
// behaves identically without pulling in the rest of the projects store.
// vi.mock factories are hoisted above the rest of the file, so the atom must be
// created inside vi.hoisted to exist by the time the factory runs.
const store = await import('@/store/projects')
const openProjectRemoveFolder = vi.mocked(store.openProjectRemoveFolder)

const project = {
  color: null,
  icon: null,
  id: 'p1',
  isAuto: false,
  label: 'Test D',
  path: '/repo'
} as unknown as SidebarProjectTree

const tipTrigger = (el: HTMLElement) => el.closest('[data-slot="tooltip-trigger"]')

const openTriggerMenu = (trigger: HTMLElement) => {
  // Radix's dropdown trigger opens on pointerdown (a synthetic 'click' fireEvent
  // alone won't do it), so fire the full mouse sequence a real click produces —
  // same technique as session-actions-menu.test.tsx (#67500).
  fireEvent.pointerDown(trigger, { button: 0, pointerType: 'mouse' })
  fireEvent.pointerUp(trigger, { button: 0, pointerType: 'mouse' })
  fireEvent.click(trigger)
}

// Radix opens a ContextMenu on contextmenu after a pointerdown positions it.
const openContextMenu = (target: HTMLElement) => {
  fireEvent.pointerDown(target, { button: 2, ctrlKey: false, pointerType: 'mouse' })
  fireEvent.contextMenu(target, { button: 2 })
}

describe('ProjectMenu', () => {
  it('does not wrap the kebab trigger in a Tip', () => {
    render(<ProjectMenu isActive={false} project={project} />)

    const button = screen.getByRole('button', { name: 'Actions' })
    expect(tipTrigger(button)).toBeNull()
  })

  // When anchorRef is absent, PopoverAnchor wraps the dropdown trigger so the
  // appearance popover positions against the kebab. asChild must still reach
  // the real button (no non-forwarding wrappers inside the chain — #67500).
  it('opens the appearance popover through the kebab trigger when anchorRef is absent', async () => {
    render(<ProjectMenu isActive={false} project={project} />)

    const trigger = screen.getByRole('button', { name: 'Actions' })

    openTriggerMenu(trigger)

    const appearanceItem = await screen.findByRole('menuitem', { name: 'Appearance' })

    fireEvent.click(appearanceItem)

    // The color-swatch "No color" clear option only renders once the
    // appearance Popover is actually open — proving the click reached the
    // real button through the full Tip > PopoverAnchor > DropdownMenuTrigger
    // chain rather than getting silently dropped on an intermediate wrapper.
    expect(await screen.findByRole('button', { name: 'No color' })).toBeTruthy()
  }, 15000)
})

// "Remove folder" is the undo half of "Add folder": without it a folder can be
// added to a project but never taken out again (moving one = remove + add).
describe('ProjectMenu remove folder', () => {
  const withFolders = (paths: string[]): ProjectInfo =>
    ({
      folders: paths.map((path, index) => ({ added_at: index, is_primary: index === 0, label: null, path })),
      id: 'p1',
      name: 'Test D',
      primary_path: paths[0] ?? null
    }) as ProjectInfo

  beforeEach(() => {
    $projects.set([])
    openProjectRemoveFolder.mockClear()
  })

  const openMenu = () => {
    render(<ProjectMenu isActive={false} project={project} />)
    openTriggerMenu(screen.getByRole('button', { name: 'Actions' }))
  }

  it('opens the folder picker for a project that has folders', async () => {
    $projects.set([withFolders(['/repo/wiki', '/repo/notes'])])

    openMenu()

    fireEvent.click(await screen.findByRole('menuitem', { name: 'Remove folder…' }))

    expect(openProjectRemoveFolder).toHaveBeenCalledWith({ id: 'p1', name: 'Test D' })
  })

  it('stays out of an auto row, which has no record to hold a folder', async () => {
    // The repo is listed in the cache, so only `isAuto` can be what hides it.
    $projects.set([withFolders(['/repo/wiki'])])

    render(<ProjectMenu isActive={false} project={{ ...project, isAuto: true } as SidebarProjectTree} />)
    openTriggerMenu(screen.getByRole('button', { name: 'Actions' }))

    // Wait for the menu to be up (this row gets the inherited-repo items)…
    await screen.findByRole('menuitem', { name: 'Appearance' })

    expect(screen.queryByRole('menuitem', { name: 'Remove folder…' })).toBeNull()
  })

  it('stays out of a project whose folders are all gone', async () => {
    $projects.set([withFolders([])])

    openMenu()

    await screen.findByRole('menuitem', { name: 'Add folder' })

    expect(screen.queryByRole('menuitem', { name: 'Remove folder…' })).toBeNull()
  })
})

// The row's right-click menu renders the same `useProjectActions` items, but
// UNCONDITIONALLY (the kebab's JSX branches on isAuto before it gets there). So
// the auto-row gate that keeps folder actions away from an inherited repo only
// has teeth here — the kebab test above would pass without it.
describe('ProjectContextMenu folder actions', () => {
  const withFolders = (paths: string[]): ProjectInfo =>
    ({
      folders: paths.map((path, index) => ({ added_at: index, is_primary: index === 0, label: null, path })),
      id: 'p1',
      name: 'Test D',
      primary_path: paths[0] ?? null
    }) as ProjectInfo

  beforeEach(() => {
    $projects.set([])
    openProjectRemoveFolder.mockClear()
  })

  const rightClickRow = (isAuto: boolean) => {
    render(
      <ProjectContextMenu isActive={false} project={{ ...project, isAuto } as SidebarProjectTree}>
        <div>row</div>
      </ProjectContextMenu>
    )
    openContextMenu(screen.getByText('row'))
  }

  it('keeps folder actions out of an auto row, even when the cache has folders', async () => {
    // The repo IS in the cached list, so only the auto gate can hide the item.
    $projects.set([withFolders(['/repo/wiki'])])

    rightClickRow(true)

    await screen.findByRole('menuitem', { name: 'Appearance' })

    expect(screen.queryByRole('menuitem', { name: 'Remove folder…' })).toBeNull()
    expect(screen.queryByRole('menuitem', { name: 'Add folder' })).toBeNull()
  })

  it('offers the folder picker on an explicit project', async () => {
    $projects.set([withFolders(['/repo/wiki', '/repo/notes'])])

    rightClickRow(false)

    fireEvent.click(await screen.findByRole('menuitem', { name: 'Remove folder…' }))

    expect(openProjectRemoveFolder).toHaveBeenCalledWith({ id: 'p1', name: 'Test D' })
  })
})
