import os
import time
import logging
import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
CHANNEL_ID = os.getenv("YOUTUBE_CHANNEL_ID")
def set_channel_id(new_id: str):
    global CHANNEL_ID
    CHANNEL_ID = new_id
    CACHE["data"] = None  # Invalidate cache


CACHE = {"data": None, "timestamp": 0}
CACHE_TTL = 90  # seconds

SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
PLAYLIST_ITEMS_URL = "https://www.googleapis.com/youtube/v3/playlistItems"


async def _fetch_json(client: httpx.AsyncClient, url: str, params: dict):
    res = await client.get(url, params=params)
    try:
        res.raise_for_status()
    except httpx.HTTPStatusError as e:
        logger.error("YouTube API error %s: %s", e.response.status_code, e.response.text)
        raise
    return res.json()


def _classify_live_status(live_details: dict) -> str | None:
    """
    Return "LIVE" / "UPCOMING" / None based on liveStreamingDetails.[web:25][web:27][web:32]
    """
    if not live_details:
        return None

    has_actual_start = "actualStartTime" in live_details
    has_actual_end = "actualEndTime" in live_details
    has_scheduled_start = "scheduledStartTime" in live_details

    if has_actual_start and not has_actual_end:
        return "LIVE"
    if has_scheduled_start and not has_actual_start:
        return "UPCOMING"
    return None


def _extract_thumbnail(snippet: dict) -> str | None:
    thumbs = snippet.get("thumbnails") or {}
    for key in ("maxres", "standard", "high", "medium", "default"):
        url = thumbs.get(key, {}).get("url")
        if url:
            return url
    return None


async def _fetch_candidate_video_ids(client: httpx.AsyncClient) -> list[str]:
    """
    Use search.list to fetch LIVE or UPCOMING videos from the channel using eventType,
    ordered by date, then collect their videoIds.[web:2][web:5]
    """
    if not CHANNEL_ID:
        return []

    video_ids: list[str] = []

    for event_type in ["live", "upcoming"]:
        params = {
            "part": "snippet",
            "channelId": CHANNEL_ID,
            "type": "video",
            "eventType": event_type,
            "order": "date",
            "maxResults": 50,
            "key": YOUTUBE_API_KEY,
        }
        try:
            data = await _fetch_json(client, SEARCH_URL, params)
            items = data.get("items", [])
            for item in items:
                id_obj = item.get("id", {})
                vid = id_obj.get("videoId")
                if vid:
                    video_ids.append(vid)
            if video_ids:
                logger.info("Found %d %s stream(s) from search", len(video_ids), event_type)
        except Exception as e:
            logger.debug("Search with eventType=%s failed: %s", event_type, e)
            continue

    return video_ids


async def _fallback_video_ids_from_uploads(client: httpx.AsyncClient) -> list[str]:
    """
    Fallback: use channel uploads playlist to get recent video IDs.[web:23][web:32]
    """
    if not CHANNEL_ID:
        return []

    channels_params = {
        "part": "contentDetails",
        "id": CHANNEL_ID,
        "key": YOUTUBE_API_KEY,
    }
    channels_data = await _fetch_json(client, CHANNELS_URL, channels_params)
    channel_items = channels_data.get("items", [])
    if not channel_items:
        logger.warning("No channel data for fallback uploads playlist")
        return []

    uploads_playlist_id = (
        channel_items[0]
        .get("contentDetails", {})
        .get("relatedPlaylists", {})
        .get("uploads")
    )
    if not uploads_playlist_id:
        logger.warning("Channel has no uploads playlist")
        return []

    playlist_params = {
        "part": "contentDetails",
        "playlistId": uploads_playlist_id,
        "maxResults": 50,
        "key": YOUTUBE_API_KEY,
    }
    playlist_data = await _fetch_json(client, PLAYLIST_ITEMS_URL, playlist_params)
    playlist_items = playlist_data.get("items", [])

    video_ids: list[str] = []
    for item in playlist_items:
        vid = item.get("contentDetails", {}).get("videoId")
        if vid:
            video_ids.append(vid)

    logger.info("Candidate video IDs from uploads playlist: %d", len(video_ids))
    return video_ids


async def _fetch_live_streams_for_ids(client: httpx.AsyncClient, video_ids: list[str]):
    """
    For a list of video IDs, call videos.list with part=snippet,liveStreamingDetails
    and build a list of live/upcoming streams.[web:25][web:27][web:30][web:32]
    """
    if not video_ids:
        return []

    params = {
        "part": "snippet,liveStreamingDetails",
        "id": ",".join(video_ids),
        "key": YOUTUBE_API_KEY,
    }
    data = await _fetch_json(client, VIDEOS_URL, params)
    items = data.get("items", [])

    streams: list[dict] = []
    for item in items:
        live = item.get("liveStreamingDetails") or {}
        status = _classify_live_status(live)
        if not status:
            continue

        snippet = item.get("snippet", {})
        thumbnail_url = _extract_thumbnail(snippet)

        streams.append(
            {
                "video_id": item.get("id"),
                "title": snippet.get("title", ""),
                "thumbnail": thumbnail_url,
                "status": status,
            }
        )

    return streams


async def fetch_channel_streams() -> list[dict]:
    """
    Return list of {video_id, title, thumbnail, status} where status ∈ {"LIVE","UPCOMING"}.
    Uses in‑memory cache with TTL.[web:25][web:27][web:30][web:32]
    """
    now = time.time()
    if CACHE["data"] is not None and now - CACHE["timestamp"] < CACHE_TTL:
        return CACHE["data"]

    if not YOUTUBE_API_KEY or not CHANNEL_ID:
        logger.error("YouTube API Key or Channel ID not configured")
        CACHE["data"] = []
        CACHE["timestamp"] = now
        return []

    async with httpx.AsyncClient(timeout=10) as client:
        streams = []
        
        # Try uploads playlist first (most reliable)
        logger.info("Fetching from uploads playlist...")
        try:
            candidate_ids = await _fallback_video_ids_from_uploads(client)
            streams = await _fetch_live_streams_for_ids(client, candidate_ids)
        except Exception as e:
            logger.error("Uploads playlist method failed: %s", e)
            streams = []

        # Fallback: search API if playlist found nothing
        if not streams:
            logger.info("Trying search API for live/upcoming streams...")
            try:
                candidate_ids = await _fetch_candidate_video_ids(client)
                streams = await _fetch_live_streams_for_ids(client, candidate_ids)
            except Exception as e:
                logger.error("Search API live detection failed: %s", e)
                streams = []

    CACHE["data"] = streams
    CACHE["timestamp"] = now

    if not streams:
        logger.warning("No live or upcoming streams found for the channel")
    else:
        logger.info("Found %d live/upcoming stream(s)", len(streams))

    return streams
