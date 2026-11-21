# InstaStock

An event-driven online store for a retail chain going digital across India.

- **PostgreSQL** (Aiven) is the source of truth for products, stock and orders, and stops the last unit from being sold twice.
- **Apache Kafka** (Aiven) carries an event for every order; workers react to it.
- **OpenSearch** (Aiven) powers fast, typo-tolerant search with category, price and city filters.

Stack: React + Vite · Python + FastAPI · Aiven PostgreSQL · Aiven Kafka · Aiven OpenSearch

> This README grows with each phase. The full version (architecture diagram, screenshots,
> demo guide) is written in Phase 7.

## Run it locally

You need Python 3.11–3.13, Node.js 20.19+ (22 LTS recommended) and Git.

**Backend** (terminal 1)

```bash
cd backend
python -m venv .venv
# Windows:  .venv\Scripts\activate      macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # Windows: copy .env.example .env   (then fill in values)
uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

**Frontend** (terminal 2)

```bash
cd frontend
npm install
npm run dev
```

Store: http://localhost:5173

**Check cloud services** (backend terminal, venv active)

```bash
python scripts/check_services.py
```

## Project status

- [x] Phase 1: skeleton storefront + API (catalog from JSON)
- [ ] Phase 2: PostgreSQL catalog and filters
- [ ] Phase 3: cart, checkout, oversell protection
- [ ] Phase 4: Kafka events and workers
- [ ] Phase 5: OpenSearch typo-tolerant search and sync
- [ ] Phase 6: UI polish
- [ ] Phase 7: documentation
- [ ] Phase 8: demo prep

## Team

Code Verse · DSATM
