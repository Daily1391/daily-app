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
TARGET = "20 to 40"  # seconds; shorter clips get watched to the end more often
GAP = 0.35  # pauses longer than this get cut out
MODEL = "claude-opus-5-5"


# ─── 1. Fetch ────────────────────────────────────────────────────────────────
def fetch(source: str) -> Path:
    """Return a local video path. Downloads with yt-dlp if given a URL."""
    if not re.match(r"^https?://", source):
        path = Path(source).expanduser().resolve()
        if not path.exists():
            raise ClipperError(f"File not found: {path}")
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
    overlay: str = Field(
        description="On-screen hook text shown for the whole clip, 3 to 8 words, no emojis",
    )
    emphasis: list[str] = Field(
        description="5 to 12 single words spoken in the clip to highlight in colour in the captions",
    )


class ClipPlan(BaseModel):
    clips: list[Clip]


SYSTEM = """You are a short-form video editor who finds the moments in long videos \
that perform as YouTube Shorts.

Your only goal is retention: viewers who don't swipe away, watch to the end, and replay.

A good clip:
- Wins the first second. The very first words are the hook: a bold claim, a question, \
a surprise, conflict, or a strong emotion. Start in the middle of the action, not on \
the setup. Never open on filler like "so", "um", "anyway" or "okay so".
- Stands alone. A viewer with zero context understands it.
- Has a payoff: a punchline, a reveal, a useful insight, or a strong opinion.
- Ends the moment the payoff lands. No wind-down, no "anyway", no laughing it off. \
A hard stop on the best line makes people replay it.
- Is as short as it can be while still landing. Aim for 20 to 40 seconds.
- Starts and ends on sentence boundaries so it doesn't cut mid-word.
Score each clip on how likely a stranger is to watch it to the end, not on how \
interesting it is to a fan.

For each clip also write overlay: the fixed text shown on screen for the whole clip, \
the thing that stops a scroller. 3 to 8 words. Build curiosity without spoiling the \
payoff, for example "JYNXZI REACTS TO A CLIP OF HIMSELF..." or "HE DID NOT EXPECT THIS". \
Name the creator if the transcript makes clear who it is. It must be true to the clip. \
No emojis and no hashtags.

Also list emphasis: 5 to 12 single words, spoken inside the clip, that carry the meaning \
(names, numbers, surprising or emotional words). They light up in colour in the captions. \
Never pick filler like "the", "and" or "like".

Use only timestamps that appear in the transcript. Clips must not overlap. \
Rank clips best first. Skip weak moments rather than padding the list."""


