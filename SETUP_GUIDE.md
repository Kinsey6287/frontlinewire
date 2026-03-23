# FrontlineWire — Complete Setup Guide
### Get your site live in about 20 minutes. No coding required.

---

## What you'll end up with
- A live website at a free URL like `https://yourusername.github.io/frontlinewire`
- Conflict news pulled from BBC, Reuters, Al Jazeera, AP and more
- AI-written summaries of every story
- Automatic updates every 6 hours, forever, for free

---

## STEP 1 — Create a free GitHub account

1. Go to **https://github.com**
2. Click **Sign up** (top right)
3. Choose a username (this becomes part of your website URL)
4. Verify your email address

---

## STEP 2 — Create your repository (your site's home)

1. Once logged in, click the **+** button (top right) → **New repository**
2. Name it: `frontlinewire`
3. Set it to **Public** (required for free hosting)
4. Leave everything else as-is
5. Click **Create repository**

---

## STEP 3 — Upload your files

You received a ZIP file with these files:
```
index.html
style.css
app.js
data.json
update.py
.github/workflows/update.yml
```

**Upload them:**
1. In your new repository, click **uploading an existing file** (in the middle of the page)
2. Drag ALL the files into the upload area
   - Important: also drag the `.github` folder (you may need to drag its contents separately — see note below)
3. Scroll down and click **Commit changes**

> **Note on the .github folder:** GitHub's web uploader may not handle folders well.
> If you have trouble, use the GitHub Desktop app (free download at desktop.github.com)
> which makes dragging folders easy.

---

## STEP 4 — Get your free Claude API key

The update script uses Claude AI to summarize articles. You need a free API key.

1. Go to **https://console.anthropic.com**
2. Sign up for a free account
3. Go to **API Keys** in the left menu
4. Click **Create Key** → name it "frontlinewire" → click **Create**
5. **Copy the key immediately** — you won't see it again
   It looks like: `sk-ant-api03-...`

> **Cost:** The free tier gives you enough credits to run updates for several months.
> After that, API costs are very low — roughly $1–3/month at 6-hour update frequency.

---

## STEP 5 — Add your API key to GitHub (securely)

Your API key must be stored as a "Secret" so it's never visible publicly.

1. Go to your `frontlinewire` repository on GitHub
2. Click **Settings** (tab at the top)
3. In the left sidebar, click **Secrets and variables** → **Actions**
4. Click **New repository secret**
5. Name: `ANTHROPIC_API_KEY`
6. Value: paste your API key from Step 4
7. Click **Add secret**

---

## STEP 6 — Enable GitHub Pages (free hosting)

1. In your repository, go to **Settings**
2. In the left sidebar, click **Pages**
3. Under "Source", select **Deploy from a branch**
4. Under "Branch", select **main** and folder **/ (root)**
5. Click **Save**
6. Wait 2-3 minutes
7. Refresh the page — you'll see a green banner with your URL:
   `https://yourusername.github.io/frontlinewire`

---

## STEP 7 — Run your first update

1. In your repository, click the **Actions** tab
2. Click **Update FrontlineWire** in the left list
3. Click **Run workflow** → **Run workflow**
4. Wait about 60–90 seconds
5. Refresh your website — it should now show real news stories!

After this, the site updates automatically every 6 hours. You don't need to do anything.

---

## OPTIONAL: Give your site a custom domain name

If you want `www.frontlinewire.news` instead of the github.io URL:

1. Buy a domain (Namecheap, Google Domains, or similar — ~$10–15/year)
2. In GitHub Pages settings, type your domain into the **Custom domain** field
3. Follow GitHub's DNS setup instructions (they walk you through it)

---

## Customizing your site

### Change the site name
Open `index.html` — find `FRONTLINE<span>WIRE</span>` and change it.

### Change update frequency
Open `.github/workflows/update.yml` — find `cron: '0 */6 * * *'`
- Every 3 hours: `0 */3 * * *`
- Every 12 hours: `0 */12 * * *`
- Once a day at 8am UTC: `0 8 * * *`

### Add or remove conflicts from the tracker
Open `app.js` — find `TRACKED_CONFLICTS` array near the top and edit the list.

### Add RSS feeds
Open `update.py` — find `RSS_FEEDS` list and add entries following the same format.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Site shows "Loading top story..." | Run the update workflow (Step 7) |
| GitHub Actions fails | Check that your API key is saved correctly in Secrets |
| Site URL gives 404 | Wait 5 minutes after enabling Pages, then refresh |
| Stories are all from one region | The RSS feeds for other regions may be slow — wait for next update |

---

## Need help?

If you get stuck, take a screenshot of the error and ask Claude for help —
describe what step you're on and what you see on screen.

---

*FrontlineWire — built with Claude AI*
