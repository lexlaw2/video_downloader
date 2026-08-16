#!/usr/bin/env python3
"""
Video Downloader — скачивание видео с YouTube и других платформ.
Основан на yt-dlp (поддержка 1000+ сайтов).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# Прокси по умолчанию (можно переопределить флагом --proxy / --no-proxy / env DOWNLOAD_PROXY)
DEFAULT_PROXY = "socks5://127.0.0.1:16431"


def _configure_stdio() -> None:
    """Windows-консоль часто в cp1251 — включаем UTF-8, чтобы не падать на стрелках."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass


def ensure_yt_dlp():
    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        print("yt-dlp не установлен. Установите зависимости:\n")
        print("  pip install -r requirements.txt\n")
        sys.exit(1)


def normalize_proxy(proxy: str | None) -> str | None:
    """Приводит адрес прокси к виду scheme://host:port."""
    if proxy is None:
        return None
    proxy = proxy.strip()
    if not proxy or proxy.lower() in ("none", "off", "false", "0"):
        return None
    if "://" not in proxy:
        # host:port или host port → socks5
        proxy = proxy.replace(" ", ":")
        proxy = f"socks5://{proxy}"
    return proxy


def resolve_proxy(cli_proxy: str | None, no_proxy: bool = False) -> str | None:
    if no_proxy:
        return None
    if cli_proxy is not None:
        return normalize_proxy(cli_proxy)
    env = os.environ.get("DOWNLOAD_PROXY") or os.environ.get("ALL_PROXY") or os.environ.get("HTTPS_PROXY")
    if env:
        return normalize_proxy(env)
    return DEFAULT_PROXY


def impersonate_available() -> bool:
    try:
        import yt_dlp
        from yt_dlp.networking.impersonate import ImpersonateTarget

        target = ImpersonateTarget.from_str("chrome")
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
            return ydl._impersonate_target_available(target)
    except Exception:
        return False


def get_impersonate_target():
    if not impersonate_available():
        return None
    from yt_dlp.networking.impersonate import ImpersonateTarget

    return ImpersonateTarget.from_str("chrome")


def normalize_url(url: str, playlist: bool) -> str:
    """Если плейлист не нужен — оставляем только конкретное видео из watch?v=...&list=..."""
    if playlist:
        return url

    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    if "youtube.com" not in host and "youtu.be" not in host:
        return url

    qs = parse_qs(parsed.query)
    video_id = (qs.get("v") or [None])[0]

    if "youtu.be" in host and parsed.path.strip("/"):
        return f"https://www.youtube.com/watch?v={parsed.path.strip('/')}"

    if video_id:
        return f"https://www.youtube.com/watch?v={video_id}"

    return url


def build_format(quality: str, audio_only: bool) -> str:
    if audio_only:
        return "bestaudio/best"

    presets = {
        "best": "bv*+ba/b",
        "1080": "bv*[height<=1080]+ba/b[height<=1080]/b",
        "720": "bv*[height<=720]+ba/b[height<=720]/b",
        "480": "bv*[height<=480]+ba/b[height<=480]/b",
        "360": "bv*[height<=360]+ba/b[height<=360]/b",
        "worst": "worst",
    }
    return presets.get(quality, quality)


def progress_hook(d: dict) -> None:
    status = d.get("status")
    if status == "downloading":
        percent = d.get("_percent_str", "").strip()
        speed = d.get("_speed_str", "").strip()
        eta = d.get("_eta_str", "").strip()
        filename = Path(d.get("filename", "")).name
        print(f"\r  {filename[:50]:<50} {percent:>7}  {speed:>10}  ETA {eta:>6}", end="", flush=True)
    elif status == "finished":
        print(f"\r  Готово: {Path(d.get('filename', '')).name}" + " " * 40)


