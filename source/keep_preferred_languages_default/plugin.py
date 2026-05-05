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
        "Preferred Audio Languages": "nld,eng,deu,jpn",
        "Preferred Audio Default Languages": "nld,eng,deu",
        "Preferred Audio Default Languages for Japanese-original": "jpn,nld,eng,deu",
        "Preferred Subtitle Languages": "nld,eng,deu,jpn",
        "Preferred Subtitle Default Languages": "nld,eng,deu",
        "Allowed Audio Languages": "jpn,nld,eng,deu",
        "Allowed Subtitle Languages": "jpn,nld,eng,deu",
        "Skip file if no allowed audio remains": True,
        "Preserve Matroska Attachments": False,
        "ffprobe Analyze Duration": "100000000",
        "ffprobe Probe Size": "100000000",
        "ffmpeg Analyze Duration": "100000000",
        "ffmpeg Probe Size": "100000000",
    }

    def __init__(self, *args, **kwargs):
        super(Settings, self).__init__(*args, **kwargs)
        self.form_settings = {
            "Preferred Audio Languages": {
                "label": "Preferred audio order (comma separated, highest priority first)",
                "tooltip": "Used for sorting kept audio streams. Japanese can be kept without always becoming default.",
            },
            "Preferred Audio Default Languages": {
                "label": "Preferred default audio languages for normal content",
                "tooltip": "Used to choose the default audio track when the source does not appear to be Japanese-original.",
            },
            "Preferred Audio Default Languages for Japanese-original": {
                "label": "Preferred default audio languages for Japanese-original content",
                "tooltip": "Used to choose the default audio track when the plugin infers the source is Japanese-original. Default: jpn,nld,eng,deu.",
            },
            "Preferred Subtitle Languages": {
                "label": "Preferred subtitle order (comma separated, highest priority first)",
                "tooltip": "Used for sorting kept subtitle streams. Default keeps Japanese subtitles but orders them after Dutch, English and German.",
            },
            "Preferred Subtitle Default Languages": {
                "label": "Preferred default subtitle languages",
                "tooltip": "Used to choose the default subtitle track. By default Japanese is excluded, so Japanese subtitles are kept but never made default.",
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
                "label": "Preserve Matroska attachments",
                "tooltip": "Disabled by default to avoid failures on embedded fonts/attachments in some MKV files. Turn on only if you need to preserve embedded subtitle fonts.",
            },
            "ffprobe Analyze Duration": {
                "label": "ffprobe analyze duration (microseconds)",
                "tooltip": "Increase this for files with hard-to-probe subtitle streams such as PGS. Default: 100000000.",
            },
            "ffprobe Probe Size": {
                "label": "ffprobe probe size (bytes)",
                "tooltip": "Increase this for files with hard-to-probe subtitle streams such as PGS. Default: 100000000.",
            },
            "ffmpeg Analyze Duration": {
                "label": "ffmpeg analyze duration (microseconds)",
                "tooltip": "Input probing duration for the remux step. Default: 100000000.",
            },
            "ffmpeg Probe Size": {
                "label": "ffmpeg probe size (bytes)",
                "tooltip": "Input probing size for the remux step. Default: 100000000.",
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
    for part in str(value).split(","):
        lang = _normalize_lang(part)
        if lang and lang not in items:
            items.append(lang)
    return items


def _parse_positive_int(value, default: int) -> int:
    try:
        parsed = int(str(value).strip())
        if parsed > 0:
            return parsed
    except Exception:
        pass
    return default


def _run_ffprobe(path: str, analyzeduration: int, probesize: int) -> Optional[dict]:
    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-analyzeduration",
        str(analyzeduration),
        "-probesize",
        str(probesize),
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


def _desired_default_src_index(streams: List[dict], preferred_default_languages: List[str]) -> Optional[int]:
    eligible = set(preferred_default_languages)
    for stream in streams:
        if stream["lang"] in eligible:
            return stream["src_index"]
    return None


def _default_is_wrong(original_streams: List[dict], desired_default_src_index: Optional[int]) -> bool:
    current_defaults = [
        stream["src_index"]
        for stream in original_streams
        if (stream.get("disposition") or {}).get("default")
    ]
    if desired_default_src_index is None:
        return bool(current_defaults)
    return current_defaults != [desired_default_src_index]


def _looks_japanese_original(audio_streams: List[dict], kept_audio_streams: List[dict]) -> bool:
    default_pos = _current_default_position(audio_streams)
    if default_pos is not None and audio_streams[default_pos]["lang"] == "jpn":
        return True
    if kept_audio_streams and all(stream["lang"] == "jpn" for stream in kept_audio_streams):
        return True
    return False


def _plan_changes(probe: dict, settings: Settings) -> Optional[dict]:
    preferred_audio = _parse_lang_list(settings.get_setting("Preferred Audio Languages"))
    preferred_audio_default = _parse_lang_list(settings.get_setting("Preferred Audio Default Languages"))
    preferred_audio_default_jpn_original = _parse_lang_list(
        settings.get_setting("Preferred Audio Default Languages for Japanese-original")
    )
    preferred_subs = _parse_lang_list(settings.get_setting("Preferred Subtitle Languages"))
    preferred_subs_default = _parse_lang_list(settings.get_setting("Preferred Subtitle Default Languages"))
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

    japanese_original = _looks_japanese_original(audio, kept_audio_original)
    active_audio_default_languages = (
        preferred_audio_default_jpn_original if japanese_original else preferred_audio_default
    )

    kept_audio_sorted = _sort_kept(kept_audio_original, preferred_audio)
    kept_subs_sorted = _sort_kept(kept_subs_original, preferred_subs)
    kept_attachments = attachments if preserve_attachments else []

    desired_audio_default_src = _desired_default_src_index(
        kept_audio_sorted,
        active_audio_default_languages,
    )
    desired_subs_default_src = _desired_default_src_index(
        kept_subs_sorted,
        preferred_subs_default,
    )

    audio_removed = len(kept_audio_original) != len(audio)
    subs_removed = len(kept_subs_original) != len(subtitle)
    audio_reordered = [s["src_index"] for s in kept_audio_original] != [s["src_index"] for s in kept_audio_sorted]
    subs_reordered = [s["src_index"] for s in kept_subs_original] != [s["src_index"] for s in kept_subs_sorted]
    attachments_removed = bool(attachments) and not preserve_attachments
    audio_default_wrong = _default_is_wrong(kept_audio_original, desired_audio_default_src)
    subs_default_wrong = _default_is_wrong(kept_subs_original, desired_subs_default_src)

    needs_processing = any([
        audio_removed,
        subs_removed,
        audio_reordered,
        subs_reordered,
        audio_default_wrong,
        subs_default_wrong,
        attachments_removed,
    ])

    if not needs_processing:
        return None

    return {
        "video": video,
        "audio": kept_audio_sorted,
        "subtitle": kept_subs_sorted,
        "data": data_streams,
        "attachments": kept_attachments,
        "audio_default_src_index": desired_audio_default_src,
        "subtitle_default_src_index": desired_subs_default_src,
        "looks_japanese_original": japanese_original,
    }


def _build_ffmpeg_command(
    file_in: str,
    file_out: str,
    plan: dict,
    analyzeduration: int,
    probesize: int,
) -> List[str]:
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-analyzeduration",
        str(analyzeduration),
        "-probesize",
        str(probesize),
        "-i",
        file_in,
        "-map_metadata",
        "0",
        "-map_chapters",
        "0",
    ]

    for stream in plan["video"]:
        cmd += ["-map", f"0:{stream['src_index']}"]
    for stream in plan["audio"]:
        cmd += ["-map", f"0:{stream['src_index']}"]
    for stream in plan["subtitle"]:
        cmd += ["-map", f"0:{stream['src_index']}"]
    for stream in plan["data"]:
        cmd += ["-map", f"0:{stream['src_index']}"]
    for stream in plan["attachments"]:
        cmd += ["-map", f"0:{stream['src_index']}"]

    cmd += ["-c", "copy", "-max_muxing_queue_size", "10240"]

    desired_audio_default_src = plan.get("audio_default_src_index")
    desired_subtitle_default_src = plan.get("subtitle_default_src_index")

    for idx, stream in enumerate(plan["audio"]):
        cmd += [
            f"-disposition:a:{idx}",
            _stream_disposition_string(stream, want_default=(stream["src_index"] == desired_audio_default_src)),
        ]
    for idx, stream in enumerate(plan["subtitle"]):
        cmd += [
            f"-disposition:s:{idx}",
            _stream_disposition_string(stream, want_default=(stream["src_index"] == desired_subtitle_default_src)),
        ]

    cmd += ["-y", file_out]
    return cmd


def on_library_management_file_test(data):
    abspath = data.get("path")
    if not abspath:
        return data

    if data.get("library_id"):
        settings = Settings(library_id=data.get("library_id"))
    else:
        settings = Settings()

    ffprobe_analyzeduration = _parse_positive_int(settings.get_setting("ffprobe Analyze Duration"), 100000000)
    ffprobe_probesize = _parse_positive_int(settings.get_setting("ffprobe Probe Size"), 100000000)

    probe = _run_ffprobe(abspath, ffprobe_analyzeduration, ffprobe_probesize)
    if not probe:
        return data

    plan = _plan_changes(probe, settings)
    if plan is not None:
        data["add_file_to_pending_tasks"] = True
        logger.debug(
            "File '%s' requires preferred-language cleanup (japanese_original=%s).",
            abspath,
            plan.get("looks_japanese_original"),
        )
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

    ffprobe_analyzeduration = _parse_positive_int(settings.get_setting("ffprobe Analyze Duration"), 100000000)
    ffprobe_probesize = _parse_positive_int(settings.get_setting("ffprobe Probe Size"), 100000000)
    ffmpeg_analyzeduration = _parse_positive_int(settings.get_setting("ffmpeg Analyze Duration"), 100000000)
    ffmpeg_probesize = _parse_positive_int(settings.get_setting("ffmpeg Probe Size"), 100000000)

    probe = _run_ffprobe(file_in, ffprobe_analyzeduration, ffprobe_probesize)
    if not probe:
        return data

    plan = _plan_changes(probe, settings)
    if plan is None:
        return data

    data["exec_command"] = _build_ffmpeg_command(
        file_in,
        file_out,
        plan,
        ffmpeg_analyzeduration,
        ffmpeg_probesize,
    )
    logger.debug(
        "Prepared ffmpeg command for '%s' (japanese_original=%s).",
        file_in,
        plan.get("looks_japanese_original"),
    )
    return data
