#!/usr/bin/env python3
"""B&O スピーカー TTS通知サーバー。

POST /notify に JSON を投げると、スピーカーがテキストを読み上げる。
再生中の音楽は自動でダッキングされ、読み上げ後に戻る。

  curl -X POST localhost:8340/notify -H 'Content-Type: application/json' \
       -d '{"text": "宅配便が来ました"}'

JSONフィールド:
  text    (必須) 読み上げるテキスト
  device  対象デバイス名 or IP(省略時はデフォルトデバイス)
  all     true で登録済み全デバイスに送信
  lang    言語コード(デフォルト ja-jp)
  volume  読み上げ音量 0-100(省略時は現在の音量)

注意: TTS生成はデバイスあたり1日100メッセージまで(同一文言は24時間キャッシュ)。
"""

import ipaddress
import json

from aiohttp import web

from bo import CONFIG_PATH, load_config, resolve_host
from mozart_api.models import (
    OverlayPlayRequest,
    OverlayPlayRequestTextToSpeechTextToSpeech,
)
from mozart_api.mozart_client import MozartClient

PORT = 8340


async def say(host: str, text: str, lang: str, volume: int | None) -> None:
    client = MozartClient(host)
    # volumeAbsolute: null を送るとMozartが400を返すため、未指定時はフィールド自体を省く
    kwargs = {} if volume is None else {"volume_absolute": int(volume)}
    try:
        await client.post_overlay_play(
            overlay_play_request=OverlayPlayRequest(
                text_to_speech=OverlayPlayRequestTextToSpeechTextToSpeech(
                    lang=lang, text=text
                ),
                **kwargs,
            )
        )
    finally:
        await client.close_api_client()


async def handle_notify(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except ValueError:
        return web.json_response({"error": "invalid JSON"}, status=400)

    text = body.get("text")
    if not text or not isinstance(text, str):
        return web.json_response({"error": "'text' is required"}, status=400)

    lang = body.get("lang", "ja-jp")
    volume = body.get("volume")
    if volume is None:
        # GUI設定のTTSデフォルト音量を共有する
        gui_config_path = CONFIG_PATH.parent / "gui.json"
        if gui_config_path.exists():
            volume = json.loads(gui_config_path.read_text()).get("ttsVolume")

    if body.get("all"):
        hosts = {
            name: dev["ip"] for name, dev in load_config()["devices"].items()
        }
    else:
        device = body.get("device")
        config = load_config()
        if device is not None and device not in config["devices"]:
            try:
                ipaddress.ip_address(device)
            except ValueError:
                return web.json_response(
                    {
                        "error": f"unknown device: {device}",
                        "devices": list(config["devices"].keys()),
                    },
                    status=404,
                )
        try:
            hosts = {device or "default": resolve_host(device)}
        except SystemExit as e:  # resolve_host はデフォルト未設定時に sys.exit する
            return web.json_response({"error": str(e)}, status=404)

    results = {}
    for name, host in hosts.items():
        try:
            await say(host, text, lang, volume)
            results[name] = "ok"
        except Exception as e:
            results[name] = f"error: {e}"

    ok = all(v == "ok" for v in results.values())
    return web.json_response(
        {"sent": results}, status=200 if ok else 502
    )


async def handle_index(request: web.Request) -> web.Response:
    config = load_config()
    return web.json_response(
        {
            "usage": "POST /notify {'text': '...', 'device'?, 'all'?, 'lang'?, 'volume'?}",
            "devices": list(config["devices"].keys()),
            "default": config["default"],
        }
    )


def main() -> None:
    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_post("/notify", handle_notify)
    print(f"TTS通知サーバー起動: http://localhost:{PORT}")
    web.run_app(app, port=PORT, print=None)


if __name__ == "__main__":
    main()