def base_opts(
    output_dir: Path,
    quality: str,
    audio_only: bool,
    audio_format: str,
    subtitles: bool,
    playlist: bool,
    proxy: str | None = None,
    *,
    impersonate: bool = True,
    youtube_clients: list[str] | None = None,
) -> dict:
    ydl_opts: dict = {
        "outtmpl": str(output_dir / "%(title)s [%(id)s].%(ext)s"),
        "format": build_format(quality, audio_only),
        "merge_output_format": "mp4",
        "noplaylist": not playlist,
        "ignoreerrors": False,
        "retries": 10,
        "fragment_retries": 10,
        "extractor_retries": 5,
        "socket_timeout": 30,
        "progress_hooks": [progress_hook],
        "quiet": False,
        "no_warnings": False,
        "file_access_retries": 5,
    }

    if proxy:
        ydl_opts["proxy"] = proxy

    target = get_impersonate_target() if impersonate else None
    if target is not None:
        ydl_opts["impersonate"] = target

    # android/ios/web часто отдают только progressive 360p.
    # android_vr даёт adaptive-потоки до 1080p+.
    clients = youtube_clients or ["android_vr"]
    ydl_opts["extractor_args"] = {"youtube": {"player_client": clients}}
    ydl_opts["format_sort"] = ["res", "vcodec:h264", "acodec:m4a", "br"]
    ydl_opts["format_sort_force"] = False

    if audio_only:
        ydl_opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": audio_format,
                "preferredquality": "192",
            }
        ]

    if subtitles:
        ydl_opts.update(
            {
                "writesubtitles": True,
                "writeautomaticsub": True,
                "subtitleslangs": ["ru", "en"],
                "subtitlesformat": "srt",
            }
        )

    return ydl_opts


def is_ssl_error(exc: BaseException) -> bool:
    text = str(exc).upper()
    return "SSL" in text or "UNEXPECTED_EOF" in text or "EOF OCCURRED" in text


def download_one(url: str, ydl_opts: dict) -> None:
    import yt_dlp

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])


def download(
    urls: list[str],
    output_dir: Path,
    quality: str = "best",
    audio_only: bool = False,
    audio_format: str = "mp3",
    subtitles: bool = False,
    playlist: bool = False,
    proxy: str | None = DEFAULT_PROXY,
) -> int:
    ensure_yt_dlp()
    import yt_dlp

    output_dir.mkdir(parents=True, exist_ok=True)

    if proxy:
        print(f"Прокси: {proxy}")
    else:
        print("Прокси: выключен")

    errors = 0
    for raw_url in urls:
        url = normalize_url(raw_url, playlist=playlist)
        print(f"\n→ {url}")
        if url != raw_url:
            print("  (плейлист в ссылке проигнорирован — качается одно видео; флаг --playlist для всего списка)")

        attempts = [
            (
                "android_vr (HD)",
                base_opts(
                    output_dir,
                    quality,
                    audio_only,
                    audio_format,
                    subtitles,
                    playlist,
                    proxy,
                    impersonate=False,
                    youtube_clients=["android_vr"],
                ),
            ),
            (
                "android_vr + android",
                base_opts(
                    output_dir,
                    quality,
                    audio_only,
                    audio_format,
                    subtitles,
                    playlist,
                    proxy,
                    impersonate=False,
                    youtube_clients=["android_vr", "android"],
                ),
            ),
            (
                "web / mweb",
                base_opts(
                    output_dir,
                    quality,
                    audio_only,
                    audio_format,
                    subtitles,
                    playlist,
                    proxy,
                    impersonate=True,
                    youtube_clients=["web", "mweb"],
                ),
            ),
        ]

        ok = False
        last_error: BaseException | None = None
        for label, opts in attempts:
            try:
                if label != attempts[0][0]:
                    print(f"  Повторная попытка ({label})...")
                download_one(url, opts)
                ok = True
                break
            except yt_dlp.utils.DownloadError as e:
                last_error = e
                if is_ssl_error(e):
                    print(f"\n  SSL/сеть: {e}")
                    continue
                print(f"\n  Ошибка: {e}", file=sys.stderr)
                break
            except yt_dlp.utils.YoutubeDLError as e:
                last_error = e
                print(f"\n  Ошибка: {e}", file=sys.stderr)
                continue
            except KeyboardInterrupt:
                print("\n\nПрервано пользователем.")
                return 130

        if not ok:
            errors += 1
            if last_error and is_ssl_error(last_error):
                print(
                    "\nНе удалось из‑за SSL/сети. Проверьте:\n"
                    "  1) что SOCKS5-прокси запущен (сейчас ожидается 127.0.0.1:16431)\n"
                    "  2) смените узел VPN/прокси\n"
                    "  3) попробуйте socks5h://127.0.0.1:16431 (DNS через прокси)\n"
                    "  4) pip install -U \"yt-dlp[default]\" \"curl_cffi>=0.10,<0.16\" PySocks\n",
                    file=sys.stderr,
                )

    return 1 if errors else 0


