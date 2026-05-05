# Unmanic keep-preferred-languages plugin bundle

This bundle contains:
- `docker-compose.yml` for Unmanic on your TrueNAS paths
- a custom Unmanic plugin that:
  - keeps only Japanese, Dutch, English, and German audio/subtitle streams
  - sorts audio streams with a normal preference of `nld,eng,deu,jpn`
  - sorts subtitle streams with a normal preference of `nld,eng,deu,jpn`
  - keeps Japanese subtitles but never makes them the default subtitle by default
  - uses Japanese audio as the default only when the file appears to be Japanese-original
  - preserves video, chapters, data streams, and optionally attachments
  - skips files that would end up with no allowed audio track

## Files

- `keep_preferred_languages_default/`
  - `plugin.py`

## Suggested install flow

1. Start Unmanic with the provided compose file.
2. Add the `keep_preferred_languages_default` folder to your custom Unmanic plugin repo's `source/` directory.
3. Push the repo so the Unmanic plugin repository rebuilds.
4. Update or reinstall the plugin in Unmanic.
5. Add the plugin to the library that points at `/library`.
6. Configure the plugin settings to:
   - Preferred Audio Languages: `nld,eng,deu,jpn`
   - Preferred Audio Default Languages: `nld,eng,deu`
   - Preferred Audio Default Languages for Japanese-original: `jpn,nld,eng,deu`
   - Preferred Subtitle Languages: `nld,eng,deu,jpn`
   - Preferred Subtitle Default Languages: `nld,eng,deu`
   - Allowed Audio Languages: `jpn,nld,eng,deu`
   - Allowed Subtitle Languages: `jpn,nld,eng,deu`

## Japanese-original detection

This plugin cannot know the real original language of the work with perfect certainty from container metadata alone.

It therefore uses a conservative heuristic:
- treat the file as Japanese-original if the current default audio track is Japanese
- also treat the file as Japanese-original if all kept audio tracks are Japanese

With that heuristic:
- Japanese audio can become default for likely Japanese-original files
- Japanese subtitles are kept, but by default they are never made the default subtitle track

## Notes

- This plugin remuxes only. It does not re-encode video or audio.
- The probe settings are intentionally high to cope better with difficult subtitle streams such as PGS.
- Matroska attachments are disabled by default to avoid failures on embedded font attachments in some MKV files.
