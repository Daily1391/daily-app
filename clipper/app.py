"""Clipper web app. Start it by double-clicking Clipper.command (Mac)."""

import json
import os
import subprocess
import tempfile
from pathlib import Path

import streamlit as st

import clipper

HERE = Path(__file__).parent
ENV_FILE = HERE / ".env"
SETTINGS_FILE = HERE / "settings.json"

st.set_page_config(page_title="Clipper", page_icon="✂️", layout="wide")


# ─── Saved settings ──────────────────────────────────────────────────────────
def load_key() -> str:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return os.environ["ANTHROPIC_API_KEY"]
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            if line.startswith("ANTHROPIC_API_KEY="):
                return line.split("=", 1)[1].strip()
    return ""


def load_settings() -> dict:
    try:
        return json.loads(SETTINGS_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_settings(**changes) -> None:
    SETTINGS_FILE.write_text(json.dumps({**load_settings(), **changes}, indent=2))


VOLUMES = {"Quiet": 0.12, "Medium": 0.22, "Loud": 0.35}

key = load_key()
if key:
    os.environ["ANTHROPIC_API_KEY"] = key
settings = load_settings()


# ─── Sidebar: setup status ───────────────────────────────────────────────────
with st.sidebar:
    st.header("Setup")
    if key:
        st.success("Claude key saved")
        if st.button("Change key"):
            ENV_FILE.unlink(missing_ok=True)
            os.environ.pop("ANTHROPIC_API_KEY", None)
            st.rerun()
    else:
        new_key = st.text_input("Claude API key", type="password",
                                help="From platform.claude.com. Saved only on this computer.")
        if st.button("Save key") and new_key.strip():
            ENV_FILE.write_text(f"ANTHROPIC_API_KEY={new_key.strip()}\n")
            ENV_FILE.chmod(0o600)
            st.rerun()

    if (HERE / "token.json").exists():
        st.success("YouTube connected")
    elif (HERE / "client_secret.json").exists():
        st.info("YouTube will ask you to log in on your first upload")
    else:
        st.warning("YouTube not set up. Add client_secret.json to the clipper folder.")

    st.divider()
    st.subheader("Music")
    for mood in clipper.MOODS:
        (clipper.MUSIC_DIR / mood).mkdir(parents=True, exist_ok=True)
    counts = {m: sum(p.suffix.lower() in clipper.AUDIO_EXT for p in (clipper.MUSIC_DIR / m).rglob("*"))
              for m in clipper.MOODS}
    if sum(counts.values()):
        st.caption(" · ".join(f"{m}: {n}" for m, n in counts.items()))
    else:
        st.warning("No music yet. Put tracks you're allowed to use in the music folders.")
    if st.button("Open music folder"):
        subprocess.run(["open", str(clipper.MUSIC_DIR)])
    st.caption("Free, safe tracks: YouTube Studio → Audio Library → Download. "
               "Popular songs get your clips claimed or muted.")
    st.divider()
    st.caption("Only post clips from creators who allow it. Read every title before posting.")


st.title("✂️ Clipper")
make_tab, clips_tab = st.tabs(["Make clips", "My clips"])


# ─── Tab 1: make clips ───────────────────────────────────────────────────────
with make_tab:
    st.write("Drop in a long video. Claude finds the best moments and cuts them into Shorts.")
    uploaded = st.file_uploader("Video file", type=["mp4", "mov", "mkv", "webm", "m4v"])
    link = st.text_input("…or paste a video link")

    c1, c2 = st.columns(2)
    count = c1.slider("How many clips", 1, 10, 5)
    focus_names = {"mix": "Mix", "funny": "Mostly funny", "hype": "Mostly hype"}
    focus = c1.radio("Look for", list(focus_names), format_func=focus_names.get, horizontal=True,
                     index=list(focus_names).index(settings.get("focus", "mix")))
    speed = c2.radio("Transcription", ["Accurate (slower)", "Fast"], horizontal=True)

    c3, c4 = st.columns(2)
    style_names = list(clipper.STYLES)
    style = c3.radio("Look", style_names, format_func=clipper.STYLES.get, horizontal=True,
                     index=style_names.index(settings.get("style", "full")))
    watermark = c4.text_input("Watermark (your channel name)", settings.get("watermark", ""),
                              disabled=style != "full", help="Small text under the captions")
    cut_pauses = st.checkbox("Cut out pauses (keeps people watching)", value=settings.get("cut_pauses", True))
    c5, c6, c7 = st.columns(3)
    music = c5.checkbox("Background music", value=settings.get("music", True),
                        help="Picks a track from your music folder that fits the clip's mood")
    music_volume = c6.select_slider("Music volume", ["Quiet", "Medium", "Loud"],
                                    value=settings.get("music_volume", "Medium"), disabled=not music)
    sfx = c7.checkbox("Sound effects", value=settings.get("sfx", True),
                      help="A boom on the hook and whooshes on the zoom-ins")

    if st.button("Make clips", type="primary", disabled=not key):
        if not uploaded and not link.strip():
            st.error("Add a video file or a link first.")
        else:
            if uploaded:
                src_dir = clipper.OUT_DIR / "source"
                src_dir.mkdir(parents=True, exist_ok=True)
                source = src_dir / uploaded.name
                if not source.exists() or source.stat().st_size != uploaded.size:
                    with open(source, "wb") as f:
                        f.write(uploaded.getbuffer())
                source = str(source)
            else:
                source = link.strip()

            with st.status("Working… a long video can take 10 to 20 minutes.", expanded=True) as status:
                try:
                    save_settings(style=style, watermark=watermark, cut_pauses=cut_pauses,
                                  music=music, music_volume=music_volume, sfx=sfx, focus=focus)
                    bars = {}

                    def transcribe_progress(p):  # bar appears under "Transcribing" on first update
                        if "bar" not in bars:
                            bars["bar"] = st.progress(0.0)
                        bars["bar"].progress(p, text=f"Transcribed {int(p * 100)}%")

                    manifest = clipper.make_clips(
                        source, count, "base" if speed == "Fast" else "small", log=st.write,
                        style=style, watermark=watermark, cut_pauses=cut_pauses,
                        music=music, music_volume=VOLUMES[music_volume], sfx=sfx, focus=focus,
                        progress=transcribe_progress,
                    )
                except Exception as e:  # show any failure in the page, not a crash
                    status.update(label="Something went wrong", state="error", expanded=True)
                    st.error(str(e) or e.__class__.__name__)
                else:
                    status.update(label="Done! Open the My clips tab.", state="complete")
                    st.session_state["manifest"] = manifest.name
    if not key:
        st.info("Add your Claude API key in the sidebar to start.")


# ─── Tab 2: review and upload ────────────────────────────────────────────────
with clips_tab:
    manifests = sorted(clipper.OUT_DIR.glob("*.clips.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not manifests:
        st.info("No clips yet. Make some in the first tab.")
        st.stop()

    names = [m.name for m in manifests]
    default = names.index(st.session_state["manifest"]) if st.session_state.get("manifest") in names else 0
    chosen = st.selectbox("Video", names, index=default,
                          format_func=lambda n: n.removesuffix(".clips.json"))
    manifest = clipper.OUT_DIR / chosen
    entries = json.loads(manifest.read_text())

    # Facecam layout: check the box, fix it if needed, and re-cut every clip with it
    src = Path(entries[0].get("source", "")) if entries and entries[0].get("source") else None
    if src and src.exists() and any(not e.get("url") for e in entries):
        is_stream = any(e.get("style") == "stream" for e in entries)
        with st.expander("Facecam layout (streamer on top, gameplay below)", expanded=is_stream):
            cam = next((e.get("cam") for e in entries if e.get("cam")), None)
            if not cam:
                with st.spinner("Looking for the facecam..."):
                    cam = clipper.find_facecam(src)
            if not cam:
                st.info("Couldn't find a face automatically. Drag the sliders to box the facecam.")
                cam = [0.0, 0.6, 0.25, 0.4]
            k = chosen
            s1, s2 = st.columns(2)
            left = s1.slider("Left edge", 0, 100, int(cam[0] * 100), key=f"cx{k}")
            top = s1.slider("Top edge", 0, 100, int(cam[1] * 100), key=f"cy{k}")
            width = s2.slider("Width", 5, 100, int(cam[2] * 100), key=f"cw{k}")
            height = s2.slider("Height", 5, 100, int(cam[3] * 100), key=f"ch{k}")
            box = [left / 100, top / 100, min(width, 100 - left) / 100, min(height, 100 - top) / 100]
            preview = clipper.cam_preview(src, box, clipper.OUT_DIR / f"{chosen}.preview.png")
            st.image(str(preview), caption="The green box goes in the top half of every clip")
            todo = [e for e in entries if not e.get("url")]
            if st.button(f"Use this layout on {len(todo)} clips", type="primary"):
                words = clipper.transcribe(src, "small")  # cached, so fast
                bar = st.progress(0.0)
                for n, (i, e) in enumerate([(i, e) for i, e in enumerate(entries) if not e.get("url")], 1):
                    e["style"], e["cam"] = "stream", box
                    path = Path(e["file"])
                    tmp = path.with_name(path.stem + ".new.mp4")
                    clipper.render(src, words, clipper.clip_from_entry(e), i + 1, out=tmp, style="stream",
                                   watermark=e.get("watermark", ""), cut_pauses=e.get("cut_pauses", False),
                                   music=e.get("music", False), music_volume=e.get("music_volume", 0.22),
                                   sfx=e.get("sfx", False), cam=box)
                    tmp.replace(path)
                    manifest.write_text(json.dumps(entries, indent=2))
                    bar.progress(n / len(todo), text=f"Re-cut {n} of {len(todo)}")
                st.rerun()

    c1, c2 = st.columns([1, 2])
    privacy = c1.selectbox("Post as", ["public", "unlisted", "private"],
                           index=["public", "unlisted", "private"].index(settings.get("privacy", "private")))
    credit = c2.text_input("Credit line (goes in every description)", settings.get("credit", ""))

    selected = []
    cols = st.columns(3)
    for i, entry in enumerate(entries):
        with cols[i % 3]:
            with st.container(border=True):
                path = Path(entry["file"])
                if path.exists():
                    st.video(str(path))
                else:
                    st.warning("Video file missing")
                kind = entry.get("kind", "").capitalize()
                st.caption(f"{kind + ' · ' if kind else ''}Score {entry['score']}/10 · "
                           f"{entry['end'] - entry['start']:.0f}s · {entry['reason']}")
                if entry.get("url"):
                    st.markdown(f"**{entry['title']}**")
                    st.success(f"Posted: {entry['url']}")
                else:
                    entry["title"] = st.text_input("Title", entry["title"], key=f"t{chosen}{i}", max_chars=100)
                    new_text = st.text_input("On-screen text", entry.get("overlay", ""), key=f"o{chosen}{i}",
                                             help="The fixed text at the top of the video")
                    source = Path(entry.get("source", ""))
                    # Update video is always shown, so typing then clicking works without pressing Enter
                    if entry.get("source") and source.exists():
                        if st.button("Update video", key=f"r{chosen}{i}",
                                     help="Type new text, then click to re-cut this clip with it"):
                            with st.spinner("Re-cutting this clip..."):
                                entry["overlay"] = new_text
                                words = clipper.transcribe(source, "small")  # cached, so fast
                                tmp = path.with_name(path.stem + ".new.mp4")  # keep the old clip if this fails
                                clipper.render(source, words, clipper.clip_from_entry(entry), i + 1, out=tmp,
                                               style=entry.get("style", "blur"),
                                               watermark=entry.get("watermark", ""),
                                               cut_pauses=entry.get("cut_pauses", False),
                                               music=entry.get("music", False),
                                               music_volume=entry.get("music_volume", 0.22),
                                               sfx=entry.get("sfx", False),
                                               cam=entry.get("cam"))
                                tmp.replace(path)
                                manifest.write_text(json.dumps(entries, indent=2))
                            st.rerun()
                    else:
                        st.caption("This clip was made before text editing existed, or its source "
                                   "video was moved. Make clips from the video again to edit it.")
                    if path.exists() and st.checkbox("Upload this one", key=f"u{chosen}{i}"):
                        selected.append(entry)

    if any(not e.get("url") for e in entries):
        if st.button(f"Upload {len(selected)} selected", type="primary", disabled=not selected):
            save_settings(privacy=privacy, credit=credit)
            manifest.write_text(json.dumps(entries, indent=2))  # keep edited titles
            try:
                yt = clipper.youtube_client()
                total = len(selected)
                bar = st.progress(0.0, text=f"Uploading 1 of {total}...")
                for n, entry in enumerate(selected, 1):
                    clip = clipper.clip_from_entry(entry)

                    def show(p, n=n):
                        bar.progress(min((n - 1 + p) / total, 1.0),
                                     text=f"Uploading {n} of {total}: {int(p * 100)}%")

                    entry["url"] = clipper.upload(yt, Path(entry["file"]), clip, privacy, credit,
                                                  progress=show)
                    manifest.write_text(json.dumps(entries, indent=2))
                    bar.progress(n / len(selected), text=f"Uploaded {n} of {len(selected)}")
            except Exception as e:
                msg = str(e)
                if "uploadLimitExceeded" in msg:
                    st.error("YouTube says this channel has hit its upload limit for now. It resets "
                             "within about 24 hours. Verifying your channel at youtube.com/verify raises it.")
                elif "quotaExceeded" in msg:
                    st.error("You've used today's upload allowance for your Google project (about 6 "
                             "videos). It resets at midnight Pacific time.")
                elif "SSL" in msg or "timed out" in msg or "Connection" in msg:
                    st.error("The internet connection dropped during the upload. Click Upload again; "
                             "clips that already went up won't be sent twice.")
                else:
                    st.error(f"Upload stopped: {e}")
            else:
                st.rerun()
