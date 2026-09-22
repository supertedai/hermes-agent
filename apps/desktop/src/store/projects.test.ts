import { atom } from 'nanostores'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { NO_PROJECT_ID, type SidebarProjectTree } from '@/app/chat/sidebar/projects/workspace-groups'
import { $sidebarAgentsGrouped } from '@/store/layout'
import { $activeGatewayProfile } from '@/store/profile'
import {
  $currentCwd,
  $selectedStoredSessionId,
  $sessions,
  applyConfiguredDefaultProjectDir
} from '@/store/session'
import type { ProjectInfo } from '@/types/hermes'

import {
  $activeProjectId,
  $projects,
  $projectScope,
  $projectsRpcAvailable,
  $projectTree,
  $removedSessionIds,
  $sessionMutationsInFlight,
  $worktreeRefreshToken,
  ALL_PROJECTS,
  beginSessionMutation,
  createProject,
  endSessionMutation,
  enterProject,
  exitProjectScope,
  openProjectCreate,
  pickProjectFolder,
  projectNameForCwd,
  refreshProjects,
  refreshProjectTree,
  refreshWorktrees,
  removeProjectFolder,
  resolveNewSessionCwd,
  scanAndRecordRepos,
  tombstoneSessions
} from './projects'

vi.mock('@/i18n', () => ({
  translateNow: (key: string) => key
}))

vi.mock('@/store/notifications', () => ({
  notify: vi.fn()
}))

vi.mock('@/lib/desktop-fs', () => ({
  desktopDefaultCwd: vi.fn(),
  isDesktopFsRemoteMode: vi.fn(),
  selectDesktopPaths: vi.fn(),
  writeDesktopFileText: vi.fn()
}))

vi.mock('@/store/gateway', () => ({
  $gateway: atom(null),
  activeGateway: vi.fn(),
  ensureActiveGatewayOpen: vi.fn()
}))

vi.mock('@/lib/desktop-git', () => ({ desktopGit: vi.fn() }))

vi.mock('@/hermes', () => ({
  getHermesConfig: vi.fn(),
  getProfiles: vi.fn(),
  setApiRequestProfile: vi.fn(),
  STARTUP_REQUEST_TIMEOUT_MS: 1000
}))

const fs = await import('@/lib/desktop-fs')
const desktopDefaultCwd = vi.mocked(fs.desktopDefaultCwd)
const isDesktopFsRemoteMode = vi.mocked(fs.isDesktopFsRemoteMode)
const selectDesktopPaths = vi.mocked(fs.selectDesktopPaths)

const gw = await import('@/store/gateway')
const activeGateway = vi.mocked(gw.activeGateway)
const gatewayAtom = gw.$gateway

const git = await import('@/lib/desktop-git')
const desktopGit = vi.mocked(git.desktopGit)

const hermes = await import('@/hermes')
const getHermesConfig = vi.mocked(hermes.getHermesConfig)
const notifications = await import('@/store/notifications')
const notify = vi.mocked(notifications.notify)

describe('project scope', () => {
  beforeEach(() => {
    window.localStorage.clear()
    $projectScope.set(ALL_PROJECTS)
  })

  it('defaults to ALL_PROJECTS', () => {
    expect($projectScope.get()).toBe(ALL_PROJECTS)
  })

  it('enterProject scopes the sidebar to the project id', () => {
    // setActiveProject fires best-effort (no gateway in test → it rejects and is
    // swallowed); the synchronous scope change is what matters here.
    enterProject('p_123')
    expect($projectScope.get()).toBe('p_123')
  })

  it('exitProjectScope returns to the overview', () => {
    enterProject('p_123')
    exitProjectScope()
    expect($projectScope.get()).toBe(ALL_PROJECTS)
  })

  it('entering the synthetic Home bucket still scopes (no active pin)', () => {
    enterProject(NO_PROJECT_ID)
    expect($projectScope.get()).toBe(NO_PROJECT_ID)
  })

  it('persists the scope to localStorage', () => {
    enterProject('p_abc')
    expect(window.localStorage.getItem('hermes.desktop.projectScope')).toBe('p_abc')
  })
})

