# Videxport Pricing Dashboard

Internal pricing-surveillance dashboard for the Videxport credit deal.
Tracks USDA Nogales shipping-point prices vs. Videxport realized prices.

Live URL: **https://andrewpelekis-lab.github.io/videxport-pricing/**

---

## Repo layout

```
.github/workflows/refresh.yml        # Auto-refreshes USDA data every Monday
scripts/refresh_usda.py              # USDA MARS API puller (IX_FV110, IX_FV120)
docs/
  index.html                         # Dashboard (password-gated, served by GitHub Pages)
  data/
    usda_master.csv                  # Written by the workflow; do not edit manually
    videxport_liquidations.csv       # Update this manually as new liquidations arrive
```

> **Why docs/data/ and not data/?**
> GitHub Pages only serves files inside the `docs/` folder. Putting data at the repo root
> would make it invisible to the dashboard's `fetch()` calls.

---

## One-time setup

### 1. Create the repository

Go to https://github.com/new and create:
```
Owner:      andrewpelekis-lab
Name:       videxport-pricing
Visibility: Public
```

### 2. Enable GitHub Pages

`Settings → Pages → Source: Deploy from a branch`
- Branch: `main`
- Folder: `/docs`

Save. The dashboard will be live at https://andrewpelekis-lab.github.io/videxport-pricing/ within ~60 seconds of your first push.

### 3. Add the USDA API key as a secret

`Settings → Secrets and variables → Actions → New repository secret`
```
Name:  USDA_API_KEY
Value: <your key from mymarketnews.ams.usda.gov → profile → API key>
```

### 4. Set the dashboard password

Generate the SHA-256 hash of your chosen password:

```bash
python3 -c "import hashlib; print(hashlib.sha256(b'YOUR_PASSWORD').hexdigest())"
```

Open `docs/index.html` and replace `REPLACE_ME_WITH_SHA256_HASH` (near the bottom of the `<script>` block) with the hex string you just generated.

> **Note:** The hash is visible in the page source — this is intentional. The gate is a "don't share this URL" signal, not real authentication.

### 5. Push everything to GitHub

```bash
cd C:\Users\andre\videxport
git init
git remote add origin https://github.com/andrewpelekis-lab/videxport-pricing.git
git add .
git commit -m "Initial scaffold"
git branch -M main
git push -u origin main
```

### 6. Run the first USDA refresh manually

GitHub → Actions tab → **Refresh USDA Data** → **Run workflow** → Run workflow

This populates `docs/data/usda_master.csv` for the first time. Check the run logs — it should end with a commit message like `Auto-refresh USDA data 2026-05-19`.

---

## Ongoing workflow

| Task | How |
|---|---|
| USDA data refresh | Automatic every Monday at 14:00 UTC |
| Force a refresh now | GitHub → Actions → Refresh USDA Data → Run workflow |
| Update Videxport liquidations | Edit `docs/data/videxport_liquidations.csv` via GitHub UI or commit locally, then push |
| Share the dashboard | Send partners the URL + password (verbally or via secure channel) |
| Rotate the dashboard password | Re-generate hash, update `docs/index.html`, push |

---

## Troubleshooting

**Refresh workflow failed**
Open GitHub → Actions → click the failed run → expand the failing step to read the logs.
Common causes: API key expired, MARS API down, network timeout.

**API key expired or rotated**
1. Regenerate at mymarketnews.ams.usda.gov → profile → API key
2. `Settings → Secrets → USDA_API_KEY → Update`
3. Re-run the workflow manually to confirm

**Dashboard shows "Could not load data"**
- On GitHub Pages: check that the workflow ran successfully and `docs/data/usda_master.csv` has real CSV content (not the placeholder comment)
- Locally: you must serve the files through a local HTTP server — `fetch()` does not work from `file://` URLs. Run `python3 -m http.server 8080` from the `docs/` folder and open `http://localhost:8080`

**Dashboard shows stale data after a refresh**
Hard-refresh: `Ctrl+Shift+R` (Windows) or `Cmd+Shift+R` (Mac).
The dashboard already uses `cache: 'no-store'` plus a `?t=` timestamp on every fetch, so a normal page refresh should pick up new data immediately.

**GitHub Pages not updating after a push**
Wait ~60 seconds. If still stale, check `Settings → Pages` to confirm the source is set to `main` / `/docs`.
