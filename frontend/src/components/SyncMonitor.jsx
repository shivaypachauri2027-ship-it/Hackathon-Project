import { useEffect, useState } from 'react'
import { api } from '../api.js'

// Shows the same product's stock in PostgreSQL (the truth) and in OpenSearch
// (the search copy) side by side, every half second, until they match.
// That gap closing is Kafka + the search-sync worker doing their job.
const POLL_MS = 500
const GIVE_UP_MS = 20000

export default function SyncMonitor({ productId, city, startedAt }) {
  const [status, setStatus] = useState(null)
  const [syncedAfter, setSyncedAfter] = useState(null)
  const [gaveUp, setGaveUp] = useState(false)

  useEffect(() => {
    if (!startedAt) return
    let alive = true
    let timer
    setSyncedAfter(null)
    setGaveUp(false)
    async function poll() {
      try {
        const s = await api.syncStatus(productId, city)
        if (!alive) return
        setStatus(s)
        if (s.in_sync || !s.search_enabled) {
          setSyncedAfter((Date.now() - startedAt) / 1000)
          return
        }
      } catch {
        // keep trying
      }
      if (!alive) return
      if (Date.now() - startedAt < GIVE_UP_MS) timer = setTimeout(poll, POLL_MS)
      else setGaveUp(true)
    }
    poll()
    return () => {
      alive = false
      clearTimeout(timer)
    }
  }, [productId, city, startedAt])

  if (!startedAt || !status) return null

  if (!status.search_enabled) {
    return (
      <p className="sync__note">
        OpenSearch is switched off, so search reads PostgreSQL directly: {status.postgres} available in {status.city}.
      </p>
    )
  }

  const waiting = syncedAfter === null && !gaveUp
  let note = `In sync ${syncedAfter?.toFixed(1)} s after the change. Search now shows the new stock.`
  if (waiting) note = 'Syncing through Kafka: inventory-events → search-sync worker → OpenSearch…'
  if (gaveUp) note = 'Search hasn’t caught up after 20 s. Is the worker running? (python -m app.worker)'

  return (
    <div className="sync" aria-live="polite">
      <div className="sync__side">
        <span className="sync__label">PostgreSQL (source of truth)</span>
        <strong className="sync__value">{status.postgres}</strong>
        <span className="sync__unit">available in {status.city}</span>
      </div>
      <div className={`sync__arrow${waiting ? ' sync__arrow--busy' : ''}`} aria-hidden="true">
        Kafka
      </div>
      <div className="sync__side">
        <span className="sync__label">OpenSearch (search copy)</span>
        <strong className="sync__value">{status.opensearch ?? '?'}</strong>
        <span className="sync__unit">available in {status.city}</span>
      </div>
      <p className={`sync__note${syncedAfter !== null ? ' sync__note--ok' : ''}${gaveUp ? ' sync__note--bad' : ''}`}>{note}</p>
    </div>
  )
}