describe('resolveNewSessionCwd', () => {
  beforeEach(() => {
    $projectScope.set(ALL_PROJECTS)
    applyConfiguredDefaultProjectDir('/home/user/configured')
    $currentCwd.set('')
    $selectedStoredSessionId.set(null)
    $sessions.set([])
    // Reset focused-session projections by clearing the inputs they read.
    // $focusedStoredSessionId falls back to $selectedStoredSessionId.
    // $focusedSessionState needs a runtime — leave it empty via no session states.
  })

  afterEach(() => {
    applyConfiguredDefaultProjectDir(null)
    $projectScope.set(ALL_PROJECTS)
    $currentCwd.set('')
    $selectedStoredSessionId.set(null)
    $sessions.set([])
  })

  it('starts a chat detached inside Home, ignoring the configured default dir', () => {
    // Attaching the default dir here would move the new chat out of Home the
    // moment it was created — "no folder" is what the bucket means.
    enterProject(NO_PROJECT_ID)

    expect(resolveNewSessionCwd()).toBe('')
  })

  it('still falls back to the configured default outside Home', () => {
    expect(resolveNewSessionCwd()).toBe('/home/user/configured')
  })

  it('inherits the focused session workspace when not drilled into a project', () => {
    // Simulate a primary session whose stored row carries a project cwd —
    // the common case: you're in a chat that has a pwd, hit ⌘N/⌘T, and
    // expect the new draft to stay in that project without sidebar drill-in.
    $selectedStoredSessionId.set('sess-a')
    $sessions.set([
      {
        archived: false,
        cwd: '/Users/me/www/hermes-agent',
        ended_at: null,
        id: 'sess-a',
        input_tokens: 0,
        is_active: true,
        last_active: 0,
        message_count: 1,
        model: null,
        output_tokens: 0,
        started_at: 0,
        title: 'work'
      } as never
    ])

    expect(resolveNewSessionCwd()).toBe('/Users/me/www/hermes-agent')
  })

  it('does not re-attach a remembered cwd when the focused session is detached', () => {
    $currentCwd.set('/Users/me/stale-remembered')
    $selectedStoredSessionId.set('sess-detached')
    $sessions.set([
      {
        archived: false,
        cwd: null,
        ended_at: null,
        id: 'sess-detached',
        input_tokens: 0,
        is_active: true,
        last_active: 0,
        message_count: 1,
        model: null,
        output_tokens: 0,
        started_at: 0,
        title: 'loose'
      } as never
    ])

    // Focused session has no workspace → fall through to configured default,
    // not the stale $currentCwd from an earlier chat.
    expect(resolveNewSessionCwd()).toBe('/home/user/configured')
  })
})

describe('projectNameForCwd', () => {
  const treeNode = (
    over: Partial<SidebarProjectTree> & Pick<SidebarProjectTree, 'id' | 'label'>
  ): SidebarProjectTree => ({
    path: null,
    repos: [],
    sessionCount: 0,
    ...over
  })

  beforeEach(() => {
    $projectTree.set([])
  })

  it('names the explicit project owning the cwd (longest path match)', () => {
    $projectTree.set([
      treeNode({ id: 'p_web', label: 'Website', path: '/repos/website' }),
      treeNode({ id: 'p_api', label: 'API', path: '/repos/api' })
    ])

    expect(projectNameForCwd('/repos/website/src/app')).toBe('Website')
  })

  it('matches nested repo and worktree paths, not just the project root', () => {
    $projectTree.set([
      treeNode({
        id: 'p_mono',
        label: 'Monorepo',
        path: '/repos/mono',
        repos: [
          {
            id: 'r1',
            label: 'mono',
            path: '/repos/mono',
            sessionCount: 0,
            groups: [{ id: 'g1', label: 'feature', path: '/elsewhere/mono-feature', sessions: [] }]
          }
        ]
      })
    ])

    // A linked worktree lives OUTSIDE the project root but still belongs to it.
    expect(projectNameForCwd('/elsewhere/mono-feature/src')).toBe('Monorepo')
  })

  it('ignores auto-projects and the No-project bucket (no named identity)', () => {
    $projectTree.set([
      treeNode({ id: '/repos/loose', label: 'loose', path: '/repos/loose', isAuto: true }),
      treeNode({ id: '__no_project__', label: 'No project', path: null, isNoProject: true })
    ])

    expect(projectNameForCwd('/repos/loose/src')).toBeNull()
  })

  it('returns null for a cwd in no project and for a blank cwd', () => {
    $projectTree.set([treeNode({ id: 'p_web', label: 'Website', path: '/repos/website' })])

    expect(projectNameForCwd('/somewhere/else')).toBeNull()
    expect(projectNameForCwd('')).toBeNull()
  })
})

