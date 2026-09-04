import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fetchBackendStatus } from '../api/backendStatus'
import BackendConnectionStatus from './BackendConnectionStatus'

vi.mock('../api/backendStatus', () => ({
  fetchBackendStatus: vi.fn(),
}))

const fetchBackendStatusMock = vi.mocked(fetchBackendStatus)

describe('BackendConnectionStatus', () => {
  beforeEach(() => {
    fetchBackendStatusMock.mockReset()
  })

  it('displays the connected backend service', async () => {
    fetchBackendStatusMock.mockResolvedValue({
      status: 'UP',
      service: 'beatrice-backend',
    })

    render(<BackendConnectionStatus />)

    expect(screen.getByText(/checking backend connection/i))
      .toBeInTheDocument()

    expect(
      await screen.findByText(/connected to beatrice-backend/i),
    ).toBeInTheDocument()
  })

  it('displays an error when the backend is unavailable', async () => {
    fetchBackendStatusMock.mockRejectedValue(
      new Error('Backend is unavailable'),
    )

    render(<BackendConnectionStatus />)

    expect(
      await screen.findByText(/unable to connect to the backend/i),
    ).toBeInTheDocument()
  })
})