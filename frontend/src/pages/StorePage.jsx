import { useEffect, useRef, useState } from 'react'
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

const LIVE_MS = 5000 // how often the store quietly re-checks stock

export default function StorePage({
  query, onClearQuery, city, onCityChange, onAddToCart, cartQuantities = {}, smartFilters, onClearSmart,
}) {
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
  const [flashIds, setFlashIds] = useState(() => new Set())

  const q = useDebounced(query.trim(), 300)
  const params = { q, category, city, min_price: minPrice, max_price: maxPrice, in_stock: inStock, sort }
  const paramsKey = JSON.stringify(params)
  const latest = useRef({ paramsKey, result: null })
  latest.current.paramsKey = paramsKey
  latest.current.result = result

  // Plain-words search ("earphones under 2000 in Pune"): apply what the parser understood
  useEffect(() => {
    if (!smartFilters) return
    setCategory(smartFilters.category || '')
    setMinPrice(smartFilters.min)
    setMaxPrice(smartFilters.max)
    setInStock(Boolean(smartFilters.inStock))
    setSort(smartFilters.sort || 'relevance')
  }, [smartFilters?.id]) // eslint-disable-line react-hooks/exhaustive-deps

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
  }, [paramsKey, reloadKey]) // eslint-disable-line react-hooks/exhaustive-deps

  // Live stock: every 5 s (while this tab is visible) quietly fetch the same list again.
  // Cards whose stock changed flash, so you can see other people's orders land.
  useEffect(() => {
    const timer = setInterval(async () => {
      if (document.visibilityState !== 'visible') return
      const askedFor = latest.current.paramsKey
      try {
        const data = await api.products(JSON.parse(askedFor))
        if (latest.current.paramsKey !== askedFor) return // filters changed meanwhile
        const before = new Map((latest.current.result?.items || []).map((p) => [p.id, p.stock_in_city]))
        const changed = data.items.filter((p) => before.has(p.id) && before.get(p.id) !== p.stock_in_city).map((p) => p.id)
        setResult(data)
        if (changed.length) {
          setFlashIds(new Set(changed))
          setTimeout(() => setFlashIds(new Set()), 2500)
        }
      } catch {
        // a missed refresh is fine; the next one will try again
      }
    }, LIVE_MS)
    return () => clearInterval(timer)
  }, [])

  function resetFilters() {
    setCategory('')
    setMinPrice(null)
    setMaxPrice(null)
    setInStock(false)
    setSort('relevance')
    onClearQuery()
    onClearSmart?.()
  }

  // Category counts: live from OpenSearch (they follow the search, price and stock
  // filters); with the PostgreSQL fallback, the plain catalogue totals.
  const facets = result?.facets?.categories
  const facetCount = facets ? Object.fromEntries(facets.map((f) => [f.name, f.count])) : null
  const countFor = (c) => (facetCount ? facetCount[c.name] || 0 : c.count)
  const totalProducts = meta.categories.reduce((sum, c) => sum + countFor(c), 0)

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
            All <span>{totalProducts}</span>
          </button>
          {meta.categories.map((c) => (
            <button
              key={c.name}
              type="button"
              className={`chip${category === c.name ? ' chip--active' : ''}${countFor(c) === 0 ? ' chip--empty' : ''}`}
              onClick={() => setCategory(c.name)}
            >
              {c.name} <span>{countFor(c)}</span>
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

        <section className="results">
          {smartFilters && (
            <div className="understood" role="status">
              <span className="understood__label">Understood:</span>
              <ul className="understood__list">
                {smartFilters.understood.map((label) => (
                  <li key={label}>{label}</li>
                ))}
              </ul>
              <button type="button" className="understood__clear" onClick={resetFilters}>
                Clear
              </button>
            </div>
          )}
          <div className="results__bar" aria-live="polite">
            <div>
              <h2 className="results__title">
                {result && !error
                  ? `${result.total} ${result.total === 1 ? 'product' : 'products'}${q ? ` for “${q}”` : ''} in ${city}`
                  : 'Products'}
              </h2>
              {result && !error && (
                <p className="results__source" title={result.search_mode}>
                  <span className="live-pill" title="Stock on this page refreshes every 5 seconds">
                    <span className="live-pill__dot" aria-hidden="true" />
                    Live stock
                  </span>
                  Served by {sourceLabel(result.source)}
                  {result.search_mode ? `, ${result.search_mode}` : ''}
                </p>
              )}
              {result && !error && result.did_you_mean && (
                <p className="results__fix">
                  Showing results for “<strong>{result.did_you_mean}</strong>”. You typed “{q}”.
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
                <ProductCard
                  key={p.id}
                  product={p}
                  onAdd={onAddToCart}
                  cartQty={cartQuantities[p.id] || 0}
                  flash={flashIds.has(p.id)}
                />
              ))}
            </div>
          )}
        </section>
      </div>
    </>
  )
}
