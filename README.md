# NeuroEngage Outreach Dashboard

Auto-updating dashboard for NeuroEngage outreach events.  
Pulls data from Microsoft Forms / OneDrive and publishes to GitHub Pages automatically.

---

## How it works

1. Someone submits the Microsoft Forms outreach form
2. OneDrive Excel file updates automatically
3. GitHub Actions runs every 4 hours, downloads the latest Excel, regenerates the dashboard
4. Updated dashboard is live at your GitHub Pages URL instantly

---

## One-time setup (do this once)

### Step 1 — Create the GitHub repo

1. Go to [github.com](https://github.com) and click **New repository**
2. Name it: `neuroengage-dashboard`
3. Set it to **Public** (required for free GitHub Pages)
4. Do NOT initialize with a README (you already have these files)
5. Click **Create repository**
6. Upload all these files into the repo (drag and drop or use GitHub Desktop)

---

### Step 2 — Get your OneDrive sharing link

1. Go to OneDrive / SharePoint and find your Microsoft Forms Excel file
2. Right-click the file > **Share** > **Copy link**
3. Make sure the link is set to **"Anyone with the link can view"**
4. Copy that URL — you will need it in Step 3

---

### Step 3 — Add your OneDrive URL as a GitHub Secret

This keeps your URL private and out of your code.

1. In your GitHub repo, go to **Settings** (top menu)
2. Click **Secrets and variables** > **Actions** (left sidebar)
3. Click **New repository secret**
4. Name: `ONEDRIVE_URL`
5. Value: paste your OneDrive sharing link from Step 2
6. Click **Add secret**

---

### Step 4 — Enable GitHub Pages

1. In your GitHub repo, go to **Settings**
2. Click **Pages** (left sidebar)
3. Under **Source**, select **Deploy from a branch**
4. Branch: `main` | Folder: `/docs`
5. Click **Save**
6. After a minute, your dashboard will be live at:
   `https://YOUR-USERNAME.github.io/neuroengage-dashboard`

---

### Step 5 — Run it manually the first time

1. Go to your repo > **Actions** tab
2. Click **Regenerate NeuroEngage Dashboard** (left sidebar)
3. Click **Run workflow** > **Run workflow**
4. Wait about 1 minute — it will download your data and publish the dashboard
5. Visit your GitHub Pages URL to see it live!

---

## Changing the update schedule

The dashboard currently refreshes every 4 hours. To change this, edit:  
`.github/workflows/update_dashboard.yml`

Change the cron line:
```
'0 */4 * * *'   → every 4 hours
'0 * * * *'     → every hour
'0 0 * * *'     → once a day at midnight
'0 0 * * 1'     → once a week on Monday
```

---

## File structure

```
neuroengage-dashboard/
├── .github/
│   └── workflows/
│       └── update_dashboard.yml   ← GitHub Actions automation
├── data/
│   └── outreach_data.csv          ← auto-downloaded from OneDrive
├── docs/
│   └── index.html                 ← the live dashboard (served by GitHub Pages)
├── download_data.py               ← downloads Excel from OneDrive, converts to CSV
├── generate_dashboard.py          ← reads CSV, generates dashboard HTML
└── README.md                      ← this file
```

---

## Sharing the dashboard

Once live, share this link with your whole team:  
`https://YOUR-USERNAME.github.io/neuroengage-dashboard`

It works on any device, any browser, no login required.
