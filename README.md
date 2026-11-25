# Common Table

Common Table is a Flask + SQLite community food-support directory with a live nearby map.

## Features

- Search curated SQLite listings by name, address, city, postal code, or description.
- Filter curated listings by resource type and open-now hours.
- Find mapped food banks, soup kitchens, and food-sharing locations within a 500 m straight-line radius of the browser's current GPS location.
- Display the user, nearby locations, and search radius on an interactive Leaflet map.
- Select a result or map marker to draw a driving route from the current location.
- Admin login and add/edit/verify/delete controls for curated directory records.

The live search queries OpenStreetMap's Overpass service. Coverage depends on what local contributors have mapped, so results may be incomplete or unverified. The bundled demo rows are not geocoded and should not be represented as real nearby services. OSM queries and map tiles need internet access. GPS permission works on localhost and HTTPS origins.

## Run locally (Windows / VS Code)

1. Open this folder in VS Code.
2. Create and activate a virtual environment:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. Install and start:

   ```powershell
   pip install -r requirements.txt
   python app.py
   ```

4. Visit <http://127.0.0.1:5000>, then choose **Find near my location** and allow location access.

The app uses `common_table.db` in this folder. If it is missing, the app creates the resources table and two labeled demo records.

## Admin demo login

- URL: <http://127.0.0.1:5000/admin/login>
- Username: `admin`
- Password: `ChangeMe123!`

These are local demo credentials. Before deployment, set `ADMIN_USERNAME`, `ADMIN_PASSWORD_HASH`, and a unique `SECRET_KEY`. `ADMIN_PASSWORD_HASH` must be a Werkzeug password hash; generate one with:

```powershell
python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('your-password'))"
```

## API

- `GET /api/resources?q=pantry&type=Food%20pantry&open_now=1` searches the curated SQLite directory.
- `GET /api/nearby-food?lat=12.97&lon=77.59` searches mapped food-support locations within 500 m.
- `GET /api/route?from_lat=12.97&from_lon=77.59&to_lat=12.971&to_lon=77.591` returns a driving route geometry.

The route service returns driving routes; the 500 m radius is measured in a straight line. Route distance can be longer. Public map and routing services are best-effort and may be unavailable or rate-limited.

## Data attribution and limitations

Map tiles and local food-support features are attributed to OpenStreetMap contributors in the UI. Live map results are not a guaranteed real-time or complete registry and should be confirmed with providers. The route endpoint sends the user's coordinates and selected destination coordinates to the public OSRM routing service. Use a hosted commercial or self-managed data/routing provider for production traffic. Before public deployment, add CSRF protection, secure session settings, HTTPS, backups, and production-grade admin credential handling.