describe('worktree refresh', () => {
  it('refreshWorktrees bumps the probe token so useRepoWorktreeMap refetches', () => {
    const before = $worktreeRefreshToken.get()
    refreshWorktrees()
    expect($worktreeRefreshToken.get()).toBe(before + 1)
  })
})

describe('pickProjectFolder', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('uses the remote-aware directory picker locally', async () => {
    isDesktopFsRemoteMode.mockReturnValue(false)
    selectDesktopPaths.mockResolvedValue(['/local/repo'])

    await expect(pickProjectFolder()).resolves.toBe('/local/repo')
    expect(selectDesktopPaths).toHaveBeenCalledWith({ defaultPath: undefined, directories: true, multiple: false })
  })

  it('seeds the picker with the backend cwd on a remote gateway', async () => {
    isDesktopFsRemoteMode.mockReturnValue(true)
    desktopDefaultCwd.mockResolvedValue({ branch: 'main', cwd: '/backend/work' })
    selectDesktopPaths.mockResolvedValue(['/backend/work/repo'])

    await expect(pickProjectFolder()).resolves.toBe('/backend/work/repo')
    expect(selectDesktopPaths).toHaveBeenCalledWith({
      defaultPath: '/backend/work',
      directories: true,
      multiple: false
    })
  })

  it('returns null when the picker is cancelled (empty selection)', async () => {
    isDesktopFsRemoteMode.mockReturnValue(false)
    selectDesktopPaths.mockResolvedValue([])

    await expect(pickProjectFolder()).resolves.toBeNull()
  })
})

describe('createProject', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    $sidebarAgentsGrouped.set(false)
    $activeProjectId.set(null)
    $projectsRpcAvailable.set(null)
  })

  it('creates the project and flips into the grouped view so a blank slate shows it', async () => {
    const created = { folders: [], id: 'p_new', name: 'Demo', primary_path: '/srv/demo' }

    const request = vi.fn(async (method: string) => {
      if (method === 'projects.create') {
        return { project: created }
      }

      // Reconcile (fire-and-forget) re-reads list + tree; echo the project back
      // so the optimistic state survives instead of being wiped to empty.
      return { active_id: 'p_new', projects: [created], scoped_session_ids: [] }
    })

    activeGateway.mockReturnValue({ connectionState: 'open', request } as never)

    const result = await createProject({ folders: ['/srv/demo'], name: 'Demo', use: true })

    expect(result).toEqual(created)
    expect(request).toHaveBeenCalledWith('projects.create', expect.objectContaining({ name: 'Demo' }))
    expect($sidebarAgentsGrouped.get()).toBe(true)
    expect($activeProjectId.get()).toBe('p_new')
  })

  it('marks the backend stale and surfaces a friendly error when projects.create is missing', async () => {
    activeGateway.mockReturnValue({
      connectionState: 'open',
      request: vi.fn().mockRejectedValue(new Error('unknown method: projects.create'))
    } as never)

    await expect(createProject({ folders: ['/srv/demo'], name: 'Demo' })).rejects.toThrow(
      'sidebar.projects.staleBackend'
    )
    expect($projectsRpcAvailable.get()).toBe(false)
  })
})

