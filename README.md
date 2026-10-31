# Instaauto: YouTube Shorts → Instagram Reels

Every 15 minutes a GitHub Action checks your YouTube channel. When a new **Short** appears, it downloads it and publishes it as an **Instagram Reel**, using the title and description as the caption. Regular (long) videos are ignored.

```
YouTube Data API ──► new Short? ──► yt-dlp download ──► Instagram API (Reel) ──► state.json updated
```

- Runs free on GitHub Actions. No server and no PC needs to stay on.
- Uses the **official Instagram API**, so no risk to your Instagram account.
- Never posts the same Short twice (`state.json` remembers what it posted).
- On the first run it only *remembers* your existing videos. Only Shorts uploaded after setup are posted.

> ⚠️ Downloading from YouTube with yt-dlp goes against YouTube's Terms of Service, even for your own videos, and YouTube sometimes blocks GitHub's servers. If downloads fail, see [Troubleshooting](#troubleshooting).

---

## Setup (about 30–45 minutes, once)

### 1. Make your Instagram account Professional
Instagram app → **Settings → Account type and tools → Switch to professional account** (Creator or Business).

### 2. Create a Meta app and get a token
1. Go to <https://developers.facebook.com/apps> → **Create app** → use case **"Manage messaging & content on Instagram"**. Choose type **Business** if asked.
2. In the app, open **Instagram → API setup with Instagram login**.
3. Under **Generate access tokens**, click **Add account** and log in with your Instagram account. (If it asks, add yourself under **App roles → Roles → Instagram Testers**, then accept the invite in Instagram: **Settings → Apps and websites → Tester invites**.)
4. Make sure the permissions include **`instagram_business_basic`** and **`instagram_business_content_publish`**.
5. Click **Generate token** and copy it. This is a long-lived token, valid for 60 days. The refresh workflow below keeps it alive.

You don't need App Review, because you're only posting to your own account.

### 3. Find your YouTube channel ID and get a YouTube API key
**Channel ID:** YouTube → your profile picture → **Settings → Advanced settings → Channel ID**. It looks like `UCxxxxxxxxxxxxxxxxxxxxxx`.

**API key** (free; this project uses about 100 of the 10,000 free daily units):
1. Go to <https://console.cloud.google.com/> and create a project, for example "instaauto".
2. **APIs & Services → Library**, search **YouTube Data API v3**, and click **Enable**.
3. **APIs & Services → Credentials → Create credentials → API key**. Copy it.
4. Optional but good practice: click the key → **API restrictions → Restrict key → YouTube Data API v3**.

> Without a key, the script falls back to YouTube's public RSS feed. In October 2026 that feed was returning 404 errors, so use the key.

### 4. Put this project on GitHub
Create a new repository on GitHub. **Make it public** so Actions minutes are unlimited and free; your tokens stay secret either way. Then push this folder:

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_NAME/instaauto.git
git push -u origin main
```

> Private repo? The free plan gives 2,000 Action minutes a month, and checking every 15 minutes uses about 2,900. Change the cron in `.github/workflows/shorts-to-reels.yml` to `*/30 * * * *`.

### 5. Add secrets and variables
In the repo: **Settings → Secrets and variables → Actions**.

**Secrets** tab:

| Name | Value | Required |
|---|---|---|
| `IG_ACCESS_TOKEN` | The Instagram token from step 2 | ✅ |
| `YT_API_KEY` | The YouTube API key from step 3 | ✅ |
| `GH_PAT` | A GitHub token so the Instagram token can refresh itself (see below) | Recommended |
| `YT_COOKIES` | YouTube cookies, only if downloads get blocked (see Troubleshooting) | Optional |

**Variables** tab:

| Name | Value | Required |
|---|---|---|
| `YT_CHANNEL_ID` | Your channel ID from step 3 | ✅ |
| `CAPTION_TEMPLATE` | Caption format. Placeholders: `{title}`, `{description}`, `{url}`. Use `\n` for new lines. Default: `{title}\n\n{description}` | Optional |

Example caption template:
```
{title}\n\n{description}\n\n▶️ More on my YouTube channel, link in bio!
```

**Creating `GH_PAT`** (lets the weekly job save the refreshed Instagram token):
GitHub → your avatar → **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**.
- Repository access: **Only select repositories** → this repo
- Permissions → Repository permissions → **Secrets: Read and write**

Without it, you must paste a fresh `IG_ACCESS_TOKEN` every 60 days.

### 6. Turn it on
1. Repo → **Actions** tab → enable workflows if GitHub asks.
2. Open **YouTube Shorts to Instagram Reels → Run workflow**. The first run remembers your existing videos and commits `state.json`.
3. Open **Refresh Instagram token → Run workflow** once to check that token refresh works.

From now on, every new Short is posted to Instagram automatically, usually within 15–30 minutes.

---

## Test it with an existing Short
After the first run, open `state.json`, delete the entry for one of your Shorts, commit, and run the workflow:
- With **Dry run** ticked, it only prints the caption it would use.
- Without it, it really posts that Short as a Reel.

## Run locally (optional)
```bash
pip install -r requirements.txt "yt-dlp[default]"
```
You also need `ffmpeg` and `deno` on your PATH. Then, in PowerShell:
```powershell
$env:YT_CHANNEL_ID="UC..."; $env:YT_API_KEY="..."; $env:IG_ACCESS_TOKEN="..."
python -m instaauto whoami   # checks the Instagram token
python -m instaauto check    # finds new Shorts
python -m instaauto run      # posts them (set $env:DRY_RUN="1" to only preview)
```

## Troubleshooting

**"YouTube Data API error (403)…"** The API isn't enabled for the key's project, or the key's restrictions don't allow YouTube Data API v3. Recheck step 3.

**"YouTube RSS feed returned HTTP 404".** `YT_API_KEY` isn't set, so the script fell back to the RSS feed. Add the secret.

**"Sign in to confirm you're not a bot" / download errors.** YouTube is blocking GitHub's servers. You have two options:
1. **Cookies:** install a "Get cookies.txt LOCALLY" browser extension, open youtube.com while logged in (a secondary Google account is safer), export the cookies in Netscape format, and paste the whole file into the `YT_COOKIES` secret. Cookies expire, so you may need to redo this every few weeks.
2. **Manual fallback:** add the Short's file to the repo as `videos/<VIDEO_ID>.mp4` (the ID is the part after `/shorts/`). The next run uses that file instead of downloading.

A failed Short is retried on every run, up to 5 times. GitHub emails you when a run fails. After 5 failures the Short is marked `gave_up` in `state.json`. Set its status back to `pending` to try again.

**Instagram errors.**
- *Invalid OAuth access token:* the token expired. Generate a new one (step 2) and set up `GH_PAT`.
- *Media upload failed / processing error:* Instagram Reels must be 3 seconds to 15 minutes long and MP4 (H.264/AAC). The script converts other codecs automatically. Copyrighted music in a Short can also get the Reel blocked or muted.
- Instagram allows at most 50 API-published posts per 24 hours.

**Scheduled runs stopped.** GitHub disables scheduled workflows in public repos after 60 days with no repo activity. Re-enable it on the Actions tab. Each post commits `state.json`, which counts as activity.

## Files
| Path | What it does |
|---|---|
| `instaauto/youtube.py` | Lists the latest uploads (YouTube Data API, or RSS fallback) and detects Shorts |
| `instaauto/downloader.py` | Downloads with yt-dlp (or uses `videos/<id>.mp4`), converts the codec if needed |
| `instaauto/instagram.py` | Uploads and publishes the Reel through the Instagram API |
| `instaauto/__main__.py` | `check` / `run` / `whoami` commands |
| `state.json` | Created on first run. Records which videos were posted or skipped |
| `.github/workflows/shorts-to-reels.yml` | Runs every 15 minutes |
| `.github/workflows/refresh-token.yml` | Refreshes the Instagram token weekly |
