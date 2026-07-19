#!/usr/bin/env python3
"""bo — Bang & Olufsen Mozart スピーカー用の薄いCLI。

使い方:
  bo discover                     # mDNSでスピーカーを探してデバイス一覧を保存
  bo devices                      # 保存済みデバイス一覧
  bo default <name>               # デフォルトデバイスを設定
  bo status                       # 再生状態・音量・ソース
  bo volume [0-100]               # 音量の取得/設定
  bo mute | unmute
  bo play | pause | stop | next | prev
  bo say "text" [--lang ja-jp] [--vol N]   # TTS読み上げ(再生中の音楽はダッキング)
  bo uri <url>                    # URLをストリーム再生
  bo preset <id>                  # プリセット再生
  bo join [peer]                  # Beolink join(peer省略時は最後のexperienceに参加)
  bo leave
  bo standby [--all]              # スタンバイ(--allでBeolink全機)
  bo reboot                       # 再起動(保留中のソフトウェア更新も適用される)
  bo stereotest [--vol N]         # 左右チャンネルテスト(「左チャンネル」「右チャンネル」を順に再生)

対象デバイスは -d <name|ip> で指定。省略時はデフォルトデバイス。
"""

import argparse
import array
import asyncio
import json
import socket
import subprocess
import sys
import tempfile
import threading
import wave
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from mozart_api.models import (
    BeolinkPeer,
    OverlayPlayRequest,
    OverlayPlayRequestTextToSpeechTextToSpeech,
    Uri,
    VolumeLevel,
    VolumeMute,
)
from mozart_api.mozart_client import MozartClient
from zeroconf import ServiceBrowser, ServiceListener, Zeroconf

CONFIG_PATH = Path.home() / ".config" / "bo-cli" / "devices.json"
MDNS_TYPE = "_bangolufsen._tcp.local."
DISCOVER_SECONDS = 5


def load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return {"default": None, "devices": {}}


def save_config(config: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2))


class _Listener(ServiceListener):
    def __init__(self) -> None:
        self.found: dict[str, dict] = {}

    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        info = zc.get_service_info(type_, name)
        if info is None or not info.addresses:
            return
        props = {
            k.decode(): v.decode() if isinstance(v, bytes) else v
            for k, v in info.properties.items()
            if k
        }
        friendly = props.get("fn") or name.split(".")[0]
        self.found[friendly] = {
            "ip": socket.inet_ntoa(info.addresses[0]),
            "model": props.get("pm", "?"),
            "serial": props.get("sn", "?"),
        }

    def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        pass

    def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        pass


def cmd_discover() -> None:
    print(f"{DISCOVER_SECONDS}秒間スキャン中...")
    zc = Zeroconf()
    listener = _Listener()
    ServiceBrowser(zc, MDNS_TYPE, listener)
    import time

    time.sleep(DISCOVER_SECONDS)
    zc.close()

    if not listener.found:
        print("デバイスが見つかりませんでした。同一ネットワークにいるか確認してください。")
        return

    config = load_config()
    config["devices"].update(listener.found)
    if config["default"] is None:
        config["default"] = next(iter(listener.found))
    save_config(config)

    for name, dev in listener.found.items():
        mark = " (default)" if config["default"] == name else ""
        print(f"  {name}: {dev['ip']}  [{dev['model']}]{mark}")
    print(f"\n{len(listener.found)}台を {CONFIG_PATH} に保存しました。")


def cmd_devices() -> None:
    config = load_config()
    if not config["devices"]:
        print("保存済みデバイスなし。`bo discover` を実行してください。")
        return
    for name, dev in config["devices"].items():
        mark = " (default)" if config["default"] == name else ""
        print(f"  {name}: {dev['ip']}  [{dev['model']}]{mark}")


def cmd_default(name: str) -> None:
    config = load_config()
    if name not in config["devices"]:
        sys.exit(f"'{name}' は未登録です。`bo devices` で確認してください。")
    config["default"] = name
    save_config(config)
    print(f"デフォルトを {name} に設定しました。")


