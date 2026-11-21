# 🎤 Karaoke Queue

A karaoke night web app: search YouTube for minus-one / karaoke versions, queue singers, and control playback (Pause, Replay, Next). Songs auto-advance when one ends.

## Run locally

```bash
python3 server.py
```

Open http://localhost:8000 (other devices on the same Wi-Fi: `http://<your-computer-ip>:8000`).

## Deploy (Render)

This repo includes `render.yaml`. On render.com: **New → Blueprint**, pick this repo, and deploy. No environment variables are required.

If YouTube blocks search from the server, add a free YouTube Data API key in the app's ⚙ Settings; it's used as a backup.
