import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type * as Nanostores from 'nanostores'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { ProjectInfo } from '@/types/hermes'

import { ProjectDialog } from './project-dialog'

afterEach(cleanup)

vi.mock('@/i18n', () => ({
  useI18n: () => ({
    t: {
      common: { cancel: 'Cancel', save: 'Save' },
      sidebar: {
        projects: {
          addFolder: 'Add folder',
          create: 'Create',
          createDesc: 'Create a new project',
          createFailed: 'Failed to create project',
          createTitle: 'New project',
          foldersLabel: 'Folders',
          ideaGenerate: 'Generate',
          ideaGenerating: 'Generating…',
          ideaLabel: 'Idea',
          ideaPlaceholder: 'What are you building?',
          ideaShuffle: 'Shuffle ideas',
          namePlaceholder: 'Project name',
          noFolders: 'No folders yet',
          primaryBadge: 'Primary',
          removeFolder: 'Remove folder',
          removeFolderDesc: 'Nothing on disk is deleted.',
          removeFolderFailed: 'Could not remove folder'
        }
      }
    }
  })
}))

// $projectDialog and $projects are real nanostore atoms in the app; recreate
// them here so useStore behaves identically without pulling in the rest of the
// projects store (backend calls, project list, etc.) which is irrelevant to the
// behavior under test. vi.mock factories are hoisted above the rest of the
// file, so the atoms must be created inside vi.hoisted to exist by the time the
// factory runs.
const { $projectDialog, $projects } = vi.hoisted(() => {
  const { atom } = require('nanostores') as typeof Nanostores

  return {
    $projectDialog: atom<{ mode: 'add-folder' | 'create' | 'remove-folder' | 'rename'; name?: string; projectId?: string } | null>(
      {
        mode: 'create'
      }
    ),
    $projects: atom<ProjectInfo[]>([])
  }
})

vi.mock('@/store/projects', () => ({
  $projectDialog,
  $projects,
  addProjectFolder: vi.fn(),
  closeProjectDialog: vi.fn(),
  createProject: vi.fn(),
  generateProjectIdea: vi.fn(),
  pickProjectFolder: vi.fn(async () => '/Users/test/my-folder'),
  removeProjectFolder: vi.fn(),
  renameProject: vi.fn()
}))

vi.mock('@/store/notifications', () => ({
  notifyError: vi.fn()
}))

vi.mock('@/lib/project-idea-templates', () => ({
  randomIdeaTemplates: () => [{ emoji: '🚀', idea: 'A rocket tracker', label: 'Rocket tracker' }]
}))

const store = await import('@/store/projects')
const closeProjectDialog = vi.mocked(store.closeProjectDialog)
const removeProjectFolder = vi.mocked(store.removeProjectFolder)

const projectWith = (folders: Array<[string, boolean]>): ProjectInfo =>
  ({
    folders: folders.map(([path, is_primary], index) => ({ added_at: index, is_primary, label: null, path })),
    id: 'p1',
    name: 'Wiki',
    primary_path: folders.find(([, is_primary]) => is_primary)?.[0] ?? null
  }) as ProjectInfo

const tipTrigger = (el: HTMLElement) => el.closest('[data-slot="tooltip-trigger"]')

describe('ProjectDialog', () => {
  it('wraps the "shuffle idea" button in a Tip', () => {
    render(<ProjectDialog />)

    const button = screen.getByRole('button', { name: 'Shuffle ideas' })
    expect(tipTrigger(button)).toBeTruthy()
  })

  it('wraps the "remove folder" button in a Tip once a folder is added', async () => {
    render(<ProjectDialog />)

    fireEvent.click(screen.getByRole('button', { name: 'Add folder' }))

    const button = await screen.findByRole('button', { name: 'Remove folder' })
    expect(tipTrigger(button)).toBeTruthy()
  })
})

// The picker half of "Remove folder…": the menu opens this dialog, the dialog
// lists what the project still owns (name + primary mark), and only a picked
// folder arms the destructive button.
describe('ProjectDialog remove-folder', () => {
  afterEach(() => {
    $projectDialog.set(null)
    $projects.set([])
    vi.clearAllMocks()
  })

  const confirmButton = () => screen.getByRole('button', { name: 'Remove folder' }) as HTMLButtonElement

  it('lists the folders, marks the primary one, and removes only the picked folder', async () => {
    $projects.set([projectWith([['/repo/wiki', true], ['/repo/notes', false]])])
    $projectDialog.set({ mode: 'remove-folder', name: 'Wiki', projectId: 'p1' })

    render(<ProjectDialog />)

    expect(screen.getByText('Nothing on disk is deleted.')).toBeTruthy()
    expect(screen.getByRole('button', { name: /wiki/ })).toBeTruthy()
    // One badge, on the primary row.
    expect(screen.getAllByText('Primary')).toHaveLength(1)
    // Nothing is preselected — the destructive button waits for a pick.
    expect(confirmButton().disabled).toBe(true)

    fireEvent.click(screen.getByRole('button', { name: /notes/ }))
    expect(confirmButton().disabled).toBe(false)

    fireEvent.click(confirmButton())

    await waitFor(() => expect(removeProjectFolder).toHaveBeenCalledWith('p1', '/repo/notes'))
    expect(closeProjectDialog).toHaveBeenCalled()
  })

  it('survives a project that has no folders left (the zero-folder state is legal)', () => {
    $projects.set([projectWith([])])
    $projectDialog.set({ mode: 'remove-folder', name: 'Wiki', projectId: 'p1' })

    render(<ProjectDialog />)

    expect(screen.getByText('No folders yet')).toBeTruthy()
    expect(confirmButton().disabled).toBe(true)
  })
})