def list_formats(url: str, playlist: bool = False, proxy: str | None = DEFAULT_PROXY) -> int:
    ensure_yt_dlp()
    import yt_dlp

    url = normalize_url(url, playlist=playlist)
    if proxy:
        print(f"Прокси: {proxy}")

    opts = base_opts(Path("."), "best", False, "mp3", False, playlist, proxy)
    opts["quiet"] = True
    opts["no_warnings"] = True
    opts.pop("progress_hooks", None)

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if info is None:
            print("Не удалось получить информацию о видео.", file=sys.stderr)
            return 1

        title = info.get("title", "?")
        duration = info.get("duration")
        uploader = info.get("uploader") or info.get("channel") or "?"
        print(f"\n{title}")
        print(f"Автор: {uploader}")
        if duration:
            m, s = divmod(int(duration), 60)
            h, m = divmod(m, 60)
            print(f"Длительность: {h:d}:{m:02d}:{s:02d}" if h else f"Длительность: {m}:{s:02d}")

        formats = info.get("formats") or []
        print(f"\n{'ID':<12} {'EXT':<6} {'RES':<12} {'FPS':<6} {'NOTE'}")
        print("-" * 60)
        for f in formats:
            if f.get("vcodec") == "none" and f.get("acodec") == "none":
                continue
            fid = f.get("format_id", "")
            ext = f.get("ext", "")
            height = f.get("height")
            width = f.get("width")
            res = f"{width}x{height}" if height and width else (f.get("resolution") or "-")
            fps = str(f.get("fps") or "-")
            note = f.get("format_note") or f.get("format") or ""
            print(f"{fid:<12} {ext:<6} {res:<12} {fps:<6} {note}")
    return 0


def list_video_destinations(root: Path | None = None, limit: int = 9) -> list[Path]:
    """Первые N подпапок в H:\\video (по имени)."""
    root = root or Path(r"H:\video")
    if not root.is_dir():
        return []
    dirs = [p for p in root.iterdir() if p.is_dir()]
    dirs.sort(key=lambda p: p.name.casefold())
    return dirs[:limit]


def choose_output_dir() -> Path | None:
    """Интерактивный выбор папки: клавиши 1-9 из H:\\video, 0 — свой путь."""
    root = Path(r"H:\video")
    folders = list_video_destinations(root, limit=9)

    print("\nПапка для сохранения:")
    if folders:
        for i, folder in enumerate(folders, start=1):
            print(f"  {i}) {folder.name}")
        print(f"  0) Другая папка / ввести путь")
        print(f"  Enter) {root} (корень)")
        choice = input(f"Выбор [1-{len(folders)}, 0, Enter]: ").strip()

        if choice == "":
            return root
        if choice == "0":
            custom = input(f"Путь [{root}]: ").strip() or str(root)
            return Path(custom)
        if choice.isdigit() and 1 <= int(choice) <= len(folders):
            return folders[int(choice) - 1]
        print("Неверный выбор.")
        return None

    print(f"  Подпапок в {root} не найдено.")
    custom = input(f"Путь [{root if root.is_dir() else 'downloads'}]: ").strip()
    if custom:
        return Path(custom)
    return root if root.is_dir() else Path("downloads")


