import { useEffect, useState } from 'react'
import { formatINR } from '../utils/format.js'

function Thumb({ src, alt, brand }) {
  const [failed, setFailed] = useState(false)
  return src && !failed ? (
    <img className="thumb" src={src} alt={alt} onError={() => setFailed(true)} />
  ) : (
    <div className="thumb thumb--fallback" aria-hidden="true">{brand}</div>
  )
}

export default function CartDrawer({ open, onClose, cart, city, onCheckout }) {
  // Close with the Escape key
  useEffect(() => {
    if (!open) return
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  return (
    <div className={`drawer${open ? ' drawer--open' : ''}`}>
      <div className="drawer__backdrop" onClick={onClose} />
      <aside className="drawer__panel" role="dialog" aria-modal="true" aria-label="Your cart">
        <header className="drawer__head">
          <div>
            <h2>Your cart</h2>
            <p className="muted">Delivering to {city}</p>
          </div>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Close cart">
            ✕
          </button>
        </header>

        {cart.items.length === 0 ? (
          <div className="drawer__empty">
            <h3>Your cart is empty</h3>
            <p className="muted">Add something from the store and it will show up here.</p>
            <button type="button" className="btn btn--primary" onClick={onClose}>
              Browse products
            </button>
          </div>
        ) : (
          <>
            <ul className="cart-lines">
              {cart.items.map((i) => (
                <li key={i.id} className="cart-line">
                  <Thumb src={i.image_url} alt={i.name} brand={i.brand} />
                  <div className="cart-line__info">
                    <p className="cart-line__name">{i.name}</p>
                    <p className="cart-line__price">
                      <strong>{formatINR(i.price * i.quantity)}</strong>
                      {i.quantity > 1 && <span className="muted"> ({formatINR(i.price)} each)</span>}
                    </p>
                    <div className="cart-line__actions">
                      <div className="qty" role="group" aria-label={`Quantity of ${i.name}`}>
                        <button type="button" aria-label="One less" onClick={() => cart.setQuantity(i.id, i.quantity - 1)}>
                          −
                        </button>
                        <span>{i.quantity}</span>
                        <button
                          type="button"
                          aria-label="One more"
                          disabled={i.quantity >= (i.max ?? 10)}
                          onClick={() => cart.setQuantity(i.id, i.quantity + 1)}
                        >
                          +
                        </button>
                      </div>
                      <button type="button" className="link-btn" onClick={() => cart.remove(i.id)}>
                        Remove
                      </button>
                    </div>
                  </div>
                </li>
              ))}
            </ul>

            <footer className="drawer__foot">
              <div className="sum-row">
                <span>Items ({cart.count})</span>
                <span>{formatINR(cart.subtotal)}</span>
              </div>
              {cart.savings > 0 && (
                <div className="sum-row sum-row--save">
                  <span>You save</span>
                  <span>{formatINR(cart.savings)}</span>
                </div>
              )}
              <div className="sum-row">
                <span>Delivery</span>
                <span>Free</span>
              </div>
              <div className="sum-row sum-row--total">
                <span>Total</span>
                <span>{formatINR(cart.subtotal)}</span>
              </div>
              <button type="button" className="btn btn--primary btn--block" onClick={onCheckout}>
                Checkout
              </button>
            </footer>
          </>
        )}
      </aside>
    </div>
  )
}
