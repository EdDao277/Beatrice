import { useEffect, useState } from 'react'
import { fetchBackendStatus } from '../api/backendStatus'

function BackendConnectionStatus() {
  const [message, setMessage] = useState('Checking backend connection...')

  useEffect(() => {
    let isMounted = true

    fetchBackendStatus()
      .then((backendStatus) => {
        if (isMounted) {
          setMessage(`Connected to ${backendStatus.service}`)
        }
      })
      .catch(() => {
        if (isMounted) {
          setMessage('Unable to connect to the backend')
        }
      })

    return () => {
      isMounted = false
    }
  }, [])

  return (
    <section aria-labelledby="backend-connection-heading">
      <h2 id="backend-connection-heading">Backend connection</h2>
      <p role="status">{message}</p>
    </section>
  )
}

export default BackendConnectionStatus