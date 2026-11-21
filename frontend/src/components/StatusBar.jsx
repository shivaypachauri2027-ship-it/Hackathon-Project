import { useEffect, useState } from 'react'
import { api } from '../api.js'

// Shows, live, which real services the app is using right now.
// Judges can see at a glance that PostgreSQL / Kafka / OpenSearch are connected
// (or that a clearly-labelled fallback is active).
const NAMES = { postgres: 'PostgreSQL', kafka: 'Kafka', opensearch: 'OpenSearch' }
const LABELS = {
  connected: 'connected',
  fallback: 'fallback mode',
  pending: 'not connected yet',
  error: 'error',
}

export default function StatusBar() {
  const [health, setHealth] = useState(null)
  const [offline, setOffline] = useState(false)

  useEffect(() => {
    let alive = true
    async function load() {
      try {
        const data = await api.health()
        if (alive) {
          setHealth(data)
          setOffline(false)
        }
      } catch {
        if (alive) setOffline(true)
      }
    }
    load()
    const timer = setInterval(load, 10000)
    return () => {
      alive = false
      clearInterval(timer)
    }
  }, [])

  return (
    <footer className="statusbar">
      <div className="statusbar__inner">
        <span className={`status status--${offline ? 'error' : health ? 'connected' : 'pending'}`}>
          <i aria-hidden="true" />
          API {offline ? 'offline' : health ? 'online' : 'checking'}
        </span>
        {health &&
          !offline &&
          Object.entries(health.services).map(([key, s]) => (
            <span key={key} className={`status status--${s.status}`} title={s.detail}>
              <i aria-hidden="true" />
              {NAMES[key] || key} {LABELS[s.status] || s.status}
            </span>
          ))}
        <span className="statusbar__note">InstaStock by Code Verse, DSATM</span>
      </div>
    </footer>
  )
}