describe('removeProjectFolder', () => {
  type Folder = ProjectInfo['folders'][number]

  const folder = (path: string, is_primary: boolean, added_at = 0): Folder => ({
    added_at,
    is_primary,
    label: null,
    path
  })

  const projectWith = (folders: Folder[], primary_path: null | string): ProjectInfo => ({
    archived: false,
    board_slug: null,
    color: null,
    created_at: 0,
    description: null,
    folders,
    icon: null,
    id: 'p1',
    name: 'Wiki',
    primary_path,
    slug: 'wiki'
  })

  const node = (path: null | string): SidebarProjectTree => ({
    id: 'p1',
    label: 'Wiki',
    path,
    repos: [],
    sessionCount: 0
  })

  // Stand-in for the projects.* backend: it owns the folders + primary_path,
  // applies the removal the way projects_db.remove_folder does (repoint to the
  // earliest folder left, or NULL when none is), and answers with the row a real
  // DB read would return. The list/tree refreshes reconcile from the same state.
  const backendFor = (state: { folders: Folder[]; primary_path: null | string }) => {
    const row = () => projectWith(state.folders, state.primary_path)

    return {
      connectionState: 'open' as const,
      request: vi.fn(async (method: string, params: Record<string, unknown>) => {
        if (method === 'projects.remove_folder') {
          const dropped = state.folders.find(f => f.path === params.path)
          state.folders = state.folders.filter(f => f.path !== params.path)

          if (dropped?.is_primary) {
            const next = [...state.folders].sort((a, b) => a.added_at - b.added_at).at(0) ?? null
            state.primary_path = next?.path ?? null
            state.folders = state.folders.map(f => ({ ...f, is_primary: f.path === next?.path }))
          }

          return { project: row() }
        }

        return method === 'projects.list'
          ? { active_id: null, projects: [row()] }
          : { active_id: null, projects: [node(state.primary_path)], scoped_session_ids: [] }
      })
    }
  }

  beforeEach(() => {
    vi.clearAllMocks()
    $projectsRpcAvailable.set(null)
  })

  it('sends the project id + path and drops a non-primary folder', async () => {
    const state = {
      folders: [folder('/repo/wiki', true, 1), folder('/repo/notes', false, 2)],
      primary_path: '/repo/wiki'
    }

    $projects.set([projectWith(state.folders, state.primary_path)])
    $projectTree.set([node('/repo/wiki')])
    const gateway = backendFor(state)
    activeGateway.mockReturnValue(gateway as never)

    await removeProjectFolder('p1', '/repo/notes')

    expect(gateway.request).toHaveBeenCalledWith('projects.remove_folder', { id: 'p1', path: '/repo/notes' })
    expect($projects.get()[0].folders.map(f => f.path)).toEqual(['/repo/wiki'])
    expect($projects.get()[0].primary_path).toBe('/repo/wiki')
    expect($projectTree.get()[0].path).toBe('/repo/wiki')
  })

  it('repoints the primary to the folder the DB read-back names', async () => {
    const state = {
      folders: [folder('/repo/wiki', true, 1), folder('/repo/notes', false, 2)],
      primary_path: '/repo/wiki'
    }

    $projects.set([projectWith(state.folders, state.primary_path)])
    $projectTree.set([node('/repo/wiki')])
    activeGateway.mockReturnValue(backendFor(state) as never)

    await removeProjectFolder('p1', '/repo/wiki')

    expect($projects.get()[0].folders).toEqual([folder('/repo/notes', true, 2)])
    expect($projects.get()[0].primary_path).toBe('/repo/notes')
    expect($projectTree.get()[0].path).toBe('/repo/notes')
  })

  it('settles on the read-back, not the local guess, when the cache is stale', async () => {
    // Another window added /repo/notes since this client last listed. Removing
    // the primary must NOT conclude "no folders left" — the DB row carries the
    // folder this client never saw, already repointed as primary.
    const state = {
      folders: [folder('/repo/wiki', true, 1), folder('/repo/notes', false, 2)],
      primary_path: '/repo/wiki'
    }

    $projects.set([projectWith([folder('/repo/wiki', true, 1)], '/repo/wiki')])
    $projectTree.set([node('/repo/wiki')])
    activeGateway.mockReturnValue(backendFor(state) as never)

    await removeProjectFolder('p1', '/repo/wiki')

    expect($projects.get()[0].folders).toEqual([folder('/repo/notes', true, 2)])
    expect($projects.get()[0].primary_path).toBe('/repo/notes')
    expect($projectTree.get()[0].path).toBe('/repo/notes')
  })

  it('paints the removal before the round-trip lands, then settles on the row', async () => {
    // The cache is a paint of server truth: the row updates on click, not after
    // the RPC returns. Hold the write open to observe the intermediate state.
    const state = {
      folders: [folder('/repo/wiki', true, 1), folder('/repo/notes', false, 2)],
      primary_path: '/repo/wiki'
    }

    $projects.set([projectWith(state.folders, state.primary_path)])
    $projectTree.set([node('/repo/wiki')])

    let settle: (value: unknown) => void = () => {}

    const inFlight = new Promise(resolve => {
      settle = resolve
    })

    const request = vi.fn(async (method: string) => {
      if (method === 'projects.remove_folder') {
        return inFlight
      }

      return method === 'projects.list'
        ? { active_id: null, projects: [projectWith(state.folders, state.primary_path)] }
        : { active_id: null, projects: [node(state.primary_path)], scoped_session_ids: [] }
    })

    activeGateway.mockReturnValue({ connectionState: 'open', request } as never)

    const call = removeProjectFolder('p1', '/repo/wiki')

    // Still awaiting the write: the folder is already gone and the survivor
    // carries the primary, with the tree node repointed alongside it.
    expect($projects.get()[0].folders).toEqual([folder('/repo/notes', true, 2)])
    expect($projects.get()[0].primary_path).toBe('/repo/notes')
    expect($projectTree.get()[0].path).toBe('/repo/notes')

    // The DB row lands — and it stays the authority.
    state.folders = [folder('/repo/notes', true, 2)]
    state.primary_path = '/repo/notes'
    settle({ project: projectWith(state.folders, state.primary_path) })
    await call

    expect($projects.get()[0].primary_path).toBe('/repo/notes')
  })

  it('leaves the project with zero folders when the last one goes', async () => {
    // Legal end state (measured: primary_path=None) — the sidebar must render
    // the folder-less project rather than crash on it.
    const state = { folders: [folder('/repo/wiki', true, 1)], primary_path: '/repo/wiki' }
    $projects.set([projectWith(state.folders, state.primary_path)])
    $projectTree.set([node('/repo/wiki')])
    activeGateway.mockReturnValue(backendFor(state) as never)

    await removeProjectFolder('p1', '/repo/wiki')

    expect($projects.get()[0].folders).toEqual([])
    expect($projects.get()[0].primary_path).toBeNull()
    expect($projectTree.get()[0].path).toBeNull()
  })

  it('rolls the cached folders + primary path back when the write fails', async () => {
    const folders = [folder('/repo/wiki', true, 1), folder('/repo/notes', false, 2)]
    $projects.set([projectWith(folders, '/repo/wiki')])
    $projectTree.set([node('/repo/wiki')])
    activeGateway.mockReturnValue({
      connectionState: 'open',
      request: vi.fn().mockRejectedValue(new Error('gateway down'))
    } as never)

    await expect(removeProjectFolder('p1', '/repo/wiki')).rejects.toThrow('gateway down')

    expect($projects.get()[0].folders).toEqual(folders)
    expect($projects.get()[0].primary_path).toBe('/repo/wiki')
    expect($projectTree.get()[0].path).toBe('/repo/wiki')
  })

  it('refuses to write once the backend is known stale', async () => {
    $projectsRpcAvailable.set(false)
    const request = vi.fn()
    activeGateway.mockReturnValue({ connectionState: 'open', request } as never)

    await expect(removeProjectFolder('p1', '/repo/wiki')).rejects.toThrow('sidebar.projects.staleBackend')
    expect(request).not.toHaveBeenCalled()
  })
})

