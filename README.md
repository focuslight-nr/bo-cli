# bo-cli

[日本語版 README](README.ja.md)

A toolkit for controlling Bang & Olufsen speakers on the [Mozart platform](https://github.com/bang-olufsen/mozart-open-api)
(Beosound Balance / Emerge / Level / A5 / A9, Beolab 8 / 28, Beosound Theatre, and more)
from macOS, built on the official [mozart-api](https://pypi.org/project/mozart-api) Python package.

Three tools in one repo:

| Tool | What it does |
|---|---|
| **`bo` CLI** | Discover speakers, playback/volume control, TTS announcements, Beolink grouping, reboot, stereo channel test |
| **Web GUI** (port 8342) | Full browser control: favorites with one-tap net-radio station switching, artwork, sound adjustments, night-mode scheduler, EN/JA UI |
| **Notify server** (port 8340) | `curl` → your speaker speaks. Perfect for reminders, CI results, doorbells |

## Requirements

- macOS (LaunchAgents for autostart; the `say` command for the stereo test)
- Python 3.11+ (3.14 tested)
- A Mozart-platform B&O speaker on the same LAN

## Install

```sh
git clone https://github.com/focuslight-nr/bo-cli.git
cd bo-cli
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

./bo discover        # find speakers via mDNS and save them
alias bo="$PWD/bo"   # add to your ~/.zshrc
```

`bo discover` stores devices in `~/.config/bo-cli/devices.json`; the first one found
becomes the default target. Use `-d <name|ip>` to target another device.

## CLI usage

```sh
bo status                # playback state, source, track, volume
bo volume [0-100]        # get / set volume
bo mute / unmute
bo play / pause / stop / next / prev
bo say "Dinner is ready" [--lang en-us] [--vol 40]   # TTS overlay (music ducks & resumes)
bo uri <url>             # stream any mp3/aac/flac/wav URL
bo preset <id>           # trigger a device preset
bo join [peer]           # join a Beolink group (latest experience if omitted)
bo leave
bo standby [--all]       # standby (--all = every Beolink device)
bo reboot                # reboot (also applies pending firmware updates)
bo stereotest [--vol 30] # "left channel" / "right channel" spoken on each side
bo devices / bo default <name>
```

## Web GUI

```sh
.venv/bin/python gui_server.py    # → http://localhost:8342/
```

- Playback / volume / mute with live status and artwork — pushed in real time over
  WebSocket (speaker notifications are relayed to the browser; falls back to polling)
- Seek bar (for seekable sources), repeat / shuffle toggles
- Power-on default volume and hardware volume limit (stored on the speaker itself)
- **Favorites**: save net-radio stations ("save now playing" or pick from the device's
  known content), input sources, and stream URLs — switch with one tap.
  Stations play directly via the `scene/run` radio action, so you are not limited
  to the 4 hardware presets
- **Local files**: browse a music folder on the Mac (default `~/Music`, configurable)
  and stream mp3/m4a/flac/wav/… to the speaker. Served with Range support, so
  seeking works; playback requires the Mac to stay awake
- TTS with a persistent TTS-specific volume (playback volume is restored afterwards)
- Sound: listening modes, bass / treble / loudness
- **Night mode**: time window + volume cap (enforced every minute) + optional
  auto-standby time — all editable in the GUI, stored in `~/.config/bo-cli/gui.json`
- Power: standby / all-standby / stereo test / reboot
- UI in English (default) or Japanese — toggle top-right, choice persists

## Notify server

```sh
.venv/bin/python notify_server.py    # → http://localhost:8340/
```

```sh
curl -X POST localhost:8340/notify -H 'Content-Type: application/json' \
     -d '{"text": "Build finished"}'

# all devices, explicit volume, English voice
curl -X POST localhost:8340/notify -H 'Content-Type: application/json' \
     -d '{"all": true, "text": "Dinner!", "volume": 40, "lang": "en-us"}'
```

Fields: `text` (required), `device`, `all`, `lang` (default `ja-jp`), `volume`
(falls back to the GUI's TTS volume setting, then to the current volume).

## Run at login (autostart)

```sh
./install_agents.sh      # installs LaunchAgents for GUI + notify servers
```

Both servers then start at login, restart on crash, and log to
`~/Library/Logs/com.bo-cli.*.log`. The night-mode scheduler only runs while the
GUI server is running, so autostart is recommended if you use night mode.

```sh
./uninstall_agents.sh    # remove both agents
```

## Known limitations

- On a **stereo pair**, the two speakers appear as one product. TTS/overlay audio
  plays from the primary speaker only; normal playback uses both.
- TTS generation is limited to 100 unique messages per device per day
  (identical messages are cached for 24 h).
- Qobuz has no native source on Mozart (as of firmware 6.2.x); use Chromecast,
  AirPlay 2, or DLNA from the Qobuz app instead.

## License

[MIT](LICENSE)
