import { useState } from 'react'
import { formatCount, formatINR } from '../utils/format.js'

const FULL_SHELF = 30 // stock level that fills the little meter

function StockLine({ inCity, city, stockByCity }) {
  if (inCity === 0) {
    const elsewhere = Object.entries(stockByCity)
      .filter(([c, n]) => c !== city && n > 0)
      .map(([c]) => c)
    return (
      <div className="stock stock--out">
        <p className="stock__text">Out of stock in {city}</p>
        {elsewhere.length > 0 && (
          <p className="stock__hint">
            Available in {elsewhere.slice(0, 2).join(', ')}
            {elsewhere.length > 2 && ` and ${elsewhere.length - 2} more`}
          </p>
        )}
      </div>
    )
  }

  const low = inCity <= 3
  const width = `${Math.max(6, Math.min(inCity / FULL_SHELF, 1) * 100)}%`
  return (
    <div className={`stock ${low ? 'stock--low' : 'stock--ok'}`}>
      <div className="stock__meter" aria-hidden="true">
        <span style={{ width }} />
      </div>
      <p className="stock__text">
        {low ? `Only ${inCity} left in ${city}` : `${inCity} in stock in ${city}`}
      </p>
    </div>
  )
}

export default function ProductCard({ product, onAdd, cartQty = 0 }) {
  const [imageFailed, setImageFailed] = useState(false)
  const {
    name, brand, price, mrp, discount_pct, rating, rating_count,
    image_url, stock_in_city, stock_by_city, city,
  } = product
  const out = stock_in_city === 0
  const allInCart = !out && cartQty >= Math.min(stock_in_city, 10)

  let buttonLabel = 'Add to cart'
  if (out) buttonLabel = 'Out of stock'
  else if (allInCart) buttonLabel = `All ${cartQty} in your cart`
  else if (cartQty > 0) buttonLabel = `Add one more (${cartQty} in cart)`

  return (
    <article className={`card${out ? ' card--out' : ''}`}>
      <div className="card__media">
        {image_url && !imageFailed ? (
          <img src={image_url} alt={name} loading="lazy" onError={() => setImageFailed(true)} />
        ) : (
          // Shown when the image CDN is unreachable (e.g. offline demo)
          <div className="card__fallback" aria-hidden="true">{brand}</div>
        )}
        {discount_pct > 0 && <span className="card__off">{discount_pct}% off</span>}
      </div>

      <div className="card__body">
        <p className="card__brand">{brand}</p>
        <h3 className="card__name" title={name}>{name}</h3>
        <p className="card__rating">
          <span className="rating-pill">{rating.toFixed(1)} ★</span>
          <span className="muted">{formatCount(rating_count)} ratings</span>
        </p>
        <p className="card__price">
          <strong>{formatINR(price)}</strong>
          {mrp > price && <s>{formatINR(mrp)}</s>}
        </p>
        <StockLine inCity={stock_in_city} city={city} stockByCity={stock_by_city} />
        {onAdd && (
          <button
            type="button"
            className={`btn card__add ${cartQty > 0 ? 'btn--ghost' : 'btn--primary'}`}
            disabled={out || allInCart}
            onClick={() => onAdd(product)}
          >
            {buttonLabel}
          </button>
        )}
      </div>
    </article>
  )
}
