#!/usr/bin/env python3
"""B&O Mozart スピーカー管理GUIサーバー(ポート8342)。

http://localhost:8342/ でブラウザUIを提供する。
夜間設定(時間帯・音量上限・自動スタンバイ)はGUIから編集でき、
~/.config/bo-cli/gui.json に保存され、サーバー内のスケジューラが1分ごとに適用する。
"""

import asyncio
import datetime
import json
from pathlib import Path

from aiohttp import web

from bo import load_config, resolve_host
from mozart_api.models import (
    Action,
    Bass,
    Loudness,
    OverlayPlayRequest,
    OverlayPlayRequestTextToSpeechTextToSpeech,
    SceneProperties,
    Treble,
    Uri,
    VolumeLevel,
    VolumeMute,
)
from mozart_api.mozart_client import MozartClient

PORT = 8342
GUI_CONFIG_PATH = Path.home() / ".config" / "bo-cli" / "gui.json"
STATIC_DIR = Path(__file__).parent / "static"

DEFAULT_GUI_CONFIG = {
    "night": {
        "enabled": False,
        "start": "22:00",
        "end": "07:00",
        "maxVolume": 40,
        "standbyAt": "",  # 空なら自動スタンバイなし
    },
    # {"name": str, "type": "radio"|"source"|"uri", "value": str}
    "favorites": [],
    # TTS読み上げのデフォルト音量(0-100)。Noneなら現在の音量で読み上げる
    "ttsVolume": None,
}


def load_gui_config() -> dict:
    if GUI_CONFIG_PATH.exists():
        config = json.loads(GUI_CONFIG_PATH.read_text())
        # 欠けたキーはデフォルトで補完
        night = {**DEFAULT_GUI_CONFIG["night"], **config.get("night", {})}
        return {
            "night": night,
            "favorites": config.get("favorites", []),
            "ttsVolume": config.get("ttsVolume"),
        }
    return json.loads(json.dumps(DEFAULT_GUI_CONFIG))


def save_gui_config(config: dict) -> None:
    GUI_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    GUI_CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2))


def client_for(request: web.Request) -> MozartClient:
    device = request.query.get("device") or None
    return MozartClient(resolve_host(device))


async def api(handler):
    """Mozartクライアントを開閉しJSONで返す薄いラッパー。"""

    async def wrapped(request: web.Request) -> web.Response:
        client = client_for(request)
        try:
            result = await handler(request, client)
            return web.json_response(result if result is not None else {"ok": True})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=502)
        finally:
            await client.close_api_client()

    return wrapped


# ---- 状態取得 ----


def pick_art_url(meta, host: str) -> str | None:
    """メタデータから最大サイズのアートワークURLを選ぶ。"""
    if meta is None or not meta.art:
        return None
    def size(art) -> int:
        try:
            return int((art.key or "0x0").split("x")[0])
        except ValueError:
            return 0
    best = max(meta.art, key=size)
    url = best.url or ""
    if not url:
        return None
    if url.startswith("/"):  # デバイス内画像は相対パスで来る
        url = f"http://{host}{url}"
    return url


async def h_state(request: web.Request, client: MozartClient) -> dict:
    volume = await client.get_current_volume()
    playback = await client.get_playback_state()
    meta = playback.metadata
    host = resolve_host(request.query.get("device") or None)
    return {
        "art": pick_art_url(meta, host),
        "state": playback.state.value if playback.state else None,
        "source": playback.source.type.value
        if playback.source and playback.source.type
        else None,
        "artist": meta.artist_name if meta else None,
        "title": meta.title if meta else None,
        "organization": meta.organization if meta else None,
        "volume": volume.level.level if volume.level else None,
        "muted": bool(volume.muted and volume.muted.muted),
    }


