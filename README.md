# Java Update Monitor

Automatic monitoring of the official Java 8 download page ([java.com](https://www.java.com/en/download/manual.jsp)), with a Telegram notification whenever a new update is published.

## How it works

On every run, `monitor.py`:

1. downloads the official Java 8 manual download page;
2. extracts the current update number, its release date, and the direct "Windows Offline (64-bit)" download link;
3. compares the update number against the last one saved in `state.json`;
4. if it changed, sends a Telegram message with the new version, its release date, the download link, and a reminder about a known installation workaround (see Configuration below); if the page is unreachable for several consecutive runs, sends an error notification (see below).

Execution is automated via GitHub Actions (`.github/workflows/monitor.yml`), twice a day, regardless of whether the local PC is on or off.

## Repository structure

```
monitor.py                     # main script
state.json                     # last detected version (updated automatically)
requirements.txt               # Python dependencies
.github/workflows/monitor.yml  # automatic scheduling
```

## Setup

### 1. Dependencies

```
pip install -r requirements.txt
```

### 2. Telegram secrets

The script reads `BOT_TOKEN` and `CHAT_ID` from environment variables.

**Locally (PowerShell)**, for manual testing only:

```powershell
$env:BOT_TOKEN="..."
$env:CHAT_ID="..."
python monitor.py
```

These locally set values are **not read by GitHub Actions**: for automatic execution they must be configured as repository *Secrets*:

1. Go to **Settings → Secrets and variables → Actions** in the GitHub repository;
2. create a secret named `BOT_TOKEN` with the Telegram bot token;
3. create a secret named `CHAT_ID` with the id of the destination chat/channel;
4. make sure the repository's **Actions** tab is enabled (GitHub sometimes disables it by default on new repositories).

Without these two secrets, the script prints "Telegram non configurato" and sends nothing — this is the expected behavior when running locally without wanting to set them.

### 3. Scheduling

The workflow runs at 10:00 and 22:00 Italian time (cron `0 8,20 * * *`, calculated for summer daylight saving time UTC+2; in winter the actual local time will be 9:00/21:00, since GitHub Actions always runs in UTC and doesn't automatically adjust for daylight saving changes). It can also be triggered manually from the Actions tab ("Run workflow").

## Configuration

The behavior can be adjusted through a few constants at the top of `monitor.py`:

- `JAVA_URL`: the page being monitored (`https://www.java.com/en/download/manual.jsp` by default);
- `ERROR_NOTIFY_THRESHOLD`: number of consecutive failed checks before an error notification is sent;
- `HEARTBEAT_DAYS`: how often the heartbeat notification is sent;
- `TEMP_REMINDER`: the text appended to every update notification. It currently reminds to move `TEMP`/`TMP` to `C:\Temp` and update through the Java Control Panel ("Rileva aggiornamenti" in the Start menu → "Aggiorna ora") on one specific machine where updates otherwise fail with error 1603 — edit or remove it if it stops being relevant. If this method were ever to fail, downloading the Offline installer from java.com and running it as administrator is the documented fallback with a longer track record.

## Error notifications

If the download page is unreachable for **two consecutive checks**, a separate Telegram notification is sent. The two-check threshold avoids alerting on a single transient issue, while still flagging a persistent problem within about ten hours. When the page becomes reachable again, a recovery notification is sent.

The threshold can be configured by changing `ERROR_NOTIFY_THRESHOLD` in `monitor.py`.

## Heartbeat notifications

To confirm that the monitor is still running correctly even when there's no new update to report, the workflow sends a periodic Telegram heartbeat every 7 days (configurable through `HEARTBEAT_DAYS`).

The heartbeat includes:

- date and time of the latest successful check;
- update number currently tracked;
- days since the monitor started running.

## Notes

- `state.json` is overwritten and automatically committed by the workflow on every run, to preserve monitoring history between runs.
- `state.json` ships pre-filled with the version known at the time this repository was created, so the first scheduled run won't silently skip notifying about the *next* update — it starts comparing right away instead of first needing a baseline run.

## License

This project is licensed under the [PolyForm Noncommercial License 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0). You may use, modify, and distribute this software for noncommercial purposes.

For commercial use or an extended license, please contact me: lufaletra@gmail.com