def pick_clips(words: list[dict], count: int) -> list[Clip]:
    client = anthropic.Anthropic()
    prompt = (
        f"Find up to {count} clips, ideally {TARGET} seconds and never under {MIN_LEN:.0f} "
        f"or over {MAX_LEN:.0f} seconds, "
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
        raise ClipperError(f"Claude did not return clips (stop_reason={response.stop_reason}).")

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


STYLES = {"full": "Full screen with zooms", "blur": "Blurred background"}
GLOW = ["&H0050FF39&", "&H00FFE500&"]  # green, cyan (ASS colours are BGR)


def norm(word: str) -> str:
    return re.sub(r"[^a-z0-9']", "", word.lower())


def esc(text: str) -> str:
    return text.replace("{", "").replace("}", "").replace("\\", "")


def write_captions(words: list[dict], clip: Clip, path: Path, per_line: int = 3,
                   style: str = "blur", watermark: str = "") -> None:
    """blur: 3-words-at-a-time captions under the video.
    full: one big glowing word at a time in the middle, key words in green or cyan."""
    header_tpl = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Outline, Shadow, Alignment, MarginV
Style: Cap,Arial,84,&H00FFFFFF,&H00000000,&H80000000,1,6,2,2,560
Style: Hook,Arial,{hook_size},&H00FFFFFF,&H00000000,&H80000000,1,7,3,2,{hook_margin}
Style: Word,Arial,128,&H00FFFFFF,&H00000000,&H90000000,1,5,4,2,980
Style: Mark,Arial,36,&H60FFFFFF,&H00000000,&HFF000000,0,1,0,8,955

[Events]
Format: Layer, Start, End, Style, Text
"""
    inside = [w for w in words if w["start"] >= clip.start and w["end"] <= clip.end]
    events = []
    hook_lines = wrap_overlay(clip.overlay)
    hook_size = {1: 96, 2: 92, 3: 80}.get(len(hook_lines), 0)
    if not hook_size:  # long text: smaller font, wider lines, never cut words off
        hook_lines, hook_size = wrap_overlay(clip.overlay, width=24), 64
    if hook_lines:
        # first half of the lines white, the rest cyan, like the usual Shorts style
        parts = list(hook_lines)
        if len(parts) > 1:
            split = len(parts) // 2  # colour stays on for every line after this
            parts[split] = "{\\c&H00FFFF00&}" + parts[split]
        text = "\\N".join(parts)
        events.append(f"Dialogue: 1,{ass_time(0)},{ass_time(clip.end - clip.start)},Hook,{text}")
    hook_margin = "1300" if style == "blur" else "1420"  # full: near the top of the screen

    if style == "full":
        keys = {norm(k) for phrase in clip.emphasis for k in phrase.split()} - {""}
        n_key = 0
        for i, w in enumerate(inside):
            start = w["start"] - clip.start
            end = (inside[i + 1]["start"] if i + 1 < len(inside) else w["end"]) - clip.start
            end = min(end, start + 1.2)  # don't leave a word up through a long pause
            word = esc(w["text"]).upper().strip()
            if not word:
                continue
            if norm(w["text"]) in keys:
                colour, n_key = GLOW[n_key % 2], n_key + 1
                fill, glow_alpha = colour, "&H40&"
            else:
                fill, colour, glow_alpha = "&H00FFFFFF&", "&H00FFFFFF&", "&HB0&"
            pop = "\\fscx80\\fscy80\\t(0,90,\\fscx100\\fscy100)"
            t0, t1 = ass_time(start), ass_time(end)
            # layer 2: soft coloured glow behind; layer 3: crisp word on top
            events.append(f"Dialogue: 2,{t0},{t1},Word,{{{pop}\\1a&HFF&\\3c{colour}\\3a{glow_alpha}\\bord16\\blur14}}{word}")
            events.append(f"Dialogue: 3,{t0},{t1},Word,{{{pop}\\c{fill}}}{word}")
        if watermark.strip():
            events.append(f"Dialogue: 1,{ass_time(0)},{ass_time(clip.end - clip.start)},Mark,{esc(watermark).upper()}")
        header = header_tpl.replace("{hook_size}", str(hook_size)).replace("{hook_margin}", hook_margin)
        path.write_text(header + "\n".join(events) + "\n")
        return

    for i in range(0, len(inside), per_line):
        group = inside[i : i + per_line]
        start = group[0]["start"] - clip.start
        end = (inside[i + per_line]["start"] if i + per_line < len(inside) else group[-1]["end"]) - clip.start
        text = " ".join(w["text"] for w in group).upper().replace("{", "").replace("}", "")
        events.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Cap,{text}")
    # sits in the blurred band above a 16:9 video (video top is about y=656)
    header = header_tpl.replace("{hook_size}", str(hook_size)).replace("{hook_margin}", hook_margin)
    path.write_text(header + "\n".join(events) + "\n")


EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F]")


def wrap_overlay(text: str, width: int = 17) -> list[str]:
    """Upper-case, strip emojis and caption-breaking characters, wrap into short lines."""
    text = EMOJI.sub("", text or "").upper().replace("{", "").replace("}", "").replace("\\", "")
    lines: list[str] = []
    for word in text.split():
        if lines and len(lines[-1]) + 1 + len(word) <= width:
            lines[-1] += " " + word
        else:
            lines.append(word)
    return lines


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


def zoom_expr(words: list[dict], clip: Clip) -> str:
    """Slow push in and out all the time, plus a quick punch-in on each key word."""
    keys = {norm(k) for phrase in clip.emphasis for k in phrase.split()} - {""}
    punches = [w for w in words if clip.start <= w["start"] <= clip.end and norm(w["text"]) in keys][:20]
    z = "1.06+0.05*sin(2*PI*t/7)"
    for w in punches:
        a = w["start"] - clip.start
        z += f"+0.10*between(t,{a:.2f},{a + 0.45:.2f})"
    return z


def speech_segments(words: list[dict], clip: Clip, gap: float = GAP, pad: float = 0.08):
    """Stretches of talking inside the clip, in clip time, with pauses removed."""
    inside = [w for w in words if w["start"] >= clip.start and w["end"] <= clip.end]
    segs: list[list[float]] = []
    for w in inside:
        a = max(w["start"] - clip.start - pad, 0)
        b = min(w["end"] - clip.start + pad, clip.end - clip.start)
        if segs and a - segs[-1][1] <= gap:
            segs[-1][1] = max(segs[-1][1], b)
        else:
            segs.append([a, b])
    return segs


def tighten(words: list[dict], clip: Clip):
    """Cut the pauses: returns the kept segments plus words and a clip re-timed to match."""
    segs = speech_segments(words, clip)
    if not segs:
        return None, words, clip
    kept = sum(b - a for a, b in segs)
    if (clip.end - clip.start) - kept < 0.5:  # almost no dead air, not worth cutting
        return None, words, clip

    def remap(t: float) -> float:
        done = 0.0
        for a, b in segs:
            if t < a:
                return done
            if t <= b:
                return done + (t - a)
            done += b - a
        return done

    new_words = []
    for w in words:
        if w["start"] >= clip.start and w["end"] <= clip.end:
            new_words.append({**w, "start": remap(w["start"] - clip.start),
                              "end": remap(w["end"] - clip.start)})
    return segs, new_words, clip.model_copy(update={"start": 0.0, "end": kept})


def render(video: Path, words: list[dict], clip: Clip, index: int, prefix: str = "",
           out: Path | None = None, style: str = "blur", watermark: str = "",
           cut_pauses: bool = True) -> Path:
    """Cut the clip to 1080x1920. blur: sharp video over a blurred fill.
    full: fill the screen, zoom, punchier colour."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", clip.title.lower()).strip("-")[:40] or "clip"
    tag = f"{prefix}-" if prefix else ""
    out = out or OUT_DIR / f"{tag}{index:02d}-{slug}.mp4"
    subs = out.with_suffix(".ass")
    source_clip = clip
    segs = None
    if cut_pauses:
        segs, words, clip = tighten(words, clip)  # captions and zooms follow the new timing
    write_captions(words, clip, subs, style=style, watermark=watermark)

    if segs:
        parts = "".join(
            f"[0:v]trim={a:.3f}:{b:.3f},setpts=PTS-STARTPTS[v{i}];"
            f"[0:a]atrim={a:.3f}:{b:.3f},asetpts=PTS-STARTPTS[a{i}];"
            for i, (a, b) in enumerate(segs)
        )
        joined = "".join(f"[v{i}][a{i}]" for i in range(len(segs)))
        pre = f"{parts}{joined}concat=n={len(segs)}:v=1:a=1[cv][ca];"
        vin, audio = "[cv]", "[ca]"
    else:
        pre, vin, audio = "", "[0:v]", "0:a?"

    ffmpeg, has_subs = find_ffmpeg()
    captions = f",subtitles='{subs.as_posix()}'" if has_subs else ""
    if style == "full":
        z = zoom_expr(words, clip)
        vf = (
            f"{pre}{vin}scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
            f"scale=w='trunc(1080*({z})/2)*2':h='trunc(1920*({z})/2)*2':eval=frame,"
            "crop=1080:1920,setsar=1,"
            "eq=contrast=1.08:saturation=1.18,unsharp=5:5:0.6"
            f"{captions}[v]"
        )
    else:
        vf = (
            f"{pre}{vin}split[a][b];"
            "[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20:2[bg];"
            "[b]scale=1080:-2[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2{captions}[v]"
        )
    cmd = [
        ffmpeg, "-y", "-loglevel", "error",
        "-ss", f"{source_clip.start:.2f}", "-to", f"{source_clip.end:.2f}", "-i", str(video),
        "-filter_complex", vf, "-map", "[v]", "-map", audio,
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
                raise ClipperError("Missing client_secret.json. See README, step 'YouTube setup'.")
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


class ClipperError(Exception):
    pass


def clip_from_entry(entry: dict) -> Clip:
    data = {k: entry[k] for k in Clip.model_fields if k in entry}
    data.setdefault("overlay", "")  # clips made before on-screen text existed
    data.setdefault("emphasis", [])
    return Clip(**data)


def make_clips(source: str, count: int, whisper: str, log=print,
               style: str = "full", watermark: str = "", cut_pauses: bool = True) -> Path:
    """Fetch, transcribe, pick and render. Returns the path of the clips list."""
    log("Getting the video...")
    video = fetch(source)
    log("Transcribing (the slow part)...")
    words = transcribe(video, whisper)
    if not words:
        raise ClipperError("No speech found. This bot picks clips from what people say.")
    log("Asking Claude for the best moments...")
    clips = pick_clips(words, count)
    if not clips:
        raise ClipperError("Claude found no clips worth posting in this video.")

    stem = re.sub(r"[^A-Za-z0-9]+", "-", video.stem).strip("-")[:40] or "video"
    results = []
    for i, clip in enumerate(clips, 1):
        log(f"Cutting clip {i} of {len(clips)}: {clip.title}")
        path = render(video, words, clip, i, prefix=stem, style=style, watermark=watermark,
                      cut_pauses=cut_pauses)
        results.append({**clip.model_dump(), "file": str(path), "source": str(video),
                        "style": style, "watermark": watermark, "cut_pauses": cut_pauses})

    manifest = OUT_DIR / f"{stem}.clips.json"
    manifest.write_text(json.dumps(results, indent=2))
    return manifest


def upload_existing(manifest: Path, privacy: str, credit: str) -> None:
    """Upload clips the bot already made, asking about each one first."""
    if not manifest.exists():
        sys.exit(f"Not found: {manifest}\nLook in the output folder for a file ending in .clips.json")
    entries = json.loads(manifest.read_text())
    pending = [e for e in entries if not e.get("url")]
    if not pending:
        sys.exit("Every clip in this list is already uploaded.")

    print(f"{len(pending)} clips not uploaded yet. For each one: y = upload, n = skip, e = edit title.\n")
    yt = youtube_client()
    for entry in pending:
        path = Path(entry["file"])
        if not path.exists():
            print(f"Skipping, file missing: {path.name}")
            continue
        print(f"{entry['score']}/10  {entry['title']}\n    {path.name}")
        answer = input("    Upload? [y/n/e] ").strip().lower()
        if answer == "e":
            entry["title"] = input("    New title: ").strip() or entry["title"]
            answer = "y"
        if answer != "y":
            print("    skipped\n")
            continue
        clip = clip_from_entry(entry)
        entry["url"] = upload(yt, path, clip, privacy, credit)
        manifest.write_text(json.dumps(entries, indent=2))  # save after each so a crash loses nothing
        print(f"    uploaded ({privacy}): {entry['url']}\n")
    print("Done.")


# ─── Main ────────────────────────────────────────────────────────────────────
def main() -> None:
    p = argparse.ArgumentParser(description="Turn a long video into YouTube Shorts.")
    p.add_argument("source", nargs="?", help="Video file path or URL")
    p.add_argument("--upload-existing", metavar="CLIPS_JSON",
                   help="Upload clips already made, from an output/*.clips.json file")
    p.add_argument("--count", type=int, default=5, help="Max clips to make (default 5)")
    p.add_argument("--whisper", default="small", help="Whisper model: tiny, base, small, medium")
    p.add_argument("--upload", action="store_true", help="Upload clips to YouTube")
    p.add_argument("--privacy", default="private", choices=["private", "unlisted", "public"])
    p.add_argument("--style", default="full", choices=list(STYLES), help="full (zooms, glowing words) or blur")
    p.add_argument("--keep-pauses", action="store_true", help="Don't cut out pauses")
    p.add_argument("--watermark", default="", help="Small channel name under the captions, full style only")
    p.add_argument("--credit", default="", help='Credit line, e.g. "Clipped from @creator with permission"')
    args = p.parse_args()

    if args.upload_existing:
        upload_existing(Path(args.upload_existing).expanduser(), args.privacy, args.credit)
        return
    if not args.source:
        p.error("give a video file or URL, or use --upload-existing")

    try:
        manifest = make_clips(args.source, args.count, args.whisper, style=args.style, watermark=args.watermark,
                              cut_pauses=not args.keep_pauses)
    except ClipperError as e:
        sys.exit(str(e))
    entries = json.loads(manifest.read_text())
    if args.upload:
        yt = youtube_client()
        for entry in entries:
            clip = clip_from_entry(entry)
            entry["url"] = upload(yt, Path(entry["file"]), clip, args.privacy, args.credit)
            manifest.write_text(json.dumps(entries, indent=2))
            print(f"    uploaded ({args.privacy}): {entry['url']}")
    print(f"\nDone. {len(entries)} clips in {OUT_DIR}. Details: {manifest}")


if __name__ == "__main__":
    main()