async def h_overview(request: web.Request, client: MozartClient) -> dict:
    """起動時にまとめて取る重めの情報。"""
    presets = await client.get_presets()
    modes = await client.get_listening_mode_set()
    active_mode = await client.get_active_listening_mode()
    product = await client.get_product_state()
    sources = await client.get_available_sources(target_remote=False)
    adjustments = (
        product.sound_settings.adjustments.to_dict()
        if product.sound_settings and product.sound_settings.adjustments
        else {}
    )
    software = (
        product.software_update_state.to_dict()
        if product.software_update_state
        else {}
    )
    return {
        "presets": {
            pid: {
                "name": (p.title or p.name or pid),
            }
            for pid, p in (presets or {}).items()
        },
        "listeningModes": [
            {"id": m.id, "name": m.name} for m in (modes or [])
        ],
        "activeListeningMode": active_mode.id if active_mode else None,
        "adjustments": adjustments,
        "softwareUpdate": software,
        "sources": [
            {"id": s.id, "name": s.name, "enabled": bool(s.is_enabled)}
            for s in (sources.items or [])
        ]
        if sources
        else [],
    }


# ---- 操作 ----


async def h_volume(request: web.Request, client: MozartClient) -> None:
    body = await request.json()
    await client.set_current_volume_level(
        volume_level=VolumeLevel(level=int(body["level"]))
    )


async def h_mute(request: web.Request, client: MozartClient) -> None:
    body = await request.json()
    await client.set_volume_mute(volume_mute=VolumeMute(muted=bool(body["muted"])))


async def h_playback(request: web.Request, client: MozartClient) -> None:
    body = await request.json()
    command = body["command"]
    if command not in ("play", "pause", "stop", "skip", "prev"):
        raise ValueError(f"unknown command: {command}")
    await client.post_playback_command(command=command)


async def h_say(request: web.Request, client: MozartClient) -> None:
    body = await request.json()
    # 音量の優先順位: リクエスト指定 > 設定のttsVolume > 未指定(現在の音量)
    volume = body.get("volume")
    if volume is None:
        volume = load_gui_config()["ttsVolume"]
    # volumeAbsolute: null を送るとMozartが400を返すため、未指定時はフィールド自体を省く
    kwargs = {}
    if volume is not None:
        kwargs["volume_absolute"] = int(volume)
    await client.post_overlay_play(
        overlay_play_request=OverlayPlayRequest(
            text_to_speech=OverlayPlayRequestTextToSpeechTextToSpeech(
                lang=body.get("lang", "ja-jp"), text=body["text"]
            ),
            **kwargs,
        )
    )


async def h_uri(request: web.Request, client: MozartClient) -> None:
    body = await request.json()
    await client.post_uri_source(uri=Uri(location=body["url"]))


async def h_preset(request: web.Request, client: MozartClient) -> None:
    body = await request.json()
    await client.activate_preset(id=int(body["id"]))


async def h_source(request: web.Request, client: MozartClient) -> None:
    body = await request.json()
    await client.set_active_source(source_id=body["id"])


async def h_listening_mode(request: web.Request, client: MozartClient) -> None:
    body = await request.json()
    await client.activate_listening_mode(id=int(body["id"]))


async def h_adjustments(request: web.Request, client: MozartClient) -> None:
    body = await request.json()
    if "bass" in body:
        await client.set_sound_settings_adjustments_bass(
            bass=Bass(value=int(body["bass"]))
        )
    if "treble" in body:
        await client.set_sound_settings_adjustments_treble(
            treble=Treble(value=int(body["treble"]))
        )
    if "loudness" in body:
        await client.set_sound_settings_adjustments_loudness(
            loudness=Loudness(value=bool(body["loudness"]))
        )


async def h_content(request: web.Request, client: MozartClient) -> dict:
    """デバイスが知っているコンテンツ一覧(ネットラジオ局など)。"""
    items = await client.get_content(start_with=request.query.get("startWith"))
    result = []
    for item in (items or {}).values():
        uri = item.content_uri or ""
        if "://" not in uri:
            continue  # "netRadio" のようなソース自体のエントリは除外
        result.append({"label": item.label or uri, "contentUri": uri})
    return {"items": result}


async def h_beolink(request: web.Request, client: MozartClient) -> dict:
    self_info = await client.get_beolink_self()
    peers = await client.get_beolink_peers()
    listeners = await client.get_beolink_listeners()
    return {
        "self": {"name": self_info.friendly_name, "jid": self_info.jid},
        "peers": [
            {"name": p.friendly_name, "jid": p.jid, "ip": p.ip_address}
            for p in (peers or [])
        ],
        "listeners": [{"jid": l.jid} for l in (listeners or [])],
    }


