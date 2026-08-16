# Video Downloader

Скрипт для скачивания видео с YouTube, Vimeo, Twitch, TikTok, VK, Rutube, Instagram и других платформ (через [yt-dlp](https://github.com/yt-dlp/yt-dlp)).

## Установка

```bash
cd video_downloader
pip install -r requirements.txt
```

Для слияния видео+аудио и конвертации в MP3 желателен [FFmpeg](https://ffmpeg.org/download.html) в `PATH`.

## Использование

### Интерактивный режим

```bash
python download.py
```

Или двойной клик по `download.bat`.

### Командная строка

```bash
# Лучшее качество
python download.py "https://www.youtube.com/watch?v=XXXX"

# 720p
python download.py -q 720 "URL"

# Только аудио (MP3)
python download.py -a "URL"

# Несколько ссылок в указанную папку
python download.py -o D:\Videos "URL1" "URL2"

# С субтитрами
python download.py -s "URL"

# Список форматов (без скачивания)
python download.py --list-formats "URL"

# Весь плейлист
python download.py --playlist "URL"

# Другой прокси / без прокси
python download.py --proxy socks5h://127.0.0.1:16431 "URL"
python download.py --no-proxy "URL"
```

По умолчанию используется SOCKS5 `socks5://127.0.0.1:16431`.  
`socks5h://` — то же самое, но DNS тоже через прокси (часто лучше при блокировках).

Через bat-файл те же аргументы:

```bat
download.bat -q 1080 "https://youtu.be/XXXX"
```

## Параметры

| Флаг | Описание |
|------|----------|
| `-o`, `--output` | Папка сохранения (по умолчанию `downloads`) |
| `-q`, `--quality` | `best`, `1080`, `720`, `480`, `360`, `worst` или id формата |
| `-a`, `--audio` | Только аудио |
| `--audio-format` | `mp3`, `m4a`, `opus`, `wav`, `flac` |
| `-s`, `--subtitles` | Субтитры ru/en |
| `--playlist` | Скачать весь плейлист |
| `--proxy` | Прокси (`socks5://host:port`, `http://host:port`) |
| `--no-proxy` | Без прокси |
| `--list-formats` | Показать доступные форматы |

## Важно

Используйте только для контента, на скачивание которого у вас есть право (свой контент, Creative Commons, явное разрешение). Соблюдайте условия использования платформ и авторское право.