describe('projects RPC capability', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    $projectsRpcAvailable.set(null)
  })

  it('marks the backend stale when projects.list is missing', async () => {
    activeGateway.mockReturnValue({
      connectionState: 'open',
      request: vi.fn().mockRejectedValue(new Error('unknown method: projects.list'))
    } as never)

    await refreshProjects()

    expect($projectsRpcAvailable.get()).toBe(false)
  })

  it('blocks opening the create dialog once the backend is known stale', () => {
    $projectsRpcAvailable.set(false)

    openProjectCreate()

    expect(notify).toHaveBeenCalledWith(
      expect.objectContaining({ kind: 'warning', message: 'sidebar.projects.staleBackend' })
    )
  })
})

describe('repository discovery policy', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    $activeGatewayProfile.set('default')
    isDesktopFsRemoteMode.mockReturnValue(false)
  })

  function gatewayWith(request: ReturnType<typeof vi.fn>) {
    const gateway = { connectionState: 'open', request }
    activeGateway.mockReturnValue(gateway as never)
    gatewayAtom.set(gateway as never)

    return gateway
  }

  it('records disabled policy without invoking the filesystem scanner', async () => {
    const request = vi.fn(async (method: string) =>
      method === 'projects.tree'
        ? { active_id: null, projects: [], scoped_session_ids: [] }
        : { accepted: false, repos: [] }
    )

    gatewayWith(request)
    const scanRepos = vi.fn()
    desktopGit.mockReturnValue({ scanRepos } as never)
    getHermesConfig.mockResolvedValue({
      desktop: {
        repo_scan_enabled: false,
        repo_scan_exclude_paths: [],
        repo_scan_roots: []
      }
    })

    await scanAndRecordRepos()

    expect(scanRepos).not.toHaveBeenCalled()
    expect(request).toHaveBeenCalledWith('projects.record_repos', {
      discovery_policy: { enabled: false, exclude_paths: [], roots: [] },
      repos: []
    })
  })

  it('passes custom roots and exclusions to Electron and records on the origin gateway', async () => {
    const request = vi.fn(async (method: string) =>
      method === 'projects.tree'
        ? { active_id: null, projects: [], scoped_session_ids: [] }
        : { accepted: true, repos: [] }
    )

    gatewayWith(request)
    const scanRepos = vi.fn().mockResolvedValue([{ label: 'repo', root: '/work/repo' }])
    desktopGit.mockReturnValue({ scanRepos } as never)
    getHermesConfig.mockResolvedValue({
      desktop: {
        repo_scan_enabled: true,
        repo_scan_exclude_paths: ['/work/vendor'],
        repo_scan_roots: ['/work']
      }
    })

    await scanAndRecordRepos()

    expect(getHermesConfig).toHaveBeenCalledWith('default')
    expect(scanRepos).toHaveBeenCalledWith(['/work'], {
      enabled: true,
      excludePaths: ['/work/vendor']
    })
    expect(request).toHaveBeenCalledWith('projects.record_repos', {
      discovery_policy: {
        enabled: true,
        exclude_paths: ['/work/vendor'],
        roots: ['/work']
      },
      repos: [{ label: 'repo', root: '/work/repo' }]
    })
  })

  it('does not scan the local filesystem for remote connections', async () => {
    isDesktopFsRemoteMode.mockReturnValue(true)
    const scanRepos = vi.fn()
    desktopGit.mockReturnValue({ scanRepos } as never)

    await scanAndRecordRepos(true)

    expect(scanRepos).not.toHaveBeenCalled()
    expect(getHermesConfig).not.toHaveBeenCalled()
  })
})

