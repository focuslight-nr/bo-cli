# bo-cli

[English README](README.md)

Bang & Olufsen の [Mozartプラットフォーム](https://github.com/bang-olufsen/mozart-open-api)搭載スピーカー
(Beosound Balance / Emerge / Level / A5 / A9、Beolab 8 / 28、Beosound Theatre など)を
macOSから制御するツール集。公式Pythonパッケージ [mozart-api](https://pypi.org/project/mozart-api) を利用しています。

| ツール | 内容 |
|---|---|
| **`bo` CLI** | スピーカー探索、再生/音量制御、TTS読み上げ、Beolinkグループ、再起動、ステレオチャンネルテスト |
| **Web GUI**(ポート8342) | ブラウザから全操作: お気に入り(ネットラジオ局のワンタップ切替)、アートワーク表示、音質調整、夜間スケジューラ、英日UI |
| **通知サーバー**(ポート8340) | `curl` するとスピーカーが喋る。リマインダー、CI完了通知、インターホン連携などに |

## 動作要件

- macOS(常駐化にLaunchAgents、ステレオテストに`say`コマンドを使用)
- Python 3.11以上(3.14で動作確認)
- 同一LAN上のMozart対応B&Oスピーカー

## インストール

```sh
git clone https://github.com/focuslight-nr/bo-cli.git
cd bo-cli
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

./bo discover        # mDNSでスピーカーを探して保存
alias bo="$PWD/bo"   # ~/.zshrc に追加推奨
```

`bo discover` はデバイスを `~/.config/bo-cli/devices.json` に保存し、最初に見つかった
1台がデフォルトになります。`-d <name|ip>` で対象を指定できます。

## CLIの使い方

```sh
bo status                # 再生状態・ソース・曲・音量
bo volume [0-100]        # 音量の取得/設定
bo mute / unmute
bo play / pause / stop / next / prev
bo say "ご飯できたよ" [--lang ja-jp] [--vol 40]   # TTS読み上げ(音楽は自動ダッキング)
bo uri <url>             # mp3/aac/flac/wav等のURLをストリーム再生
bo preset <id>           # 本体プリセット再生
bo join [peer名]         # Beolinkグループ参加(省略時は最後のexperience)
bo leave
bo standby [--all]       # スタンバイ(--allで全Beolink機器)
bo reboot                # 再起動(保留中のファームウェア更新も適用)
bo stereotest [--vol 30] # 左右から「左チャンネル」「右チャンネル」と読み上げ
bo devices / bo default <name>
```

## Web GUI

```sh
.venv/bin/python gui_server.py    # → http://localhost:8342/
```

- 再生・音量・ミュート — スピーカーの通知WebSocketをブラウザへ中継し**リアルタイム反映**
  (切断時はポーリングにフォールバック)
- シークバー(シーク可能なソースのみ)、リピート/シャッフル切替
- 起動時音量・最大音量の設定(スピーカー本体に保存)
- **お気に入り**: ネットラジオ局(「再生中を保存」またはデバイスの既知コンテンツから選択)、
  入力ソース、ストリームURLを保存してワンタップ切替。局は `scene/run` のradioアクションで
  直接再生するため、本体プリセット4枠に縛られません
- **ローカルファイル**: Mac上の音楽フォルダ(デフォルト `~/Music`、変更可)をブラウズして
  mp3/m4a/flac/wav等をスピーカーへストリーム再生。Range対応配信なのでシークも効く。
  再生中はMacを起こしておく必要あり
- TTS読み上げ(TTS専用音量を保存可能。読み上げ後は元の音量に自動復帰)
- サウンド: リスニングモード、低音/高音/ラウドネス
- **夜間設定**: 時間帯+音量上限(1分ごとに強制)+自動スタンバイ時刻をGUIで編集。
  `~/.config/bo-cli/gui.json` に保存
- 電源: スタンバイ/全機スタンバイ/ステレオテスト/再起動
- UIは英語(デフォルト)/日本語切替。選択は次回起動時も維持

## 通知サーバー

```sh
.venv/bin/python notify_server.py    # → http://localhost:8340/
```

```sh
curl -X POST localhost:8340/notify -H 'Content-Type: application/json' \
     -d '{"text": "宅配便が来ました"}'

# 全デバイスに音量40で
curl -X POST localhost:8340/notify -H 'Content-Type: application/json' \
     -d '{"all": true, "text": "夕食の時間です", "volume": 40}'
```

フィールド: `text`(必須) / `device` / `all` / `lang`(既定 `ja-jp`) / `volume`
(未指定時はGUIの読み上げ音量設定 → それもなければ現在の音量)

## 常駐化(ログイン時自動起動)

```sh
./install_agents.sh      # GUI・通知サーバー両方のLaunchAgentを登録
```

ログイン時に自動起動し、落ちても再起動されます。ログは
`~/Library/Logs/com.bo-cli.*.log`。夜間スケジューラはGUIサーバーが動いている間だけ
働くので、夜間設定を使うなら常駐化を推奨します。

```sh
./uninstall_agents.sh    # 両方解除
```

## 既知の制約

- **ステレオペア**は1つの製品として見えます。TTS/オーバーレイ音声はプライマリ機のみから
  再生されます(通常再生は両方から鳴ります)
- TTS生成はデバイスあたり1日100メッセージまで(同一文言は24時間キャッシュ)
- QobuzはMozartにネイティブソースがありません(ファームウェア6.2.x時点)。
  QobuzアプリからChromecast / AirPlay 2 / DLNA経由で再生してください

## ライセンス

[MIT](LICENSE)
