# SocialMediaProject
This is a project to post AI generated reels on TikTok, Instagram, or Youtube.

## reelbot: automated animal-facts reels

Generates ~60-90s vertical videos (TikTok first): Wikipedia-grounded script, fact-check pass, neural voiceover, stock footage and burned-in captions. Everything uses free tiers.

| Step | Tool (free) |
|---|---|
| Facts | Wikipedia API |
| Script + fact-check | Gemini free tier (or local Ollama, no key) |
| Voice + word timings | `edge-tts` (Microsoft neural voices) |
| Footage | Pexels and/or Pixabay free APIs |
| Captions / render | FFmpeg (ASS subtitles) |
| Topic rotation | SQLite (`data/reelbot.db`) |

### Setup

```powershell
winget install Python.Python.3.12 Gyan.FFmpeg
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env   # then fill in the free keys
$env:PYTHONPATH = "src"
.\.venv\Scripts\python -m reelbot doctor
.\.venv\Scripts\python -m reelbot generate                 # next topic
.\.venv\Scripts\python -m reelbot generate --animal Octopus
```

Output goes to `out/<timestamp>_<animal>/` with `video.mp4` and `meta.json` (caption, hashtags, source, status).
A video is `held` if the script fails fact-checking or its duration is outside the account's range (TikTok Creator Rewards needs > 1 minute).

Optional: put royalty-free music (CC0 or similar) in `assets/music/`; it is mixed in quietly.

### Accounts

Each account is a file in `config/` (voice, style, duration limits). Add `config/<name>.toml` and use `--account <name>`.

### Posting to TikTok

1. Create an app at <https://developers.tiktok.com/apps/> and add the **Content Posting API** and **Login Kit** products.
   Register the redirect URI `http://localhost:3455/callback/`.
2. Put the app's client key and secret in `.env` (`TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`).
3. Authorize your account once (opens a browser): `python -m reelbot tiktok-auth`
4. Post the oldest ready video: `python -m reelbot post`

Modes (`[tiktok]` in `config/<account>.toml`):
- `draft` (default): uploads to your TikTok inbox; open the app and tap Post. Needs the `video.upload` scope.
- `direct`: posts automatically (`video.publish` scope, and enable *Direct Post* in the app). Until TikTok audits the app,
  every direct post is forced to private (`SELF_ONLY`). Apply for the audit at <https://developers.tiktok.com/application/content-posting-api>.

Videos are always sent with the AI-generated flag.

### Daily schedule

`python -m reelbot daily` generates a video (retrying up to 3 topics if one is held) and posts it. If a video is already
queued, for example after a failed upload, it posts that one first. Register it with Windows Task Scheduler:

```powershell
.\scripts\register_task.ps1 -Time 09:00     # runs scripts\run_daily.ps1 daily; logs in logs\
```

The PC must be on (a missed run starts when it wakes). Test the task with `Start-ScheduledTask reelbot-animals`.

### Roadmap

1. Done: local end-to-end generation.
2. Done: daily scheduler and TikTok posting (draft + direct).
3. TikTok API audit, then switch to `direct` + `PUBLIC_TO_EVERYONE`.
4. Analytics feedback loop and multi-account support.

Label videos as AI-generated when posting.
