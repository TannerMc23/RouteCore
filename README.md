# RouteCore — Backend API

Flask + SQLite backend for the RouteCore logistics CRM.

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Seed the database with sample data (optional)
python seed.py

# 3. Start the server
python app.py
```

The API will be available at `http://localhost:5000`.

---

## Project Structure

```
routecore/
├── app.py            # Flask application & all API routes
├── database.py       # DB connection, schema creation
├── seed.py           # Sample data loader
├── requirements.txt  # Python dependencies
└── routecore.db      # SQLite file (auto-created on first run)
```

---

## API Reference

### Health

| Method | Endpoint  | Description        |
|--------|-----------|--------------------|
| GET    | /health   | Server health check|

---

### Shipments

| Method | Endpoint                  | Description            |
|--------|---------------------------|------------------------|
| GET    | /shipments                | List all shipments     |
| GET    | /shipments/:id            | Get one shipment       |
| POST   | /shipments                | Create a shipment      |
| PUT    | /shipments/:id            | Update a shipment      |
| DELETE | /shipments/:id            | Delete a shipment      |

**POST /shipments — Request body**
```json
{
  "customer_id": "CUST-001",
  "origin":      "New York, US",
  "destination": "Los Angeles, US",
  "status":      "Pending"
}
```

**Status values:** `Pending` | `In Transit` | `Delivered`

**Shipment response shape**
```json
{
  "id":          "SHP-0001",
  "customer_id": "CUST-001",
  "origin":      "New York, US",
  "destination": "Los Angeles, US",
  "status":      "Pending",
  "created_at":  "2025-04-22"
}
```

---

### Customers

| Method | Endpoint           | Description                          |
|--------|--------------------|--------------------------------------|
| GET    | /customers         | List all customers                   |
| GET    | /customers/:id     | Get customer + their shipments       |
| POST   | /customers         | Create a customer                    |
| DELETE | /customers/:id     | Delete a customer                    |

**POST /customers — Request body**
```json
{
  "name":  "Apex Logistics",
  "email": "ops@apexlogistics.com",
  "phone": "+1 (212) 555-0101",
  "notes": "Priority account"
}
```

---

## Connecting the Frontend

In the RouteCore frontend, replace the in-memory array with `fetch()` calls:

```javascript
// Load all shipments on page start
async function loadShipments() {
  const res = await fetch("http://localhost:5000/shipments");
  shipments = await res.json();
  renderShipments();
}

// Create a new shipment
async function addShipment(payload) {
  const res = await fetch("http://localhost:5000/shipments", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}

// Delete a shipment
async function deleteShipment(id) {
  await fetch(`http://localhost:5000/shipments/${id}`, { method: "DELETE" });
}

// Update a shipment
async function updateShipment(id, payload) {
  const res = await fetch(`http://localhost:5000/shipments/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}
```

---

## Error Responses

All errors return JSON with a descriptive message:

```json
{ "error": "Shipment not found" }
```

| Code | Meaning                        |
|------|--------------------------------|
| 200  | OK                             |
| 201  | Created                        |
| 400  | Bad request (invalid JSON)     |
| 404  | Resource not found             |
| 409  | Conflict (duplicate email)     |
| 422  | Validation error (missing field / bad value) |
