import { formatINR } from '../utils/format.js'

export const PRICE_RANGES = [
  { id: 'any', label: 'Any price', min: null, max: null },
  { id: 'u500', label: `Under ${formatINR(500)}`, min: null, max: 499 },
  { id: '500', label: `${formatINR(500)} to ${formatINR(1999)}`, min: 500, max: 1999 },
  { id: '2000', label: `${formatINR(2000)} to ${formatINR(9999)}`, min: 2000, max: 9999 },
  { id: '10000', label: `${formatINR(10000)} to ${formatINR(49999)}`, min: 10000, max: 49999 },
  { id: '50000', label: `${formatINR(50000)} and above`, min: 50000, max: null },
]

const toNumber = (v) => (v === '' ? null : Math.max(0, Number(v)))

export default function FilterSidebar({ open, minPrice, maxPrice, onPriceChange, inStock, onInStockChange, city, onReset }) {
  const activeRange = PRICE_RANGES.find((r) => r.min === minPrice && r.max === maxPrice)

  return (
    <aside className={`filters${open ? ' filters--open' : ''}`} aria-label="Filters">
      <fieldset className="filters__group">
        <legend>Price</legend>
        {PRICE_RANGES.map((r) => (
          <label key={r.id} className="radio">
            <input
              type="radio"
              name="price"
              checked={activeRange?.id === r.id}
              onChange={() => onPriceChange(r.min, r.max)}
            />
            <span>{r.label}</span>
          </label>
        ))}
        <div className="price-inputs">
          <label>
            <span>Min ₹</span>
            <input
              type="number"
              inputMode="numeric"
              min="0"
              value={minPrice ?? ''}
              onChange={(e) => onPriceChange(toNumber(e.target.value), maxPrice)}
            />
          </label>
          <label>
            <span>Max ₹</span>
            <input
              type="number"
              inputMode="numeric"
              min="0"
              value={maxPrice ?? ''}
              onChange={(e) => onPriceChange(minPrice, toNumber(e.target.value))}
            />
          </label>
        </div>
      </fieldset>

      <fieldset className="filters__group">
        <legend>Availability</legend>
        <label className="check">
          <input type="checkbox" checked={inStock} onChange={(e) => onInStockChange(e.target.checked)} />
          <span>Hide items out of stock in {city}</span>
        </label>
      </fieldset>

      <button type="button" className="btn btn--ghost" onClick={onReset}>
        Clear all filters
      </button>
    </aside>
  )
}