def resolve_host(target: str | None) -> str:
    config = load_config()
    if target is None:
        if config["default"] is None:
            sys.exit("デバイス未指定。`bo discover` を実行するか -d で指定してください。")
        return config["devices"][config["default"]]["ip"]
    # IPアドレスならそのまま、名前なら設定から引く
    if target in config["devices"]:
        return config["devices"][target]["ip"]
    return target


async def with_client(host: str, func) -> None:
    client = MozartClient(host)
    try:
        await func(client)
    finally:
        await client.close_api_client()


def build_stereo_test_wav(dest_dir: str) -> str:
    """「左チャンネル」「右チャンネル」をL/Rに振り分けたステレオWAVを生成する。"""

    def synth(text: str, path: str) -> None:
        subprocess.run(
            ["say", "-v", "Kyoko", "--data-format=LEI16@22050", "-o", path, text],
            check=True,
        )

    def read_mono(path: str) -> tuple[int, bytes]:
        with wave.open(path) as w:
            rate = w.getframerate()
            samples = array.array("h", w.readframes(w.getnframes()))
        # sayの出力はピークが3割程度しかないので9割まで正規化する
        peak = max(1, max(abs(s) for s in samples))
        gain = int(32767 * 0.9) / peak
        if gain > 1:
            samples = array.array("h", (int(s * gain) for s in samples))
        return rate, samples.tobytes()

    left_path = f"{dest_dir}/left.wav"
    right_path = f"{dest_dir}/right.wav"
    synth("左チャンネル", left_path)
    synth("右チャンネル", right_path)
    rate, left = read_mono(left_path)
    _, right = read_mono(right_path)
    gap = b"\x00\x00" * int(rate * 0.6)

    frames = bytearray()
    for chunk in (left, gap):
        for i in range(0, len(chunk), 2):
            frames += chunk[i : i + 2] + b"\x00\x00"
    for i in range(0, len(right), 2):
        frames += b"\x00\x00" + right[i : i + 2]

    out = f"{dest_dir}/stereo_test.wav"
    with wave.open(out, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))
    return out


