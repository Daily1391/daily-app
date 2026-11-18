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
                                  music=music, music_volume=music_volume, sfx=sfx)
                    manifest = clipper.make_clips(
                        source, count, "base" if speed == "Fast" else "small", log=st.write,
                        style=style, watermark=watermark, cut_pauses=cut_pauses,
                        music=music, music_volume=VOLUMES[music_volume], sfx=sfx,
                    )
                except Exception as e:  # show any failure in the page, not a crash
                    status.update(label="Something went wrong", state="error")
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
                st.caption(f"Score {entry['score']}/10 · {entry['end'] - entry['start']:.0f}s · {entry['reason']}")
                if entry.get("url"):
                    st.markdown(f"**{entry['title']}**")
                    st.success(f"Posted: {entry['url']}")
                else:
                    entry["title"] = st.text_input("Title", entry["title"], key=f"t{chosen}{i}", max_chars=100)
                    new_text = st.text_input("On-screen text", entry.get("overlay", ""), key=f"o{chosen}{i}",
                                             help="The fixed text at the top of the video")
                    source = Path(entry.get("source", ""))
                    if new_text != entry.get("overlay", ""):
                        if entry.get("source") and source.exists():
                            if st.button("Update video", key=f"r{chosen}{i}"):
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
                                                   sfx=entry.get("sfx", False))
                                    tmp.replace(path)
                                    manifest.write_text(json.dumps(entries, indent=2))
                                st.rerun()
                        else:
                            st.caption("Can't change the text on clips made before this update.")
                    if path.exists() and st.checkbox("Upload this one", key=f"u{chosen}{i}"):
                        selected.append(entry)

    if any(not e.get("url") for e in entries):
        if st.button(f"Upload {len(selected)} selected", type="primary", disabled=not selected):
            save_settings(privacy=privacy, credit=credit)
            manifest.write_text(json.dumps(entries, indent=2))  # keep edited titles
            try:
                yt = clipper.youtube_client()
                bar = st.progress(0.0)
                for n, entry in enumerate(selected, 1):
                    clip = clipper.clip_from_entry(entry)
                    entry["url"] = clipper.upload(yt, Path(entry["file"]), clip, privacy, credit)
                    manifest.write_text(json.dumps(entries, indent=2))
                    bar.progress(n / len(selected), text=f"Uploaded {n} of {len(selected)}")
            except Exception as e:
                st.error(f"Upload stopped: {e}")
            else:
                st.rerun()
