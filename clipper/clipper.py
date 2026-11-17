"""Clipper: turn a long video into vertical Shorts and (optionally) upload them.

Pipeline: fetch -> transcribe -> pick moments with Claude -> cut to 9:16 with
captions -> upload to YouTube as private for you to review.

Usage:
    python clipper.py path/to/video.mp4
    python clipper.py https://example.com/video --count 5 --upload
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import anthropic
from pydantic import BaseModel, Field

OUT_DIR = Path(__file__).parent / "output"
MIN_LEN, MAX_LEN = 15.0, 59.0  # Shorts must be under 60s to be safe everywhere
MODEL = "claude-opus-5-5"


# ─── 1. Fetch ────────────────────────────────────────────────────────────────
def fetch(source: str) -> Path:
    """Return a local video path. Downloads with yt-dlp if given a URL."""
    if not re.match(r"^https?://", source):
        path = Path(source).expanduser().resolve()
        if not path.exists():
            sys.exit(f"File not found: {path}")
        return path

    import yt_dlp

    dl_dir = OUT_DIR / "source"
    dl_dir.mkdir(parents=True, exist_ok=True)
    opts = {
        "format": "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b",
        "merge_output_format": "mp4",
        "outtmpl": str(dl_dir / "%(id)s.%(ext)s"),
        "quiet": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(source, download=True)
        return Path(ydl.prepare_filename(info)).with_suffix(".mp4")


# ─── 2. Transcribe ───────────────────────────────────────────────────────────
def transcribe(video: Path, model_size: str) -> list[dict]:
    """Return a list of words: {"start", "end", "text"}. Cached next to output."""
    cache = OUT_DIR / f"{video.stem}.words.json"
    if cache.exists():
        return json.loads(cache.read_text())

    from faster_whisper import WhisperModel

    print(f"Transcribing with whisper '{model_size}' (first run downloads the model)...")
    model = WhisperModel(model_size, device="auto", compute_type="int8")
    segments, _ = model.transcribe(str(video), word_timestamps=True, vad_filter=True)
    words = [
        {"start": round(w.start, 2), "end": round(w.end, 2), "text": w.word.strip()}
        for seg in segments
        for w in (seg.words or [])
    ]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(words))
    return words


def transcript_lines(words: list[dict], chunk: int = 12) -> str:
    """Group words into timestamped lines Claude can read: [12.3-16.1] text"""
    lines = []
    for i in range(0, len(words), chunk):
        part = words[i : i + chunk]
        text = " ".join(w["text"] for w in part)
        lines.append(f"[{part[0]['start']:.1f}-{part[-1]['end']:.1f}] {text}")
    return "\n".join(lines)


# ─── 3. Pick moments ─────────────────────────────────────────────────────────
class Clip(BaseModel):
    start: float = Field(description="Start time in seconds, at the start of a sentence")
    end: float = Field(description="End time in seconds, at the end of a sentence")
    title: str = Field(description="YouTube Shorts title, under 70 characters, no clickbait lies")
    hook: str = Field(description="The first line viewers hear, quoted from the transcript")
    reason: str = Field(description="One sentence on why this moment will hold attention")
    score: int = Field(description="Virality score from 1 to 10")


class ClipPlan(BaseModel):
    clips: list[Clip]


SYSTEM = """You are a short-form video editor who finds the moments in long videos \
that perform as YouTube Shorts.

A good clip:
- Opens on a hook in the first two seconds: a bold claim, a question, a surprise, \
conflict, or a strong emotion. Never opens on filler like "so", "um", or "anyway".
- Stands alone. A viewer with zero context understands it.
- Has a payoff: a punchline, a reveal, a useful insight, or a strong opinion.
- Starts and ends on sentence boundaries so it doesn't cut mid-word.

Use only timestamps that appear in the transcript. Clips must not overlap. \
Rank clips best first. Skip weak moments rather than padding the list."""


def pick_clips(words: list[dict], count: int) -> list[Clip]:
    client = anthropic.Anthropic()
    prompt = (
        f"Find up to {count} clips between {MIN_LEN:.0f} and {MAX_LEN:.0f} seconds long "
        f"in this transcript.\n\n<transcript>\n{transcript_lines(words)}\n</transcript>"
    )
    print("Asking Claude for the best moments...")
    response = client.beta.messages.parse(
        model=MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",  # if a request is declined, retry on a fallback model
        output_config={"effort": "high"},
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        output_format=ClipPlan,
    )
    if response.stop_reason == "refusal" or response.parsed_output is None:
        sys.exit(f"Claude did not return clips (stop_reason={response.stop_reason}).")

    clips, taken = [], []
    for c in sorted(response.parsed_output.clips, key=lambda c: -c.score):
        c.end = min(c.end, c.start + MAX_LEN)
        if c.end - c.start < MIN_LEN:
            continue
        if any(c.start < e and s < c.end for s, e in taken):
            continue
        taken.append((c.start, c.end))
        clips.append(c)
    return clips[:count]


# ─── 4. Render ───────────────────────────────────────────────────────────────
def ass_time(t: float) -> str:
    h, rem = divmod(max(t, 0), 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def write_captions(words: list[dict], clip: Clip, path: Path, per_line: int = 3) -> None:
    """Big, centered, 3-words-at-a-time captions, the standard Shorts style."""
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Outline, Shadow, Alignment, MarginV
Style: Cap,Arial,84,&H00FFFFFF,&H00000000,&H80000000,1,6,2,2,560

[Events]
Format: Layer, Start, End, Style, Text
"""
    inside = [w for w in words if w["start"] >= clip.start and w["end"] <= clip.end]
    events = []
    for i in range(0, len(inside), per_line):
        group = inside[i : i + per_line]
        start = group[0]["start"] - clip.start
        end = (inside[i + per_line]["start"] if i + per_line < len(inside) else group[-1]["end"]) - clip.start
        text = " ".join(w["text"] for w in group).upper().replace("{", "").replace("}", "")
        events.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Cap,{text}")
    path.write_text(header + "\n".join(events) + "\n")


