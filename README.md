# Instaauto: Google Drive → Instagram Reels

Upload a video to a Google Drive folder and it's posted to Instagram as a **Reel** automatically. A GitHub Action checks the folder every 15 minutes, publishes new videos through the official Instagram API, and moves each posted video into a `Posted` subfolder.

```
You upload to Drive ──► GitHub Action (every 15 min) ──► Instagram Reel ──► video moved to Posted/
```

- Runs free on GitHub Actions. No server and no PC needs to stay on.
- Uses the **official Instagram API**, so no risk to your Instagram account.
- Your Drive folder stays **private**. Only you and a Google "service account" (a robot user) can see it.
- Never posts the same video twice (`state.json` remembers what was posted).

## How to use it (after setup)

1. Upload a video (MP4 or MOV, vertical 9:16, 3 seconds to 15 minutes) to your **Instaauto** folder in Google Drive.
2. **Caption:** upload a `.txt` file with the **same name** as the video, e.g. `goa-trip.mp4` + `goa-trip.txt`. Put the caption and hashtags in the text file. Without a `.txt`, the file name is used as the caption (`Goa trip 🌴.mp4` → "Goa trip 🌴").
3. Within about 15–30 minutes the Reel is live and both files move to `Posted/`.

Good to know:
- New uploads wait **5 minutes** before posting, so you have time to add the `.txt` after the video.
- **One video per run** (every 15 minutes) by default, so a batch of uploads goes out spread over time. Change this with the `MAX_POSTS_PER_RUN` variable.
- If a video fails 5 times (for example, a broken file), it moves to `Failed/` and GitHub emails you.

---

## Setup (once)

### 1. Instagram Professional account ✅
Instagram → **Settings → Account type and tools → Switch to professional account**. (@kyahoagar already is one.)

### 2. Meta app and Instagram token
1. <https://developers.facebook.com/apps> → open your app (**Kyaho**). It already has the **"Manage messaging & content on Instagram"** use case. (For a new app: **Create app** → that use case.)
2. **Use cases → Customize → API setup with Unified login.**
3. Meta requires a **Business portfolio** here. Click **+ Business portfolio → Create new account** and fill in a name and email. (Brand-new Facebook accounts must wait before they can create one. Just try again later.) Business verification is **not** needed to post to your own account.
4. Under **Generate access tokens**, click **Add account** and log in with Instagram. If asked, add yourself under **App roles → Roles → Instagram Testers** and accept the invite in Instagram (**Settings → Apps and websites → Tester invites**).
5. Make sure the permissions include **`instagram_business_basic`** and **`instagram_business_content_publish`**.
6. Click **Generate token** and copy it. It's valid for 60 days, and the refresh workflow keeps it alive.

### 3. Google service account (lets GitHub read your Drive folder)
1. Go to <https://console.cloud.google.com/> → **Select a project → New project** → name it `instaauto` → **Create**.
2. **APIs & Services → Library** → search **Google Drive API** → **Enable**.
3. **IAM & Admin → Service accounts → Create service account** → name it `instaauto` → **Create and continue** → skip roles → **Done**.
4. Click the new service account → **Keys → Add key → Create new key → JSON → Create**. A `.json` file downloads.
5. Copy the service account's email. It looks like `instaauto@your-project.iam.gserviceaccount.com`.

> 🔒 The JSON file is a password for the robot account. Don't share it or commit it. Delete it from your PC once it's in GitHub (step 5).

### 4. Drive folder
1. In Google Drive, create a folder, e.g. **Instaauto**. Optionally create `Posted` and `Failed` inside it; they're created automatically otherwise.
2. Right-click the folder → **Share** → paste the service account email → set it to **Editor** → untick "Notify people" → **Share**.
3. Open the folder and copy its link: `https://drive.google.com/drive/folders/1AbC...`.

### 5. GitHub secrets and variables
Repo **ashvin008/Instaauto** → **Settings → Secrets and variables → Actions**.

**Secrets** tab:

| Name | Value | Required |
|---|---|---|
| `IG_ACCESS_TOKEN` | Instagram token from step 2 | ✅ |
| `GDRIVE_SERVICE_ACCOUNT` | The **entire contents** of the JSON key file from step 3 (open it in Notepad, copy everything) | ✅ |
| `GH_PAT` | GitHub token so the Instagram token can refresh itself (see below) | Recommended |

