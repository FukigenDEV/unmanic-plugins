# -*- coding: utf-8 -*-

import json
import logging
import subprocess
from typing import List, Optional, Tuple

from unmanic.libs.unplugins.settings import PluginSettings

logger = logging.getLogger("Unmanic.Plugin.keep_preferred_languages_default")


LANG_ALIASES = {
    # Japanese
    "jpn": "jpn",
    "ja": "jpn",
    "jp": "jpn",
    "japanese": "jpn",
    # Dutch
    "nld": "nld",
    "dut": "nld",
    "nl": "nld",
    "dutch": "nld",
    "nederlands": "nld",
    # English
    "eng": "eng",
    "en": "eng",
    "english": "eng",
    # German
    "deu": "deu",
    "ger": "deu",
    "de": "deu",
    "german": "deu",
    "deutsch": "deu",
    # Undefined / unknown
    "und": "und",
    "unknown": "und",
    "": "und",
}


class Settings(PluginSettings):
    settings = {
        "Preferred Languages": "jpn,nld,eng,deu",
        "Allowed Audio Languages": "jpn,nld,eng,deu",
        "Allowed Subtitle Languages": "jpn,nld,eng,deu",
        "Skip file if no allowed audio remains": True,
        "Preserve Matroska Attachments": False,
    }

    def __init__(self, *args, **kwargs):
        super(Settings, self).__init__(*args, **kwargs)
        self.form_settings = {
            "Preferred Languages": {
                "label": "Preferred language order for audio and subtitles (comma separated, highest priority first)",
                "tooltip": "Examples: jpn,nld,eng,deu or ja,nl,en,de. Two-letter and common aliases are normalized.",
            },
            "Allowed Audio Languages": {
                "label": "Allowed audio languages (comma separated)",
                "tooltip": "Only audio tracks in these languages are kept.",
            },
            "Allowed Subtitle Languages": {
                "label": "Allowed subtitle languages (comma separated)",
                "tooltip": "Only subtitle tracks in these languages are kept.",
            },
            "Skip file if no allowed audio remains": {
                "label": "Skip file if no allowed audio remains",
                "tooltip": "Recommended safety option. Prevents stripping all audio from files that do not contain any allowed language.",
            },
            "Preserve Matroska Attachments": {
                "label": "Preserve Matroska attachments (fonts, cover art)",
                "tooltip": "Disabled by default because some MKV attachment streams can make FFmpeg remux jobs fail. Enable only if you specifically need embedded fonts or cover art preserved.",
            },
        }


def _normalize_lang(value: Optional[str]) -> str:
    if value is None:
        return "und"
    normalized = str(value).strip().lower()
    return LANG_ALIASES.get(normalized, normalized)


def _parse_lang_list(value: str) -> List[str]:
    if not value:
        return []
    items = []
    for part in value.split(","):
        lang = _normalize_lang(part)
        if lang and lang not in items:
            items.append(lang)
    return items


def _run_ffprobe(path: str) -> Optional[dict]:
    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_streams",
        "-show_format",
        path,
    ]
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        return json.loads(result.stdout)
    except Exception as exc:
        logger.warning("ffprobe failed for '%s': %s", path, exc)
        return None


def _stream_disposition_string(stream: dict, want_default: bool) -> str:
    disposition = stream.get("disposition") or {}
    flags = [name for name, value in disposition.items() if value and name != "default"]
    if want_default:
        flags.insert(0, "default")
    return "+".join(flags) if flags else "0"


def _extract_streams(probe: dict) -> Tuple[List[dict], List[dict], List[dict], List[dict], List[dict]]:
    video = []
    audio = []
    subtitle = []
    data_streams = []
    attachments = []

    for stream in probe.get("streams", []):
        codec_type = stream.get("codec_type")
        tags = stream.get("tags") or {}
        item = {
            "src_index": stream.get("index"),
            "codec_type": codec_type,
            "lang": _normalize_lang(tags.get("language")),
            "tags": tags,
            "disposition": stream.get("disposition") or {},
        }
        if codec_type == "video":
            video.append(item)
        elif codec_type == "audio":
            audio.append(item)
        elif codec_type == "subtitle":
            subtitle.append(item)
        elif codec_type == "data":
            data_streams.append(item)
        elif codec_type == "attachment":
            attachments.append(item)
    return video, audio, subtitle, data_streams, attachments


def _sort_kept(streams: List[dict], preferred: List[str]) -> List[dict]:
    rank = {lang: idx for idx, lang in enumerate(preferred)}
    return sorted(streams, key=lambda s: (rank.get(s["lang"], 999), s["src_index"]))


def _current_default_position(streams: List[dict]) -> Optional[int]:
    for pos, stream in enumerate(streams):
        if (stream.get("disposition") or {}).get("default"):
            return pos
    return None


