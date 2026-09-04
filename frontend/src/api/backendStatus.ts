export interface BackendStatus {
  status: string
  service: string
}

export async function fetchBackendStatus(): Promise<BackendStatus> {
  const response = await fetch('/api/status')

  if (!response.ok) {
    throw new Error(`Backend status request failed: ${response.status}`)
  }

  return (await response.json()) as BackendStatus
}