describe('project tree profile isolation', () => {
  it('does not publish a late response from the previous profile', async () => {
    let resolveA: ((value: unknown) => void) | undefined

    const responseA = new Promise(resolve => {
      resolveA = resolve
    })

    const gatewayA = { connectionState: 'open', request: vi.fn(() => responseA) }

    const gatewayB = {
      connectionState: 'open',
      request: vi.fn().mockResolvedValue({
        active_id: null,
        projects: [{ id: 'profile-b', label: 'Profile B', path: null, repos: [], sessionCount: 0 }],
        scoped_session_ids: []
      })
    }

    let current = gatewayA
    activeGateway.mockImplementation(() => current as never)
    gatewayAtom.set(gatewayA as never)

    const pendingA = refreshProjectTree()
    current = gatewayB
    $activeGatewayProfile.set('profile-b')
    gatewayAtom.set(gatewayB as never)
    await refreshProjectTree()
    resolveA?.({
      active_id: null,
      projects: [{ id: 'profile-a', label: 'Profile A', path: null, repos: [], sessionCount: 0 }],
      scoped_session_ids: []
    })
    await pendingA

    expect($projectTree.get().map(project => project.id)).toEqual(['profile-b'])
  })
})

describe('tombstone pruning', () => {
  const openGatewayReturning = (scopedIds: string[]) => {
    const gateway = {
      connectionState: 'open',
      request: vi.fn().mockResolvedValue({ active_id: null, projects: [], scoped_session_ids: scopedIds })
    }

    activeGateway.mockImplementation(() => gateway as never)
    gatewayAtom.set(gateway as never)

    return gateway
  }

  beforeEach(() => {
    $removedSessionIds.set(new Set())
    $sessionMutationsInFlight.set(new Set())
  })

  it('keeps an in-flight delete tombstone even when the backend snapshot omits it', async () => {
    // Optimistic delete: hide the row, mark the RPC as in flight.
    tombstoneSessions(['sess-1'])
    beginSessionMutation(['sess-1'])

    // A projects.tree refresh races the pending delete: the id is already gone
    // from scope, but the RPC hasn't landed — the tombstone must survive so the
    // row doesn't flash back.
    openGatewayReturning([])
    await refreshProjectTree()

    expect($removedSessionIds.get().has('sess-1')).toBe(true)
  })

  it('prunes the tombstone once the mutation settles and scope no longer lists it', async () => {
    tombstoneSessions(['sess-1'])
    beginSessionMutation(['sess-1'])
    openGatewayReturning([])
    await refreshProjectTree()

    // Delete RPC settled; the next refresh with the id absent from scope drops it.
    endSessionMutation(['sess-1'])
    await refreshProjectTree()

    expect($removedSessionIds.get().has('sess-1')).toBe(false)
  })
})
