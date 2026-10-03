# UrbanShield

Geospatial infrastructure risk dashboard and API for a synthetic city dataset.
The demo includes an interactive map, risk filters, maintenance priorities, API
documentation, and a data-backed assistant.

## Run Locally with Docker

From PowerShell, run the full stack from the `urbanshield` directory:

```powershell
cd .\urbanshield
$env:API_PORT='8010'
$env:FRONTEND_PORT='8080'
$env:ASSISTANT_PORT='8001'
docker compose up --build -d
```

Open the dashboard at http://localhost:8080. The dashboard includes API Docs
and the assistant. Detailed project documentation is in
[`urbanshield/README.md`](urbanshield/README.md).

## Free Render Demo

The root `Dockerfile` and `render.yaml` configure one free Docker web service.
It uses the bundled CSV data, so a hosted PostGIS database is not required for
the demo.

1. Publish the workspace root (the folder containing this README and
   `render.yaml`) to a GitHub repository. The `.gitignore` files exclude local
   environments and secrets while keeping the small runtime demo datasets.
2. In Render, select **New > Blueprint** and connect that repository.
3. Render reads `render.yaml` and creates the `urbanshield-demo` web service.
   Open the generated `onrender.com` address after deployment.

Render's free web services spin down after 15 minutes without traffic and may
take about a minute to wake up. The assistant uses live project data when no
external AI credits are configured. The dataset is synthetic and intended for
demonstration, not operational decisions.