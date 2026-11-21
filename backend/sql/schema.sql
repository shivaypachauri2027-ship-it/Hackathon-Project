-- =====================================================================
-- InstaStock database schema (PostgreSQL = the source of truth)
-- Safe to run many times: every statement uses IF NOT EXISTS.
-- Tables for later phases (orders, outbox_events, event_log) are created
-- now so we never have to change the database in the middle of the night.
-- =====================================================================

-- Cities where the chain has a store
CREATE TABLE IF NOT EXISTS cities (
    name        TEXT PRIMARY KEY,
    sort_order  INTEGER NOT NULL
);

-- The product catalog
CREATE TABLE IF NOT EXISTS products (
    id            INTEGER PRIMARY KEY,
    sku           TEXT UNIQUE NOT NULL,
    name          TEXT NOT NULL,
    brand         TEXT NOT NULL,
    category      TEXT NOT NULL,
    price         INTEGER NOT NULL CHECK (price >= 0),          -- in rupees
    mrp           INTEGER NOT NULL CHECK (mrp >= price),
    rating        NUMERIC(2,1) NOT NULL DEFAULT 0,
    rating_count  INTEGER NOT NULL DEFAULT 0,
    image_url     TEXT,
    description   TEXT,
    tags          TEXT[] NOT NULL DEFAULT '{}',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Stock of every product in every city.
--   on_hand  = units physically in the store
--   reserved = units promised to orders that are not finalised yet
--   available to sell = on_hand - reserved
-- The CHECK constraints are a second safety net: even buggy code can never
-- push stock below zero or reserve more than exists.
CREATE TABLE IF NOT EXISTS inventory (
    product_id  INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    city        TEXT    NOT NULL REFERENCES cities(name),
    on_hand     INTEGER NOT NULL CHECK (on_hand >= 0),
    reserved    INTEGER NOT NULL DEFAULT 0 CHECK (reserved >= 0),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (product_id, city),
    CONSTRAINT reserved_not_more_than_on_hand CHECK (reserved <= on_hand)
);

-- Orders (Phase 3)
CREATE TABLE IF NOT EXISTS orders (
    id              BIGSERIAL PRIMARY KEY,
    order_number    TEXT UNIQUE NOT NULL,
    customer_name   TEXT NOT NULL,
    phone           TEXT NOT NULL,
    address         TEXT NOT NULL,
    city            TEXT NOT NULL REFERENCES cities(name),
    total_amount    INTEGER NOT NULL CHECK (total_amount >= 0),
    payment_method  TEXT NOT NULL DEFAULT 'COD',
    status          TEXT NOT NULL DEFAULT 'PLACED'
                    CHECK (status IN ('PLACED', 'CONFIRMED', 'CANCELLED')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    confirmed_at    TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS order_items (
    order_id    BIGINT  NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id  INTEGER NOT NULL REFERENCES products(id),
    quantity    INTEGER NOT NULL CHECK (quantity > 0),
    unit_price  INTEGER NOT NULL CHECK (unit_price >= 0),
    PRIMARY KEY (order_id, product_id)
);

-- Transactional outbox (Phase 4): events are saved in the SAME transaction
-- as the order, then a publisher sends them to Kafka. If Kafka is down,
-- nothing is lost; the events wait here and are sent later.
CREATE TABLE IF NOT EXISTS outbox_events (
    id                BIGSERIAL PRIMARY KEY,
    topic             TEXT  NOT NULL,
    event_type        TEXT  NOT NULL,
    event_key         TEXT,
    payload           JSONB NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at      TIMESTAMPTZ,
    publish_attempts  INTEGER NOT NULL DEFAULT 0,
    last_error        TEXT
);

-- What each Kafka consumer did with each event (Phase 4 live events page)
CREATE TABLE IF NOT EXISTS event_log (
    id               BIGSERIAL PRIMARY KEY,
    consumer         TEXT NOT NULL,
    topic            TEXT NOT NULL,
    event_type       TEXT NOT NULL,
    event_key        TEXT,
    kafka_partition  INTEGER,
    kafka_offset     BIGINT,
    detail           TEXT,
    processed_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_products_category ON products (category);
CREATE INDEX IF NOT EXISTS idx_inventory_city ON inventory (city);
CREATE INDEX IF NOT EXISTS idx_orders_created ON orders (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_outbox_unpublished ON outbox_events (id) WHERE published_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_event_log_time ON event_log (processed_at DESC);
