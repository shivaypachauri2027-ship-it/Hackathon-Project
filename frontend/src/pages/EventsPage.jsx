import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { formatINR } from '../utils/format.js'

const REFRESH_MS = 2000

const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`

const timeOf = (at) =>
  at ? new Date(at).toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit', second: '2-digit' }) : ''

function Stage({ title, kind, value }) {
  return (
    <div className={`stage stage--${kind}`}>
      <span className="stage__kind">{kind === 'topic' ? 'Kafka topic' : kind === 'consumer' ? 'Kafka consumer group' : kind}</span>
      <strong className="stage__title">{title}</strong>
      {value !== undefined && <span className="stage__value">{value}</span>}
    </div>
  )
}

export default function EventsPage() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [updatedAt, setUpdatedAt] = useState(null)

  // Refresh every 2 seconds while this page is open
  useEffect(() => {
    let alive = true
    let timer
    async function load() {
      try {
        const d = await api.events(25)
        if (!alive) return
        setData(d)
        setError('')
        setUpdatedAt(new Date())
      } catch (err) {
        if (alive) setError(err.message)
      }
      if (alive) timer = setTimeout(load, REFRESH_MS)
    }
    load()
    return () => {
      alive = false
      clearTimeout(timer)
    }
  }, [])

  const s = data?.stats

  return (
    <section className="page events">
      <h1 className="page__title">Live events</h1>
      <p className="page__lede">
        Every order becomes an event in Apache Kafka. Workers pick it up, finalise the stock and refresh search.
        {updatedAt && <span className="muted"> Updated {timeOf(updatedAt)}.</span>}
      </p>

      {error && (
        <div className="notice notice--error" role="alert">
          <h3>Live events could not load</h3>
          <p>{error}</p>
        </div>
      )}

      {s && (
        <div className="pipeline" aria-label="Event pipeline">
          <Stage kind="PostgreSQL outbox" title="Checkout" value={`${s.waiting} waiting`} />
          <span className="pipeline__arrow" aria-hidden="true">→</span>
          <Stage kind="topic" title="order-events" value={`${plural(s.published, 'event')} sent`} />
          <span className="pipeline__arrow" aria-hidden="true">→</span>
          <Stage kind="consumer" title="inventory-worker" value={`${plural(s.inventory_worker, 'order')} confirmed`} />
          <span className="pipeline__arrow" aria-hidden="true">→</span>
          <Stage kind="topic" title="inventory-events" />
          <span className="pipeline__arrow" aria-hidden="true">→</span>
          <Stage kind="consumer" title="search-sync" value={plural(s.search_sync, 'index update')} />
          <span className="pipeline__arrow" aria-hidden="true">→</span>
          <Stage kind="OpenSearch" title="Search index" />
        </div>
      )}

      {data && (
        <>
          <div className="events__grid">
            <div className="panel">
              <h2>Sent to Kafka</h2>
              {data.outbox.length === 0 ? (
                <p className="muted">No events yet. Place an order and watch it appear here.</p>
              ) : (
                <div className="table-wrap">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Created</th>
                        <th>Event</th>
                        <th>Key</th>
                        <th>Topic</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.outbox.map((e) => (
                        <tr key={e.id}>
                          <td>{timeOf(e.created_at)}</td>
                          <td>{e.event_type}</td>
                          <td className="mono">{e.event_key}</td>
                          <td>{e.topic}</td>
                          <td>
                            {e.published_at ? (
                              <span className="badge badge--ok">Sent {timeOf(e.published_at)}</span>
                            ) : e.last_error ? (
                              <span className="badge badge--bad" title={e.last_error}>
                                Retrying ({e.publish_attempts})
                              </span>
                            ) : (
                              <span className="badge badge--wait">Waiting</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            <div className="panel">
              <h2>Processed by consumers</h2>
              {data.consumed.length === 0 ? (
                <p className="muted">Nothing processed yet. Is the worker running? (python -m app.worker)</p>
              ) : (
                <div className="table-wrap">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Time</th>
                        <th>Consumer</th>
                        <th>Partition, offset</th>
                        <th>What happened</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.consumed.map((e) => (
                        <tr key={e.id}>
                          <td>{timeOf(e.processed_at)}</td>
                          <td>{e.consumer}</td>
                          <td className="mono">
                            {e.kafka_partition ?? '-'}, {e.kafka_offset ?? '-'}
                          </td>
                          <td>
                            <span className="mono">{e.event_key}</span> {e.detail}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>

          <div className="panel">
            <h2>Latest orders</h2>
            {data.orders.length === 0 ? (
              <p className="muted">No orders yet.</p>
            ) : (
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Order</th>
                      <th>Placed</th>
                      <th>City</th>
                      <th>Units</th>
                      <th>Total</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.orders.map((o) => (
                      <tr key={o.order_number}>
                        <td className="mono">{o.order_number}</td>
                        <td>{timeOf(o.created_at)}</td>
                        <td>{o.city}</td>
                        <td>{o.units}</td>
                        <td>{formatINR(o.total_amount)}</td>
                        <td>
                          <span className={`badge ${o.status === 'CONFIRMED' ? 'badge--ok' : 'badge--wait'}`}>
                            {o.status === 'CONFIRMED' ? 'Confirmed' : 'Placed, stock reserved'}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </section>
  )
}
