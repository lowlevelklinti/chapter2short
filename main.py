import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading

try:
    import yt_dlp
except ImportError:
    print("yt-dlp is not installed. Run: pip install -r requirements.txt")
    sys.exit(1)

PRINT_LOCK = threading.Lock()
INVALID = re.compile(r'[<>:"/\\|?*]')
RESERVED = {"con", "prn", "aux", "nul"} | {f"com{i}" for i in range(1, 10)} | {f"lpt{i}" for i in range(1, 10)}


def log(msg):
    with PRINT_LOCK:
        print(msg, flush=True)


def safe_name(name):
    name = INVALID.sub("_", name or "").strip().rstrip(". ")
    if not name:
        name = "chapter"
    if len(name) > 100:
        name = name[:100].rstrip(". ")
    if name.lower() in RESERVED:
        name += "_"
    return name


def ffmpeg_present():
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=False)
        return True
    except FileNotFoundError:
        return False


def split_video(src, outdir, chapters, total):
    used = set()
    for i, ch in enumerate(chapters, 1):
        start = float(ch["start_time"])
        end = float(ch.get("end_time") or total)
        dur = end - start
        if dur <= 0.2:
            log(f"  skip '{ch['title']}' (too short)")
            continue
        base = safe_name(ch["title"])
        if base in used:
            n = 2
            while f"{base} ({n})" in used:
                n += 1
            base = f"{base} ({n})"
        used.add(base)
        out = os.path.join(outdir, base + ".mp4")
        codec = ["-c", "copy"]
        if src.lower().endswith((".webm", ".mkv")):
            codec = ["-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac"]
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
               "-ss", f"{start:.3f}", "-i", src, "-t", f"{dur:.3f}",
               *codec, "-avoid_negative_ts", "make_zero", out]
        try:
            subprocess.run(cmd, check=True)
            log(f"  [{i}/{len(chapters)}] {base}.mp4")
        except subprocess.CalledProcessError:
            log(f"  [{i}/{len(chapters)}] FAILED: {base}.mp4")


def process_url(url):
    if not ffmpeg_present():
        log("ffmpeg not found on PATH, cannot split. Install ffmpeg first.")
        return
    tmp = tempfile.mkdtemp(prefix="chapter2short_")
    try:
        opts = {
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "outtmpl": os.path.join(tmp, "%(title).120B [%(id)s].%(ext)s"),
            "noplaylist": True,
            "yes_playlist": False,
            "quiet": True,
            "no_warnings": True,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            log("Fetching video info ...")
            info = ydl.extract_info(url, download=False)
            chapters = info.get("chapters")
            if not chapters:
                log("This video has no chapters.")
                return
            title = info.get("title") or "video"
            outdir = os.path.join(os.getcwd(), safe_name(title))
            os.makedirs(outdir, exist_ok=True)
            log(f"Downloading: {title}")
            info = ydl.extract_info(url, download=True)
            src = ydl.prepare_filename(info)
            if not os.path.exists(src):
                log("Download failed.")
                return
            total = info.get("duration") or 0
            log(f"Splitting {len(chapters)} chapters into '{safe_name(title)}' ...")
            split_video(src, outdir, chapters, total)
            log(f"Done -> {outdir}")
    except Exception as e:
        log(f"Error: {e}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    if not ffmpeg_present():
        print("Warning: ffmpeg not found on PATH. Splitting will not work.")
        print("Install ffmpeg: winget install Gyan.FFmpeg")
        print()
    print("chapter2short - paste a YouTube link, and get a simple short for each chapter.")
    print("Type 'exit' to quit.")
    while True:
        try:
            url = input(">> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not url:
            continue
        if url.lower() in ("exit", "quit"):
            break
        threading.Thread(target=process_url, args=(url,), daemon=True).start()


if __name__ == "__main__":
    main()
