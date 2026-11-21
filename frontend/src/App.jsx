import { useState } from 'react'
import Navbar from './components/Navbar.jsx'
import StatusBar from './components/StatusBar.jsx'
import StorePage from './pages/StorePage.jsx'

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

  function changeCity(next) {
    setCity(next)
    try {
      localStorage.setItem(CITY_KEY, next)
    } catch {
      // private browsing: just don't remember it
    }
  }

  return (
    <div className="app">
      <Navbar query={query} onQueryChange={setQuery} cartCount={0} />
      <main className="app__main">
        <StorePage query={query} onClearQuery={() => setQuery('')} city={city} onCityChange={changeCity} />
      </main>
      <StatusBar />
    </div>
  )
}