async def h_beolink_join(request: web.Request, client: MozartClient) -> None:
    body = await request.json()
    if body.get("jid"):
        await client.join_beolink_peer(jid=body["jid"])
    else:
        await client.join_latest_beolink_experience()


async def h_beolink_leave(request: web.Request, client: MozartClient) -> None:
    await client.post_beolink_leave()


async def h_standby(request: web.Request, client: MozartClient) -> None:
    body = await request.json() if request.can_read_body else {}
    if body.get("all"):
        await client.post_beolink_allstandby()
    else:
        await client.post_standby()


async def h_reboot(request: web.Request, client: MozartClient) -> None:
    await client.post_reboot()


async def h_stereotest(request: web.Request, client: MozartClient) -> None:
    from bo import do_stereotest

    device = request.query.get("device") or None
    await do_stereotest(client, resolve_host(device), None)


# ---- お気に入り ----


async def play_favorite(client: MozartClient, fav: dict) -> None:
    if fav["type"] == "radio":
        await client.run_provided_scene(
            scene_properties=SceneProperties(
                action_list=[Action(type="radio", radio_station_id=fav["value"])]
            )
        )
    elif fav["type"] == "source":
        await client.set_active_source(source_id=fav["value"])
    elif fav["type"] == "uri":
        await client.post_uri_source(uri=Uri(location=fav["value"]))
    else:
        raise ValueError(f"unknown favorite type: {fav['type']}")


async def h_favorite_play(request: web.Request, client: MozartClient) -> None:
    body = await request.json()
    favorites = load_gui_config()["favorites"]
    index = int(body["index"])
    if not 0 <= index < len(favorites):
        raise ValueError(f"favorite index out of range: {index}")
    await play_favorite(client, favorites[index])


async def h_favorite_save_current(request: web.Request, client: MozartClient) -> dict:
    """再生中のコンテンツをお気に入りに保存する。"""
    active = await client.get_active_content()
    if active is None or active.content is None:
        raise ValueError("再生中のコンテンツがありません")
    content = active.content
    uri = content.content_uri or ""
    label = content.label or uri
    if uri.startswith("netRadio://"):
        fav = {"name": label, "type": "radio", "value": uri.split("://", 1)[1]}
    elif uri.startswith(("http://", "https://")):
        fav = {"name": label, "type": "uri", "value": uri}
    else:
        # 入力ソース(spotify等)はソース切替として保存
        source = content.source.value if content.source else uri
        fav = {"name": label, "type": "source", "value": source}
    config = load_gui_config()
    if fav in config["favorites"]:
        raise ValueError(f"「{fav['name']}」は既に保存されています")
    config["favorites"].append(fav)
    save_gui_config(config)
    return {"saved": fav}


async def h_favorites_get(request: web.Request) -> web.Response:
    return web.json_response(load_gui_config()["favorites"])


async def h_favorites_put(request: web.Request) -> web.Response:
    favorites = await request.json()
    if not isinstance(favorites, list):
        return web.json_response({"error": "list expected"}, status=400)
    for fav in favorites:
        if fav.get("type") not in ("radio", "source", "uri") or not fav.get("value"):
            return web.json_response({"error": f"invalid entry: {fav}"}, status=400)
        fav.setdefault("name", fav["value"])
    config = load_gui_config()
    config["favorites"] = favorites
    save_gui_config(config)
    return web.json_response(favorites)


# ---- デバイス・夜間設定 ----


async def h_devices(request: web.Request) -> web.Response:
    config = load_config()
    return web.json_response(
        {
            "devices": {
                name: dev["ip"] for name, dev in config["devices"].items()
            },
            "default": config["default"],
        }
    )


async def h_tts_volume_get(request: web.Request) -> web.Response:
    return web.json_response({"volume": load_gui_config()["ttsVolume"]})


async def h_tts_volume_put(request: web.Request) -> web.Response:
    body = await request.json()
    volume = body.get("volume")
    if volume is not None:
        volume = max(0, min(100, int(volume)))
    config = load_gui_config()
    config["ttsVolume"] = volume
    save_gui_config(config)
    return web.json_response({"volume": volume})


async def h_night_get(request: web.Request) -> web.Response:
    return web.json_response(load_gui_config()["night"])


