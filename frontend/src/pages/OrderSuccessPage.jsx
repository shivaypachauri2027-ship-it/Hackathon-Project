import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { formatINR } from '../utils/format.js'

const POLL_MS = 1500
const MAX_POLLS = 80 // stop checking after about 2 minutes

const timeOf = (at) =>
  at ? new Date(at).toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit', second: '2-digit' }) : ''

export default function OrderSuccessPage({ initialOrder, onContinue }) {
  const [order, setOrder] = useState(initialOrder)
  const [polls, setPolls] = useState(0)
  const allDone = order.journey.every((s) => s.done)

  // Re-fetch the order every 1.5 s so the journey below updates live
  // as the Kafka workers (Phase 4/5) process it.
  useEffect(() => {
    if (allDone || polls >= MAX_POLLS) return
    const t = setTimeout(async () => {
      try {
        setOrder(await api.order(order.order_number))
      } catch {
        // keep showing what we have; try again next round
      }
      setPolls((n) => n + 1)
    }, POLL_MS)
    return () => clearTimeout(t)
  }, [order, polls, allDone])

  return (
    <section className="page success">
      <div className="success__hero">
        <div className="success__tick" aria-hidden="true">✓</div>
        <div>
          <h1 className="page__title">Order placed</h1>
          <p className="success__meta">
            Order <strong>{order.order_number}</strong> for {order.customer_name}, cash on delivery in {order.city}
          </p>
        </div>
      </div>

      <div className="success__grid">
        <div className="panel">
          <h2>What happened to your order</h2>
          <ol className="journey">
            {order.journey.map((step, n) => (
              <li key={step.key} className={`journey__step${step.done ? ' journey__step--done' : ''}`}>
                <span className="journey__marker" aria-hidden="true">
                  {step.done ? '✓' : n + 1}
                </span>
                <div>
                  <p className="journey__label">
                    {step.label}
                    {step.done && step.at && <span className="journey__time">{timeOf(step.at)}</span>}
                  </p>
                  <p className="journey__detail">{step.detail}</p>
                </div>
              </li>
            ))}
          </ol>
          {!allDone && <p className="muted live-note">This list updates by itself while the workers process your order.</p>}
        </div>

        <div className="panel summary">
          <h2>Items</h2>
          <ul className="summary__lines">
            {order.items.map((i) => (
              <li key={i.product_id}>
                <span>
                  {i.name} <span className="muted">× {i.quantity}</span>
                </span>
                <span>{formatINR(i.line_total)}</span>
              </li>
            ))}
          </ul>
          <div className="sum-row sum-row--total">
            <span>Total (cash on delivery)</span>
            <span>{formatINR(order.total_amount)}</span>
          </div>
          <p className="muted">
            Delivering to {order.address}, {order.city}. Mobile {order.phone}.
          </p>
          <button type="button" className="btn btn--primary btn--block" onClick={onContinue}>
            Continue shopping
          </button>
        </div>
      </div>
    </section>
  )
}
