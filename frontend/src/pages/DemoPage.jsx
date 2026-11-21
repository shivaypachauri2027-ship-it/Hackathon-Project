import { useEffect, useState } from 'react'
import { api } from '../api.js'
import SyncMonitor from '../components/SyncMonitor.jsx'

const SONY = 5 // Sony WH-1000XM5: the default demo product

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

// Polls until OpenSearch shows the same stock as PostgreSQL (or the time runs out)
async function waitForSearch(productId, city, maxMs) {
  const started = Date.now()
  while (Date.now() - started < maxMs) {
    try {
      const s = await api.syncStatus(productId, city)
      if (s.in_sync || !s.search_enabled) return true
    } catch {
      // try again
    }
    await sleep(300)
  }
  return false
}

function ProductPicker({ products, value, onChange }) {
  return (
    <select value={value} onChange={(e) => onChange(Number(e.target.value))}>
      {products.map((p) => (
        <option key={p.id} value={p.id}>
          {p.name}
        </option>
      ))}
    </select>
  )
}

function CityPicker({ cities, value, onChange }) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)}>
      {cities.map((c) => (
        <option key={c} value={c}>
          {c}
        </option>
      ))}
    </select>
  )
}

export default function DemoPage({ city: startCity }) {
  const [products, setProducts] = useState([])
  const [cities, setCities] = useState([startCity])
  const [error, setError] = useState('')

  // Flash sale
  const [saleProduct, setSaleProduct] = useState(SONY)
  const [saleCity, setSaleCity] = useState(startCity)
  const [shopperCount, setShopperCount] = useState(20)
  const [shoppers, setShoppers] = useState([])
  const [running, setRunning] = useState(false)
  const [saleSyncAt, setSaleSyncAt] = useState(null)

  // Restock
  const [stockProduct, setStockProduct] = useState(SONY)
  const [stockCity, setStockCity] = useState(startCity)
  const [quantity, setQuantity] = useState(5)
  const [restockResult, setRestockResult] = useState(null)
  const [restockSyncAt, setRestockSyncAt] = useState(null)

  useEffect(() => {
    api.meta().then((m) => setCities(m.cities)).catch(() => {})
    api
      .products({ city: startCity, sort: 'relevance' })
      .then((r) => setProducts([...r.items].sort((a, b) => a.name.localeCompare(b.name))))
      .catch((e) => setError(e.message))
  }, [startCity])

  const update = (no, patch) => setShoppers((list) => list.map((s) => (s.no === no ? { ...s, ...patch } : s)))

  async function startFlashSale() {
    setError('')
    setSaleSyncAt(null)
    setShoppers([])
    setRunning('setup')

    try {
      // 1) Make exactly ONE unit available (this also publishes STOCK_CHANGED to Kafka)
      await api.changeStock({ product_id: saleProduct, city: saleCity, set_available: 1 })
      // Wait (max 8 s) until search shows that 1 unit too, so the sync view after the sale is honest
      await waitForSearch(saleProduct, saleCity, 8000)
    } catch (e) {
      setError(e.message)
      setRunning(false)
      return
    }

    setRunning('buying')
    const list = Array.from({ length: shopperCount }, (_, i) => ({ no: i + 1, state: 'waiting' }))
    setShoppers(list)

    // 2) Every shopper sends a real order to the API at the same moment
    let wonAt = null
    await Promise.all(
      list.map(async ({ no }) => {
        const t0 = performance.now()
        try {
          const order = await api.placeOrder({
            city: saleCity,
            customer: {
              name: `Flash shopper ${no}`,
              phone: String(9800000000 + no),
              address: 'Flash sale demo, MG Road',
            },
            items: [{ product_id: saleProduct, quantity: 1 }],
          })
          wonAt = Date.now()
          update(no, { state: 'won', order: order.order_number, ms: performance.now() - t0 })
        } catch (e) {
          update(no, { state: e.status === 409 ? 'lost' : 'error', message: e.message, ms: performance.now() - t0 })
        }
      }),
    )
    setRunning(false)
    setSaleSyncAt(wonAt ?? Date.now()) // time the search sync from the winning order
  }

  async function restock() {
    setError('')
    setRestockResult(null)
    try {
      const r = await api.changeStock({ product_id: stockProduct, city: stockCity, add: quantity })
      setRestockResult(r)
      setRestockSyncAt(Date.now())
    } catch (e) {
      setError(e.message)
    }
  }

  const done = shoppers.length > 0 && !running
  const winners = shoppers.filter((s) => s.state === 'won').length
  const refused = shoppers.filter((s) => s.state === 'lost').length

  return (
    <section className="page demo">
      <h1 className="page__title">Demo tools</h1>
      <p className="page__lede">
        Run a flash sale on the last unit, or restock a product, then watch PostgreSQL and OpenSearch stay in sync
        through Kafka. These tools change real stock.
      </p>

      {error && (
        <div className="notice notice--error" role="alert">
          <h3>That didn’t work</h3>
          <p>{error}</p>
        </div>
      )}

      <div className="demo__grid">
        <div className="panel">
          <h2>Flash sale: many shoppers, one unit</h2>
          <p className="muted">
            Sets the stock to exactly 1, then fires every shopper’s order at the API at the same time. PostgreSQL’s row
            lock lets exactly one win.
          </p>
          <div className="demo__controls">
            <label className="field">
              <span>Product</span>
              <ProductPicker products={products} value={saleProduct} onChange={setSaleProduct} />
            </label>
            <label className="field">
              <span>City</span>
              <CityPicker cities={cities} value={saleCity} onChange={setSaleCity} />
            </label>
            <label className="field">
              <span>Shoppers</span>
              <select value={shopperCount} onChange={(e) => setShopperCount(Number(e.target.value))}>
                {[10, 20, 30].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <button type="button" className="btn btn--primary" onClick={startFlashSale} disabled={running || !products.length}>
            {running === 'setup' && 'Setting the stock to 1…'}
            {running === 'buying' && 'Shoppers are buying…'}
            {!running && 'Start flash sale'}
          </button>

          {shoppers.length > 0 && (
            <>
              {done && (
                <p className={`demo__verdict${winners === 1 ? ' demo__verdict--ok' : ''}`}>
                  {winners === 1
                    ? `1 of ${shoppers.length} shoppers got the last unit. ${refused} were told it’s sold out. No overselling.`
                    : `${winners} orders succeeded. Expected exactly 1: check the stock and try again.`}
                </p>
              )}
              <ol className="shoppers">
                {shoppers.map((s) => (
                  <li key={s.no} className={`shopper shopper--${s.state}`}>
                    <span className="shopper__name">Shopper {s.no}</span>
                    <span className="shopper__state">
                      {s.state === 'waiting' && 'Buying…'}
                      {s.state === 'won' && `Got it: ${s.order}`}
                      {s.state === 'lost' && 'Sold out'}
                      {s.state === 'error' && 'Error'}
                    </span>
                    {s.ms !== undefined && <span className="shopper__ms">{Math.round(s.ms)} ms</span>}
                  </li>
                ))}
              </ol>
              <SyncMonitor productId={saleProduct} city={saleCity} startedAt={saleSyncAt} />
            </>
          )}
        </div>

        <div className="panel">
          <h2>Restock</h2>
          <p className="muted">
            Adds units in one city. A STOCK_CHANGED event goes through Kafka and search shows the new stock.
          </p>
          <label className="field">
            <span>Product</span>
            <ProductPicker products={products} value={stockProduct} onChange={setStockProduct} />
          </label>
          <div className="demo__controls">
            <label className="field">
              <span>City</span>
              <CityPicker cities={cities} value={stockCity} onChange={setStockCity} />
            </label>
            <label className="field">
              <span>Units to add</span>
              <input
                type="number"
                min="1"
                max="100"
                value={quantity}
                onChange={(e) => setQuantity(Math.max(1, Math.min(100, Number(e.target.value) || 1)))}
              />
            </label>
          </div>
          <button type="button" className="btn btn--primary" onClick={restock} disabled={!products.length}>
            Restock
          </button>
          {restockResult && (
            <p className="demo__verdict demo__verdict--ok">
              Restocked. {restockResult.available} now available in {restockResult.city}.
            </p>
          )}
          <SyncMonitor productId={stockProduct} city={stockCity} startedAt={restockSyncAt} />
        </div>
      </div>
    </section>
  )
}