async def h_night_put(request: web.Request) -> web.Response:
    body = await request.json()
    config = load_gui_config()
    night = config["night"]
    for key in ("enabled", "start", "end", "maxVolume", "standbyAt"):
        if key in body:
            night[key] = body[key]
    # 形式チェック
    for key in ("start", "end"):
        datetime.time.fromisoformat(night[key])
    if night["standbyAt"]:
        datetime.time.fromisoformat(night["standbyAt"])
    night["maxVolume"] = max(0, min(100, int(night["maxVolume"])))
    save_gui_config(config)
    return web.json_response(night)


def in_window(now: datetime.time, start: datetime.time, end: datetime.time) -> bool:
    if start <= end:
        return start <= now < end
    return now >= start or now < end  # 日跨ぎ(例 22:00-07:00)


async def night_scheduler(app: web.Application) -> None:
    """1分ごとに夜間設定を適用する。"""
    last_standby_date: datetime.date | None = None
    while True:
        try:
            night = load_gui_config()["night"]
            if night["enabled"]:
                now_dt = datetime.datetime.now()
                now = now_dt.time().replace(second=0, microsecond=0)
                start = datetime.time.fromisoformat(night["start"])
                end = datetime.time.fromisoformat(night["end"])
                host = resolve_host(None)
                if in_window(now, start, end):
                    client = MozartClient(host)
                    try:
                        volume = await client.get_current_volume()
                        level = volume.level.level if volume.level else 0
                        if level > night["maxVolume"]:
                            await client.set_current_volume_level(
                                volume_level=VolumeLevel(level=night["maxVolume"])
                            )
                            print(
                                f"[night] 音量 {level} -> {night['maxVolume']} に制限"
                            )
                    finally:
                        await client.close_api_client()
                if night["standbyAt"]:
                    standby = datetime.time.fromisoformat(night["standbyAt"])
                    if (
                        now.hour == standby.hour
                        and now.minute == standby.minute
                        and last_standby_date != now_dt.date()
                    ):
                        last_standby_date = now_dt.date()
                        client = MozartClient(host)
                        try:
                            await client.post_standby()
                            print("[night] 自動スタンバイ実行")
                        finally:
                            await client.close_api_client()
        except Exception as e:
            print(f"[night] scheduler error: {e}")
        await asyncio.sleep(60)


async def start_background(app: web.Application):
    task = asyncio.create_task(night_scheduler(app))
    yield
    task.cancel()


async def h_index(request: web.Request) -> web.FileResponse:
    return web.FileResponse(STATIC_DIR / "index.html")


async def make_app() -> web.Application:
    app = web.Application()
    r = app.router
    r.add_get("/", h_index)
    r.add_get("/api/devices", h_devices)
    r.add_get("/api/night", h_night_get)
    r.add_put("/api/night", h_night_put)
    r.add_get("/api/tts-volume", h_tts_volume_get)
    r.add_put("/api/tts-volume", h_tts_volume_put)
    r.add_get("/api/favorites", h_favorites_get)
    r.add_put("/api/favorites", h_favorites_put)
    r.add_get("/api/state", await api(h_state))
    r.add_get("/api/overview", await api(h_overview))
    r.add_get("/api/content", await api(h_content))
    r.add_get("/api/beolink", await api(h_beolink))
    for path, handler in [
        ("/api/volume", h_volume),
        ("/api/mute", h_mute),
        ("/api/playback", h_playback),
        ("/api/say", h_say),
        ("/api/uri", h_uri),
        ("/api/preset", h_preset),
        ("/api/source", h_source),
        ("/api/listening-mode", h_listening_mode),
        ("/api/adjustments", h_adjustments),
        ("/api/favorites/play", h_favorite_play),
        ("/api/favorites/save-current", h_favorite_save_current),
        ("/api/beolink/join", h_beolink_join),
        ("/api/beolink/leave", h_beolink_leave),
        ("/api/standby", h_standby),
        ("/api/reboot", h_reboot),
        ("/api/stereotest", h_stereotest),
    ]:
        r.add_post(path, await api(handler))
    app.cleanup_ctx.append(start_background)
    return app


def main() -> None:
    print(f"GUIサーバー起動: http://localhost:{PORT}")
    web.run_app(make_app(), port=PORT, print=None)


if __name__ == "__main__":
    main()
