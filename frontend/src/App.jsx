import { useEffect, useState } from 'react'
import CartDrawer from './components/CartDrawer.jsx'
import Navbar from './components/Navbar.jsx'
import StatusBar from './components/StatusBar.jsx'
import CheckoutPage from './pages/CheckoutPage.jsx'
import DemoPage from './pages/DemoPage.jsx'
import EventsPage from './pages/EventsPage.jsx'
import OrderSuccessPage from './pages/OrderSuccessPage.jsx'
import StorePage from './pages/StorePage.jsx'
import useCart from './useCart.js'
import { parseQuery } from './utils/parseQuery.js'

const DEFAULT_CITY = 'Bengaluru'
const CITY_KEY = 'instastock.city'

function savedCity() {
  try {
    return localStorage.getItem(CITY_KEY) || DEFAULT_CITY
  } catch {
    return DEFAULT_CITY
  }
}

export default function App() {
  const [query, setQuery] = useState('')
  const [city, setCity] = useState(savedCity)
  const [view, setView] = useState('store') // 'store' | 'checkout' | 'success' | 'events' | 'demo'
  const [smartFilters, setSmartFilters] = useState(null) // what plain-words search understood
  const [cartOpen, setCartOpen] = useState(false)
  const [lastOrder, setLastOrder] = useState(null)
  const [toast, setToast] = useState('')
  const cart = useCart()

  // Hide the toast message after 2.5 seconds
  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(''), 2500)
    return () => clearTimeout(t)
  }, [toast])

  // Each screen starts at the top
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [view])

  function changeCity(next) {
    setCity(next)
    try {
      localStorage.setItem(CITY_KEY, next)
    } catch {
      // private browsing: just don't remember it
    }
  }

  function addToCart(product) {
    cart.add(product)
    setToast(`Added to cart: ${product.name}`)
  }

  function goToStore() {
    setView('store')
  }

  // Enter in the search box: "earphones under 2000 in Pune" -> text + filters
  function searchInPlainWords(text) {
    const parsed = parseQuery(text)
    setView('store')
    if (!parsed.changed) return // just words: the normal live search already covers it
    setQuery(parsed.text)
    if (parsed.city) changeCity(parsed.city)
    setSmartFilters({ ...parsed, id: Date.now() })
  }

  return (
    <div className="app">
      <Navbar
        query={query}
        onQueryChange={(q) => {
          setQuery(q)
          setSmartFilters(null)
          setView('store')
        }}
        onSearchSubmit={searchInPlainWords}
        cartCount={cart.count}
        onCartClick={() => setCartOpen(true)}
        onHome={goToStore}
        onEventsClick={() => setView('events')}
        onDemoClick={() => setView('demo')}
        view={view}
      />

      <main className="app__main">
        {view === 'store' && (
          <StorePage
            query={query}
            onClearQuery={() => setQuery('')}
            city={city}
            onCityChange={changeCity}
            onAddToCart={addToCart}
            cartQuantities={cart.quantities}
            smartFilters={smartFilters}
            onClearSmart={() => setSmartFilters(null)}
          />
        )}
        {view === 'checkout' && (
          <CheckoutPage
            city={city}
            cart={cart}
            onBack={goToStore}
            onPlaced={(order) => {
              cart.clear()
              setLastOrder(order)
              setView('success')
            }}
          />
        )}
        {view === 'success' && lastOrder && <OrderSuccessPage initialOrder={lastOrder} onContinue={goToStore} />}
        {view === 'events' && <EventsPage />}
        {view === 'demo' && <DemoPage city={city} />}
      </main>

      <CartDrawer
        open={cartOpen}
        onClose={() => setCartOpen(false)}
        cart={cart}
        city={city}
        onCheckout={() => {
          setCartOpen(false)
          setView('checkout')
        }}
      />

      {toast && (
        <div className="toast" role="status">
          {toast}
        </div>
      )}

      <StatusBar />
    </div>
  )
}