_FFMPEG: tuple[str, bool] | None = None


def find_ffmpeg() -> tuple[str, bool]:
    """Pick an ffmpeg that can burn captions. Homebrew's plain 'ffmpeg' can't
    (no libass); 'ffmpeg-full' can. Falls back to no captions with a warning."""
    global _FFMPEG
    if _FFMPEG:
        return _FFMPEG
    candidates = [
        "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg",
        "/usr/local/opt/ffmpeg-full/bin/ffmpeg",
        "ffmpeg",
    ]
    for exe in candidates:
        try:
            filters = subprocess.run(
                [exe, "-hide_banner", "-filters"], capture_output=True, text=True
            ).stdout
        except FileNotFoundError:
            continue
        if re.search(r"\ssubtitles\s", filters):
            _FFMPEG = (exe, True)
            return _FFMPEG
    print("Warning: your ffmpeg can't add captions. Clips will have none.\n"
          "  Fix: brew install ffmpeg-full")
    _FFMPEG = ("ffmpeg", False)
    return _FFMPEG


def render(video: Path, words: list[dict], clip: Clip, index: int) -> Path:
    """Cut the clip and make it 1080x1920: sharp video centered over a blurred fill."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", clip.title.lower()).strip("-")[:40] or "clip"
    out = OUT_DIR / f"{index:02d}-{slug}.mp4"
    subs = OUT_DIR / f"{index:02d}.ass"
    write_captions(words, clip, subs)

    ffmpeg, has_subs = find_ffmpeg()
    captions = f",subtitles='{subs.as_posix()}'" if has_subs else ""
    vf = (
        "[0:v]split[a][b];"
        "[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20:2[bg];"
        "[b]scale=1080:-2[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2{captions}[v]"
    )
    cmd = [
        ffmpeg, "-y", "-loglevel", "error",
        "-ss", f"{clip.start:.2f}", "-to", f"{clip.end:.2f}", "-i", str(video),
        "-filter_complex", vf, "-map", "[v]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
        str(out),
    ]
    subprocess.run(cmd, check=True)
    return out


# ─── 5. Upload ───────────────────────────────────────────────────────────────
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def youtube_client():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    here = Path(__file__).parent
    token, secret = here / "token.json", here / "client_secret.json"
    creds = Credentials.from_authorized_user_file(token, SCOPES) if token.exists() else None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not secret.exists():
                sys.exit("Missing client_secret.json. See README, step 'YouTube setup'.")
            creds = InstalledAppFlow.from_client_secrets_file(secret, SCOPES).run_local_server(port=0)
        token.write_text(creds.to_json())
    return build("youtube", "v3", credentials=creds)


def upload(yt, path: Path, clip: Clip, privacy: str, credit: str) -> str:
    from googleapiclient.http import MediaFileUpload

    description = f"{clip.hook}\n\n{credit}\n\n#Shorts".strip()
    body = {
        "snippet": {"title": clip.title[:100], "description": description, "categoryId": "22"},
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
    }
    request = yt.videos().insert(
        part="snippet,status", body=body, media_body=MediaFileUpload(str(path), resumable=True)
    )
    response = None
    while response is None:
        _, response = request.next_chunk()
    return f"https://youtube.com/shorts/{response['id']}"


# ─── Main ────────────────────────────────────────────────────────────────────
def main() -> None:
    p = argparse.ArgumentParser(description="Turn a long video into YouTube Shorts.")
    p.add_argument("source", help="Video file path or URL")
    p.add_argument("--count", type=int, default=5, help="Max clips to make (default 5)")
    p.add_argument("--whisper", default="small", help="Whisper model: tiny, base, small, medium")
    p.add_argument("--upload", action="store_true", help="Upload clips to YouTube")
    p.add_argument("--privacy", default="private", choices=["private", "unlisted", "public"])
    p.add_argument("--credit", default="", help='Credit line, e.g. "Clipped from @creator with permission"')
    args = p.parse_args()

    video = fetch(args.source)
    words = transcribe(video, args.whisper)
    if not words:
        sys.exit("No speech found. This bot picks clips from what people say.")

    clips = pick_clips(words, args.count)
    if not clips:
        sys.exit("Claude found no clips worth posting in this video.")

    yt = youtube_client() if args.upload else None
    results = []
    for i, clip in enumerate(clips, 1):
        print(f"[{i}/{len(clips)}] {clip.score}/10  {clip.start:.0f}s-{clip.end:.0f}s  {clip.title}")
        path = render(video, words, clip, i)
        entry = {**clip.model_dump(), "file": str(path)}
        if yt:
            entry["url"] = upload(yt, path, clip, args.privacy, args.credit)
            print(f"    uploaded ({args.privacy}): {entry['url']}")
        results.append(entry)

    manifest = OUT_DIR / f"{video.stem}.clips.json"
    manifest.write_text(json.dumps(results, indent=2))
    print(f"\nDone. {len(results)} clips in {OUT_DIR}. Details: {manifest}")


if __name__ == "__main__":
    main()
