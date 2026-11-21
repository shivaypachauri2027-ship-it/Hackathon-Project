import { useState } from 'react'
import { api } from '../api.js'
import { formatINR } from '../utils/format.js'

// Speeds up live demos: fills the form with a realistic address
const DEMO_CUSTOMER = {
  name: 'Ananya Rao',
  phone: '9876543210',
  address: 'Flat 304, Lakeview Apartments, 4th Cross, 2nd Main Road',
}

function validate(form) {
  const errors = {}
  if (form.name.trim().length < 2) errors.name = 'Enter your full name.'
  if (!/^[6-9]\d{9}$/.test(form.phone.replace(/\D/g, '').slice(-10))) errors.phone = 'Enter a 10-digit mobile number.'
  if (form.address.trim().length < 10) errors.address = 'Enter your full address (at least 10 characters).'
  return errors
}

export default function CheckoutPage({ city, cart, onBack, onPlaced }) {
  const [form, setForm] = useState({ name: '', phone: '', address: '' })
  const [showErrors, setShowErrors] = useState(false)
  const [placing, setPlacing] = useState(false)
  const [failure, setFailure] = useState(null) // { message, problems }

  const errors = validate(form)
  const update = (field) => (e) => setForm({ ...form, [field]: e.target.value })

  async function placeOrder(e) {
    e.preventDefault()
    setShowErrors(true)
    if (Object.keys(errors).length > 0 || placing) return

    setPlacing(true)
    setFailure(null)
    try {
      const order = await api.placeOrder({
        city,
        customer: form,
        items: cart.items.map((i) => ({ product_id: i.id, quantity: i.quantity })),
      })
      onPlaced(order)
    } catch (err) {
      setFailure({ message: err.message, problems: err.problems || [] })
      setPlacing(false)
    }
  }

  if (cart.items.length === 0) {
    return (
      <section className="page">
        <div className="notice">
          <h3>Your cart is empty</h3>
          <p>Add a few products, then come back to check out.</p>
          <button type="button" className="btn btn--primary" onClick={onBack}>
            Back to the store
          </button>
        </div>
      </section>
    )
  }

  return (
    <section className="page">
      <button type="button" className="link-btn back-link" onClick={onBack}>
        ← Back to the store
      </button>
      <h1 className="page__title">Checkout</h1>

      {failure && (
        <div className="notice notice--error checkout-error" role="alert">
          <h3>{failure.problems.length ? 'Some items just sold out' : 'The order could not be placed'}</h3>
          {failure.problems.length > 0 ? (
            <>
              <ul>
                {failure.problems.map((p) => (
                  <li key={p.product_id}>
                    <strong>{p.name}</strong>: you asked for {p.requested}, only {p.available} left in {city}.
                  </li>
                ))}
              </ul>
              <p>Nothing was charged and no stock was held. Update your cart and try again.</p>
              <button
                type="button"
                className="btn btn--primary"
                onClick={() => {
                  cart.applyAvailability(failure.problems)
                  setFailure(null)
                }}
              >
                Update my cart to what’s available
              </button>
            </>
          ) : (
            <p>{failure.message}</p>
          )}
        </div>
      )}

      <div className="checkout">
        <form id="checkout-form" className="panel" onSubmit={placeOrder} noValidate>
          <div className="panel__head">
            <h2>Delivery details</h2>
            <button type="button" className="link-btn" onClick={() => setForm(DEMO_CUSTOMER)}>
              Use demo details
            </button>
          </div>

          <label className="field">
            <span>Full name</span>
            <input value={form.name} onChange={update('name')} autoComplete="name" />
            {showErrors && errors.name && <small className="field__error">{errors.name}</small>}
          </label>

          <label className="field">
            <span>Mobile number</span>
            <input value={form.phone} onChange={update('phone')} inputMode="tel" autoComplete="tel" placeholder="98765 43210" />
            {showErrors && errors.phone && <small className="field__error">{errors.phone}</small>}
          </label>

          <label className="field">
            <span>Address</span>
            <textarea value={form.address} onChange={update('address')} rows={3} autoComplete="street-address" />
            {showErrors && errors.address && <small className="field__error">{errors.address}</small>}
          </label>

          <div className="field">
            <span>City</span>
            <p className="field__static">
              {city} <span className="muted">(change it in the store headline)</span>
            </p>
          </div>

          <div className="field">
            <span>Payment</span>
            <p className="field__static">Cash on delivery</p>
          </div>
        </form>

        <aside className="panel summary">
          <h2>Order summary</h2>
          <ul className="summary__lines">
            {cart.items.map((i) => (
              <li key={i.id}>
                <span>
                  {i.name} <span className="muted">× {i.quantity}</span>
                </span>
                <span>{formatINR(i.price * i.quantity)}</span>
              </li>
            ))}
          </ul>
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
          <button type="submit" form="checkout-form" className="btn btn--primary btn--block" disabled={placing}>
            {placing ? 'Placing order…' : `Place order (${formatINR(cart.subtotal)})`}
          </button>
          <p className="summary__note muted">Stock is reserved the moment you place the order.</p>
        </aside>
      </div>
    </section>
  )
}