def interactive(proxy: str | None = DEFAULT_PROXY) -> int:
    print("=" * 50)
    print("  Video Downloader (yt-dlp)")
    print("=" * 50)
    print("Платформы: YouTube, Vimeo, Twitch, TikTok,")
    print("           VK, Rutube, Instagram и др.")
    print(f"Прокси по умолчанию: {DEFAULT_PROXY}\n")

    url = input("URL видео или плейлиста: ").strip()
    if not url:
        print("URL не указан.")
        return 1

    proxy_in = input(f"Прокси [{proxy or 'нет'}] (Enter — оставить, none — выкл): ").strip()
    if proxy_in:
        proxy = None if proxy_in.lower() in ("none", "off", "нет", "выкл") else normalize_proxy(proxy_in)

    print("\nРежим:")
    print("  1) Видео (лучшее качество)")
    print("  2) Видео 1080p")
    print("  3) Видео 720p")
    print("  4) Только аудио (MP3)")
    print("  5) Список доступных форматов")
    choice = input("Выбор [1]: ").strip() or "1"

    want_playlist = False
    if "list=" in url and choice != "5":
        ans = input("В ссылке есть плейлист. Скачать весь плейлист? [y/N]: ").strip().lower()
        want_playlist = ans in ("y", "yes", "д", "да")

    if choice == "5":
        return list_formats(url, playlist=want_playlist, proxy=proxy)

    out = choose_output_dir()
    if out is None:
        return 1
    print(f"Сохранение в: {out}")

    quality_map = {"1": "best", "2": "1080", "3": "720"}
    audio_only = choice == "4"
    quality = quality_map.get(choice, "best")

    return download(
        urls=[url],
        output_dir=out,
        quality=quality,
        audio_only=audio_only,
        playlist=want_playlist,
        proxy=proxy,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Скачивание видео с YouTube и других платформ (yt-dlp).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Примеры:
  python download.py https://www.youtube.com/watch?v=...
  python download.py -q 720 URL
  python download.py -a URL
  python download.py --proxy socks5://127.0.0.1:16431 URL
  python download.py --proxy socks5h://127.0.0.1:16431 URL   # DNS через прокси
  python download.py --no-proxy URL
  python download.py --playlist URL
  python download.py --list-formats URL

Прокси по умолчанию: {DEFAULT_PROXY}
        """,
    )
    p.add_argument("urls", nargs="*", help="URL видео / плейлистов")
    p.add_argument("-o", "--output", default="downloads", help="Папка сохранения (по умолчанию: downloads)")
    p.add_argument(
        "-q",
        "--quality",
        default="best",
        help="Качество: best, 1080, 720, 480, 360, worst или format_id (по умолчанию: best)",
    )
    p.add_argument("-a", "--audio", action="store_true", help="Скачать только аудио")
    p.add_argument("--audio-format", default="mp3", choices=["mp3", "m4a", "opus", "wav", "flac"], help="Формат аудио")
    p.add_argument("-s", "--subtitles", action="store_true", help="Скачать субтитры (ru/en)")
    p.add_argument(
        "--playlist",
        action="store_true",
        help="Скачать весь плейлист (по умолчанию — только одно видео из ссылки)",
    )
    p.add_argument(
        "--proxy",
        default=None,
        help=f"Прокси (socks5://host:port, http://host:port). По умолчанию: {DEFAULT_PROXY}",
    )
    p.add_argument("--no-proxy", action="store_true", help="Не использовать прокси")
    p.add_argument("--list-formats", action="store_true", help="Показать доступные форматы (без скачивания)")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    proxy = resolve_proxy(args.proxy, no_proxy=args.no_proxy)

    if not args.urls:
        return interactive(proxy=proxy)

    if args.list_formats:
        if len(args.urls) != 1:
            print("Укажите один URL для --list-formats.", file=sys.stderr)
            return 1
        return list_formats(args.urls[0], playlist=args.playlist, proxy=proxy)

    return download(
        urls=args.urls,
        output_dir=Path(args.output),
        quality=args.quality,
        audio_only=args.audio,
        audio_format=args.audio_format,
        subtitles=args.subtitles,
        playlist=args.playlist,
        proxy=proxy,
    )


if __name__ == "__main__":
    _configure_stdio()
    sys.exit(main())