def local_ip_towards(device_ip: str) -> str:
    """デバイスへ向かうインターフェースのローカルIPを得る。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((device_ip, 80))
        return s.getsockname()[0]
    finally:
        s.close()


async def do_stereotest(client: MozartClient, device_ip: str, vol: int | None) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        wav = build_stereo_test_wav(tmp)
        fetched = threading.Event()

        class Handler(SimpleHTTPRequestHandler):
            def log_message(self, *args) -> None:
                fetched.set()

        server = ThreadingHTTPServer(
            ("0.0.0.0", 0), partial(Handler, directory=tmp)
        )
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://{local_ip_towards(device_ip)}:{port}/stereo_test.wav"
            # overlay/playはプライマリ機のみで鳴る(ステレオペアに配信されない)ため、
            # 通常再生を使う。現在のソースは中断される。
            if vol is not None:
                await client.set_current_volume_level(
                    volume_level=VolumeLevel(level=vol)
                )
            await client.post_uri_source(uri=Uri(location=url))
            if fetched.wait(timeout=10):
                print("再生開始(左→右の順に読み上げ)。左右逆ならペア設定を確認してください。")
                # 再生完了までサーバーを維持(音源は数秒で終わる)
                await asyncio.sleep(8)
            else:
                print("スピーカーがファイルを取得しませんでした(10秒待機)。")
        finally:
            server.shutdown()


async def do_status(client: MozartClient) -> None:
    volume = await client.get_current_volume()
    playback = await client.get_playback_state()
    state = playback.state.value if playback.state else None
    print(f"再生状態: {state or '?'}")
    if playback.source and playback.source.type:
        print(f"ソース: {playback.source.type.value}")
    meta = playback.metadata
    if meta and (meta.title or meta.artist_name):
        track = " / ".join(x for x in (meta.artist_name, meta.title) if x)
        print(f"曲: {track}")
    if volume.level:
        muted = " (ミュート中)" if volume.muted and volume.muted.muted else ""
        print(f"音量: {volume.level.level}{muted}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="bo", description="B&O Mozart スピーカーCLI")
    parser.add_argument("-d", "--device", help="対象デバイス(名前 or IP)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("discover")
    sub.add_parser("devices")
    p = sub.add_parser("default")
    p.add_argument("name")
    sub.add_parser("status")
    p = sub.add_parser("volume")
    p.add_argument("level", nargs="?", type=int)
    for name in ("mute", "unmute", "play", "pause", "stop", "next", "prev", "leave", "reboot"):
        sub.add_parser(name)
    p = sub.add_parser("stereotest")
    p.add_argument("--vol", type=int, default=30)
    p = sub.add_parser("say")
    p.add_argument("text")
    p.add_argument("--lang", default="ja-jp")
    p.add_argument("--vol", type=int)
    p = sub.add_parser("uri")
    p.add_argument("url")
    p = sub.add_parser("preset")
    p.add_argument("id", type=int)
    p = sub.add_parser("join")
    p.add_argument("peer", nargs="?")
    p = sub.add_parser("standby")
    p.add_argument("--all", action="store_true", dest="all_devices")

    args = parser.parse_args()

    if args.command == "discover":
        cmd_discover()
        return
    if args.command == "devices":
        cmd_devices()
        return
    if args.command == "default":
        cmd_default(args.name)
        return

    host = resolve_host(args.device)

    # スピーカー側のコマンド名に変換(CLIではnext/prevの方が打ちやすい)
    playback_commands = {
        "play": "play",
        "pause": "pause",
        "stop": "stop",
        "next": "skip",
        "prev": "prev",
    }

    async def run(client: MozartClient) -> None:
        if args.command == "status":
            await do_status(client)
        elif args.command == "volume":
            if args.level is None:
                volume = await client.get_current_volume()
                print(volume.level.level if volume.level else "?")
            else:
                await client.set_current_volume_level(
                    volume_level=VolumeLevel(level=args.level)
                )
        elif args.command == "mute":
            await client.set_volume_mute(volume_mute=VolumeMute(muted=True))
        elif args.command == "unmute":
            await client.set_volume_mute(volume_mute=VolumeMute(muted=False))
        elif args.command in playback_commands:
            await client.post_playback_command(command=playback_commands[args.command])
        elif args.command == "say":
            # volumeAbsolute: null を送るとMozartが400を返すため、未指定時はフィールド自体を省く
            kwargs = {} if args.vol is None else {"volume_absolute": args.vol}
            await client.post_overlay_play(
                overlay_play_request=OverlayPlayRequest(
                    text_to_speech=OverlayPlayRequestTextToSpeechTextToSpeech(
                        lang=args.lang, text=args.text
                    ),
                    **kwargs,
                )
            )
        elif args.command == "uri":
            await client.post_uri_source(uri=Uri(location=args.url))
        elif args.command == "preset":
            await client.activate_preset(id=args.id)
        elif args.command == "join":
            if args.peer:
                config = load_config()
                peers = await client.get_beolink_peers()
                match = next(
                    (
                        p
                        for p in peers
                        if args.peer.lower() in (p.friendly_name or "").lower()
                    ),
                    None,
                )
                if match is None:
                    names = ", ".join(p.friendly_name or p.jid for p in peers)
                    sys.exit(f"peer '{args.peer}' が見つかりません。候補: {names or 'なし'}")
                await client.join_beolink_peer(jid=match.jid)
            else:
                await client.join_latest_beolink_experience()
        elif args.command == "leave":
            await client.post_beolink_leave()
        elif args.command == "reboot":
            await client.post_reboot()
            print("再起動コマンドを送信しました。復帰まで1〜2分かかります。")
        elif args.command == "stereotest":
            await do_stereotest(client, host, args.vol)
        elif args.command == "standby":
            if args.all_devices:
                await client.post_beolink_allstandby()
            else:
                await client.post_standby()

    asyncio.run(with_client(host, run))


if __name__ == "__main__":
    main()
