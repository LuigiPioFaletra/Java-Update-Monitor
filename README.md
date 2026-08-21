# Java Update Monitor

Automatic monitoring of the official Java 8 download page ([java.com](https://www.java.com/en/download/manual.jsp)), with a Telegram notification whenever a new update is published — including a direct download link and a reminder about the `TEMP`/`TMP` workaround needed before installing on one specific machine.

## How it works

On every run, `monitor.py`:

1. downloads the official Java 8 manual download page;
2. extracts the current update number, its release date, and the direct "Windows Offline (64-bit)" download link;
3. compares the update number against the last one saved in `state.json`;
4. if it changed, sends a Telegram message with the new version, its release date, the download link, and the `TEMP`/`TMP` reminder.

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

```
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
- Unlike [inPA-Monitor](https://github.com/LuigiPioFaletra/inPA-Monitor), this project tracks a single fixed URL (`JAVA_URL` in `monitor.py`) instead of a list in a separate config file, since there's only one page to check.
- The `TEMP`/`TMP` reminder is specific to one machine's setup (error 1603 during Java updates, worked around by moving `TEMP`/`TMP` to `C:\Temp` before installing). Edit or remove the `TEMP_REMINDER` constant in `monitor.py` if it stops being relevant.
- `state.json` ships pre-filled with the version known at the time this repository was created, so the first scheduled run won't silently skip notifying about the *next* update — it starts comparing right away instead of first needing a baseline run.

## License

This project is licensed under the [PolyForm Noncommercial License 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0), matching the license used for [inPA-Monitor](https://github.com/LuigiPioFaletra/inPA-Monitor). Change or remove this section if you'd rather use a different license for this repository.
