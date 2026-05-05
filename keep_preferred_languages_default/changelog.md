## 0.0.3

- Remove anime-specific detection and settings
- Make Japanese the highest global priority for both audio and subtitles
- Keep Japanese audio and subtitle tracks by default
- Apply one shared priority list to both audio and subtitles

## 0.0.2

- Add anime-specific audio priority
- Detect anime files by configurable path keywords
- Allow anime audio priorities to extend the normal allowed audio list
- Keep subtitle priorities unchanged for anime by default

## 0.0.1

- Initial release
- Keep only selected audio/subtitle languages
- Reorder streams by preferred language order
- Set default audio and subtitle tracks
- Skip files with no allowed audio remaining


## v0.0.4
- Added optional preservation of Matroska attachments.
- Default is now to skip attachments during remux to avoid FFmpeg failures on files with embedded font/attachment streams.
