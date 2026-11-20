# Clipper

Turns a long video into vertical YouTube Shorts.

1. Downloads the video (or uses a file you already have).
2. Transcribes it with Whisper, with a timestamp on every word.
3. Sends the transcript to Claude, which picks the moments most likely to hold attention and writes titles.
4. Cuts each moment to 1080x1920 with a blurred background and big captions.
5. Uploads to YouTube as **private** so you check each one before it goes public.

## Install on a Mac (one line)

Open Terminal and paste:

```
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Daily1391/daily-app/claude/bot-creation-lcbtji/clipper/install.sh)"
```

It installs what Clipper needs and puts the app in a `Clipper` folder in your home folder. Run the same line again any time to update; your key, YouTube login, music and clips are kept.

## Easiest way: the app

Double-click `Clipper.command`. A browser page opens where you drop in a video, make clips, watch them, edit titles, and pick which to upload. The first run installs everything (a few minutes). Keep the black window open while you use it; close it to stop.

If macOS blocks it the first time: right-click `Clipper.command`, choose Open, then Open again.

## Setup (once)

You need Python 3.10+ and ffmpeg (`brew install ffmpeg` on Mac).

```bash
cd clipper
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...   # from console.anthropic.com
```

### YouTube setup (only needed for `--upload`)

1. Go to console.cloud.google.com and create a project.
2. Enable "YouTube Data API v3".
3. OAuth consent screen: choose External, add yourself as a test user.
4. Credentials → Create OAuth client ID → Desktop app → download the JSON.
5. Save it as `clipper/client_secret.json`.

The first upload opens a browser to log in. After that it remembers you (`token.json`).

## Use it

```bash
# Make clips only, look at them in clipper/output/
python clipper.py my_podcast.mp4

# Make 3 clips and upload them as private
python clipper.py my_podcast.mp4 --count 3 --upload --credit "Clipped from @creator with permission"

# Upload clips you already made (asks y/n/edit-title for each one)
python clipper.py --upload-existing "output/my_podcast.clips.json" --privacy public
```

Options: `--count` (max clips), `--whisper tiny|base|small|medium` (bigger is more accurate, slower), `--privacy private|unlisted|public`.

## Limits you will hit

- **Upload quota.** A new Google project gets 10,000 units a day and each upload costs 1,600. That's 6 uploads a day.
- **Unverified apps upload as private-locked.** Until Google audits your project, API uploads may be stuck private. Fine for testing. Request the audit before you scale.
- **Speech only.** Clips are picked from what people say. A silent gameplay video gets nothing.
- **Cost.** Roughly 10 to 20 cents of Claude usage per hour of video. Whisper runs on your computer for free.

## Rights

Only clip videos you own or have permission to clip. Reposting other people's content gets copyright strikes, and YouTube demonetizes channels for "reused content". The legit version of this business is clipping for creators who pay clippers or explicitly allow it.