**Variables** tab:

| Name | Value | Required |
|---|---|---|
| `GDRIVE_FOLDER_ID` | The folder link from step 4 (the full link or just the ID) | ✅ |
| `CAPTION_TEMPLATE` | Caption format. `{caption}` = text from the `.txt` (or the file name), `{filename}` = file name. Use `\n` for new lines. Default: `{caption}` | Optional |
| `MAX_POSTS_PER_RUN` | Videos posted per 15-minute run. Default: `1` | Optional |

Example caption template, which adds the same hashtags to every post:
```
{caption}\n\n#reels #kyaho
```

**Creating `GH_PAT`:** GitHub → your avatar → **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**.
- Repository access: **Only select repositories** → `Instaauto`
- Permissions → Repository permissions → **Secrets: Read and write**

Without it, you must paste a fresh `IG_ACCESS_TOKEN` every 60 days.

### 6. Turn it on
1. Repo → **Actions** → **Google Drive videos to Instagram Reels** → enable it if it's disabled.
2. Upload a test video to the folder, wait 5 minutes, then click **Run workflow** with **Dry run** ticked. The log shows the caption it would use.
3. Run it again without dry run to really post it. After that, it runs by itself every 15 minutes.
4. Run **Refresh Instagram token** once to check that token renewal works.

---

## Run locally (optional)
```bash
pip install -r requirements.txt
```
You also need `ffmpeg` on your PATH. Then, in PowerShell:
```powershell
$env:GDRIVE_FOLDER_ID="https://drive.google.com/drive/folders/..."
$env:GDRIVE_SERVICE_ACCOUNT = Get-Content .\service-account.json -Raw
$env:IG_ACCESS_TOKEN="..."
python -m instaauto whoami   # checks the Instagram token
python -m instaauto check    # finds new videos
python -m instaauto run      # posts them (set $env:DRY_RUN="1" to only preview)
```
Keep the JSON key outside this folder, or make sure it's never committed.

## Troubleshooting

**"Google Drive GET failed (404): File not found"** The folder isn't shared with the service account, or `GDRIVE_FOLDER_ID` is wrong. Share the folder with the service account email as **Editor**.

**"Google Drive … (403): Google Drive API has not been used in project…"** Enable the Google Drive API (step 3.2) in the same project as the service account.

**"Could not move file to Posted/"** (warning). The Reel was still posted, and it won't be posted again. The service account only needs **Editor** access on the folder; check the sharing settings.

**Can't create a JSON key ("Service account key creation is disabled").** This happens with Google Workspace (company) accounts. Use a personal Gmail account for the Google Cloud project.

**Instagram errors.**
- *Invalid OAuth access token:* the token expired. Generate a new one (step 2) and set up `GH_PAT`.
- *Processing error:* Reels must be 3 seconds to 15 minutes long. The script converts unusual video codecs to H.264 automatically. Copyrighted music can get a Reel blocked or muted.
- Instagram allows at most 50 API-published posts per 24 hours.

**A video is stuck as `failed`/`gave_up`.** Check the error in `state.json`. To retry, set its `"status"` back to `"pending"` and its `"attempts"` to `0`, commit, and move the file back out of `Failed/`.

**Scheduled runs stopped.** GitHub disables scheduled workflows in public repos after 60 days without repo activity. Re-enable it on the Actions tab. Each post commits `state.json`, which counts as activity.

**Private repo?** The free plan gives 2,000 Action minutes a month, and checking every 15 minutes uses about 2,900. Change the cron in `.github/workflows/drive-to-reels.yml` to `*/30 * * * *`.

## Files
| Path | What it does |
|---|---|
| `instaauto/drive.py` | Lists, downloads and moves files in the Drive folder (service account) |
| `instaauto/media.py` | Converts the video to H.264 if Instagram wouldn't accept it |
| `instaauto/instagram.py` | Uploads and publishes the Reel through the Instagram API |
| `instaauto/__main__.py` | `check` / `run` / `whoami` commands |
| `state.json` | Created on first run. Records which videos were posted |
| `.github/workflows/drive-to-reels.yml` | Runs every 15 minutes |
| `.github/workflows/refresh-token.yml` | Refreshes the Instagram token weekly |
