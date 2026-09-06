import { render, screen, cleanup } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import TeamEditor from './TeamEditor'
import { roles } from '../api/teams'

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

it('saves edited player names and comfort through the API', async () => {
  const team = { id: 1, version: 0, name: 'Ravens', players: roles.map(role => ({ role, name: '', riotId: '', champions: [] })) }
  const saved = { ...team, version: 1 }
  const fetchMock = vi.fn().mockImplementation((path: string) => Promise.resolve(new Response(JSON.stringify(path === '/api/champions'
    ? { version: 'test', champions: [{ id: 'Swain', name: 'Swain', portrait: '/api/champions/Swain/portrait' }] } : saved))))
  vi.stubGlobal('fetch', fetchMock)
  const onSaved = vi.fn()
  render(<TeamEditor team={team} onSaved={onSaved} onDirty={vi.fn()} />)
  await userEvent.type(screen.getAllByLabelText('Player name')[0], 'Ed')
  await userEvent.click(screen.getAllByRole('button', { name: '+ Add champion' })[0])
  await userEvent.click(await screen.findByRole('button', { name: 'Swain' }))
  await userEvent.selectOptions(screen.getByLabelText('Comfort'), '10')
  await userEvent.click(screen.getByRole('button', { name: 'Save roster' }))
  expect(await screen.findByRole('status')).toHaveTextContent('Roster saved')
  const request = JSON.parse(fetchMock.mock.calls.find(call => call[1]?.method === 'PUT')![1].body)
  expect(request.players[0]).toMatchObject({ name: 'Ed', champions: [{ name: 'Swain', comfort: 10 }] })
  expect(onSaved).toHaveBeenCalledWith(saved)
})
