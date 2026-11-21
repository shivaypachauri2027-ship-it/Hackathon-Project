export function BoltIcon({ size = 22 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="8" fill="var(--marigold)" />
      <path d="M18 4 8 18h7l-2 10 11-15h-7z" fill="var(--indigo-900)" />
    </svg>
  )
}

function SearchIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true">
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" strokeLinecap="round" />
    </svg>
  )
}

function CartIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M3 4h2l2.4 11.2a1.5 1.5 0 0 0 1.5 1.2h8.6a1.5 1.5 0 0 0 1.5-1.1L21 8H6.2" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="9.5" cy="20" r="1.3" />
      <circle cx="17.5" cy="20" r="1.3" />
    </svg>
  )
}

export default function Navbar({ query, onQueryChange, cartCount = 0, onCartClick, onHome }) {
  return (
    <header className="nav">
      <div className="nav__inner">
        <a
          className="brand"
          href="/"
          aria-label="InstaStock home"
          onClick={(e) => {
            if (onHome) {
              e.preventDefault()
              onHome()
            }
          }}
        >
          <BoltIcon />
          <span>InstaStock</span>
        </a>

        <form className="search" role="search" onSubmit={(e) => e.preventDefault()}>
          <SearchIcon />
          <input
            type="search"
            value={query}
            onChange={(e) => onQueryChange(e.target.value)}
            placeholder="Search earbuds, kadhai, cricket bat…"
            aria-label="Search products"
          />
        </form>

        <button
          type="button"
          className="cart-btn"
          onClick={onCartClick}
          disabled={!onCartClick}
          title={onCartClick ? 'Open cart' : 'Cart arrives in Phase 3'}
        >
          <CartIcon />
          <span className="cart-btn__label">Cart</span>
          <span className="cart-btn__count" aria-label={`${cartCount} items in cart`}>{cartCount}</span>
        </button>
      </div>
    </header>
  )
}