def _plan_changes(probe: dict, settings: Settings) -> Optional[dict]:
    preferred = _parse_lang_list(settings.get_setting("Preferred Languages"))
    allowed_audio = set(_parse_lang_list(settings.get_setting("Allowed Audio Languages")))
    allowed_subs = set(_parse_lang_list(settings.get_setting("Allowed Subtitle Languages")))
    skip_if_no_audio = bool(settings.get_setting("Skip file if no allowed audio remains"))
    preserve_attachments = bool(settings.get_setting("Preserve Matroska Attachments"))

    video, audio, subtitle, data_streams, attachments = _extract_streams(probe)
    if not video:
        return None

    kept_audio_original = [s for s in audio if s["lang"] in allowed_audio]
    kept_subs_original = [s for s in subtitle if s["lang"] in allowed_subs]

    if skip_if_no_audio and audio and not kept_audio_original:
        logger.info("Skipping file because no allowed audio track remains after filtering.")
        return None

    kept_audio_sorted = _sort_kept(kept_audio_original, preferred)
    kept_subs_sorted = _sort_kept(kept_subs_original, preferred)

    audio_removed = len(kept_audio_original) != len(audio)
    subs_removed = len(kept_subs_original) != len(subtitle)
    audio_reordered = [s["src_index"] for s in kept_audio_original] != [s["src_index"] for s in kept_audio_sorted]
    subs_reordered = [s["src_index"] for s in kept_subs_original] != [s["src_index"] for s in kept_subs_sorted]

    audio_default_pos = _current_default_position(kept_audio_original)
    subs_default_pos = _current_default_position(kept_subs_original)
    audio_default_wrong = bool(kept_audio_sorted) and not (
        audio_default_pos is not None
        and kept_audio_original[audio_default_pos]["src_index"] == kept_audio_sorted[0]["src_index"]
        and sum(1 for s in kept_audio_original if (s.get("disposition") or {}).get("default")) == 1
    )
    subs_default_wrong = bool(kept_subs_sorted) and not (
        subs_default_pos is not None
        and kept_subs_original[subs_default_pos]["src_index"] == kept_subs_sorted[0]["src_index"]
        and sum(1 for s in kept_subs_original if (s.get("disposition") or {}).get("default")) == 1
    )

    needs_processing = any([
        audio_removed,
        subs_removed,
        audio_reordered,
        subs_reordered,
        audio_default_wrong,
        subs_default_wrong,
    ])

    if not needs_processing:
        return None

    return {
        "video": video,
        "audio": kept_audio_sorted,
        "subtitle": kept_subs_sorted,
        "data": data_streams,
        "attachments": attachments if preserve_attachments else [],
    }


def _build_ffmpeg_command(file_in: str, file_out: str, plan: dict) -> List[str]:
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-y",
        "-i",
        file_in,
        "-map_metadata",
        "0",
        "-map_chapters",
        "0",
        "-c",
        "copy",
    ]

    ordered_streams = []
    ordered_streams.extend(plan["video"])
    ordered_streams.extend(plan["audio"])
    ordered_streams.extend(plan["subtitle"])
    ordered_streams.extend(plan["data"])
    ordered_streams.extend(plan["attachments"])

    audio_out_idx = 0
    sub_out_idx = 0

    for stream in ordered_streams:
        src_index = stream["src_index"]
        cmd.extend(["-map", f"0:{src_index}"])

    for output_index, stream in enumerate(ordered_streams):
        stream_type = stream["codec_type"]
        if stream_type == "audio":
            want_default = audio_out_idx == 0
            audio_out_idx += 1
            cmd.extend([
                f"-disposition:a:{audio_out_idx - 1}",
                _stream_disposition_string(stream, want_default),
            ])
        elif stream_type == "subtitle":
            want_default = sub_out_idx == 0
            sub_out_idx += 1
            cmd.extend([
                f"-disposition:s:{sub_out_idx - 1}",
                _stream_disposition_string(stream, want_default),
            ])
        else:
            cmd.extend([
                f"-disposition:{output_index}",
                _stream_disposition_string(stream, False),
            ])

    cmd.append(file_out)
    return cmd


def on_library_management_file_test(data):
    abspath = data.get("path")
    if not abspath:
        return data

    if data.get("library_id"):
        settings = Settings(library_id=data.get("library_id"))
    else:
        settings = Settings()

    probe = _run_ffprobe(abspath)
    if not probe:
        return data

    plan = _plan_changes(probe, settings)
    if plan is not None:
        data["add_file_to_pending_tasks"] = True
        logger.debug("File '%s' requires preferred-language cleanup.", abspath)
    return data


def on_worker_process(data):
    data["exec_command"] = []
    data["repeat"] = False

    file_in = data.get("file_in")
    file_out = data.get("file_out")
    if not file_in or not file_out:
        return data

    if data.get("library_id"):
        settings = Settings(library_id=data.get("library_id"))
    else:
        settings = Settings()

    probe = _run_ffprobe(file_in)
    if not probe:
        return data

    plan = _plan_changes(probe, settings)
    if plan is None:
        return data

    data["exec_command"] = _build_ffmpeg_command(file_in, file_out, plan)
    logger.debug("Prepared ffmpeg command for '%s'.", file_in)
    return data
