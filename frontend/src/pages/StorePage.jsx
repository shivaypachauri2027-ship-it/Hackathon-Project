import { useEffect, useState } from 'react'
import { api } from '../api.js'
import FilterSidebar from '../components/FilterSidebar.jsx'
import ProductCard from '../components/ProductCard.jsx'
import { sourceLabel } from '../utils/format.js'
import useDebounced from '../utils/useDebounced.js'

const SORTS = [
  { id: 'relevance', label: 'Relevance' },
  { id: 'price_asc', label: 'Price: low to high' },
  { id: 'price_desc', label: 'Price: high to low' },
  { id: 'rating', label: 'Customer rating' },
  { id: 'discount', label: 'Biggest discount' },
]

function SkeletonGrid() {
  return (
    <div className="grid" aria-hidden="true">
      {Array.from({ length: 8 }, (_, i) => (
        <div key={i} className="card card--skeleton">
          <div className="card__media" />
          <div className="card__body">
            <span className="sk sk--short" />
            <span className="sk" />
            <span className="sk sk--mid" />
          </div>
        </div>
      ))}
    </div>
  )
}

export default function StorePage({ query, onClearQuery, city, onCityChange, onAddToCart }) {
  const [meta, setMeta] = useState({ categories: [], cities: [city] })
  const [category, setCategory] = useState('')
  const [minPrice, setMinPrice] = useState(null)
  const [maxPrice, setMaxPrice] = useState(null)
  const [inStock, setInStock] = useState(false)
  const [sort, setSort] = useState('relevance')
  const [showFilters, setShowFilters] = useState(false) // only matters on phones

  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [reloadKey, setReloadKey] = useState(0)

  const q = useDebounced(query.trim(), 300)

  // Categories and cities for the filters (loaded once)
  useEffect(() => {
    api.meta().then(setMeta).catch(() => {})
  }, [reloadKey])

  // Products: reload whenever any filter changes
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError('')
    api
      .products(
        { q, category, city, min_price: minPrice, max_price: maxPrice, in_stock: inStock, sort },
        controller.signal,
      )
      .then((data) => {
        setResult(data)
        setLoading(false)
      })
      .catch((err) => {
        if (err.name === 'AbortError') return
        setError(err.message)
        setLoading(false)
      })
    return () => controller.abort()
  }, [q, category, city, minPrice, maxPrice, inStock, sort, reloadKey])

  function resetFilters() {
    setCategory('')
    setMinPrice(null)
    setMaxPrice(null)
    setInStock(false)
    setSort('relevance')
    onClearQuery()
  }

  const totalProducts = meta.categories.reduce((sum, c) => sum + c.count, 0)

  return (
    <>
      <section className="hero">
        <div className="hero__inner">
          <h1 className="hero__title">
            What’s in stock in{' '}
            {/* The visible text sizes itself to the city name; the real <select> sits invisibly on top */}
            <span className="city-select">
              <span className="city-select__label" aria-hidden="true">{city}</span>
              <select value={city} onChange={(e) => onCityChange(e.target.value)} aria-label="Choose your city">
                {meta.cities.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </span>
          </h1>
          <p className="hero__lede">
            Live counts from our {city} store. When someone orders, the number drops for everyone.
          </p>
        </div>

        <nav className="chips" aria-label="Categories">
          <button type="button" className={`chip${category === '' ? ' chip--active' : ''}`} onClick={() => setCategory('')}>
            All <span>{totalProducts || ''}</span>
          </button>
          {meta.categories.map((c) => (
            <button
              key={c.name}
              type="button"
              className={`chip${category === c.name ? ' chip--active' : ''}`}
              onClick={() => setCategory(c.name)}
            >
              {c.name} <span>{c.count}</span>
            </button>
          ))}
        </nav>
      </section>

      <div className="store">
        <button
          type="button"
          className="btn btn--ghost filters-toggle"
          aria-expanded={showFilters}
          onClick={() => setShowFilters((v) => !v)}
        >
          {showFilters ? 'Hide filters' : 'Show filters'}
        </button>
        <FilterSidebar
          open={showFilters}
          minPrice={minPrice}
          maxPrice={maxPrice}
          onPriceChange={(min, max) => {
            setMinPrice(min)
            setMaxPrice(max)
          }}
          inStock={inStock}
          onInStockChange={setInStock}
          city={city}
          onReset={resetFilters}
        />

        <section className="results" aria-live="polite">
          <div className="results__bar">
            <div>
              <h2 className="results__title">
                {result && !error
                  ? `${result.total} ${result.total === 1 ? 'product' : 'products'}${q ? ` for “${q}”` : ''} in ${city}`
                  : 'Products'}
              </h2>
              {result && !error && (
                <p className="results__source" title={result.search_mode}>
                  Served by {sourceLabel(result.source)}
                  {q && result.search_mode ? `, ${result.search_mode}` : ''}
                </p>
              )}
            </div>
            <label className="sort">
              <span>Sort by</span>
              <select value={sort} onChange={(e) => setSort(e.target.value)}>
                {SORTS.map((s) => (
                  <option key={s.id} value={s.id}>{s.label}</option>
                ))}
              </select>
            </label>
          </div>

          {error ? (
            <div className="notice notice--error" role="alert">
              <h3>The store couldn’t load products</h3>
              <p>{error}</p>
              <button type="button" className="btn btn--primary" onClick={() => setReloadKey((k) => k + 1)}>
                Try again
              </button>
            </div>
          ) : loading && !result ? (
            <SkeletonGrid />
          ) : result.items.length === 0 ? (
            <div className="notice">
              <h3>No products match{q ? ` “${q}”` : ' these filters'} in {city}</h3>
              <p>Check the spelling, widen the price range or switch city.</p>
              <button type="button" className="btn btn--primary" onClick={resetFilters}>
                Clear filters
              </button>
            </div>
          ) : (
            <div className={`grid${loading ? ' grid--updating' : ''}`}>
              {result.items.map((p) => (
                <ProductCard key={p.id} product={p} onAdd={onAddToCart} />
              ))}
            </div>
          )}
        </section>
      </div>
    </>
  )
}
