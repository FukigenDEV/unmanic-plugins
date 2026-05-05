Keeps only allowed audio and subtitle languages, sorts them by preferred order, and sets the first remaining audio and subtitle streams as default.

Default behavior:
- Preferred order for audio and subtitles: `jpn,nld,eng,deu`
- Allowed audio languages: `jpn,nld,eng,deu`
- Allowed subtitle languages: `jpn,nld,eng,deu`
- Skip files that would end up with no allowed audio track

The plugin remuxes without re-encoding and preserves video, chapters, data streams, and attachments.
