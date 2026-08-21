import os
import re
import json
from datetime import datetime

import requests

STATE_FILE = "state.json"
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

JAVA_URL = "https://www.java.com/en/download/manual.jsp"
ERROR_NOTIFY_THRESHOLD = 2
HEARTBEAT_DAYS = 7

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

# Reminder specific to the laptop where updates otherwise fail with error 1603.
# Edit or remove this if it stops being relevant.
TEMP_REMINDER = (
    "Prima di aggiornare sul portatile: sposta TEMP e TMP da "
    "%USERPROFILE%\\AppData\\Local\\Temp a C:\\Temp (creala se serve), "
    "riavvia il PC, poi apri il Pannello di controllo Java (cerca "
    "'Rileva aggiornamenti' nel menu Start) e clicca 'Aggiorna ora'."
)


def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default if default is not None else {}


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def telegram(message):
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram non configurato")
        return
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data={
            "chat_id": CHAT_ID,
            "text": message,
            "disable_web_page_preview": True,
        },
        timeout=20,
    ).raise_for_status()


def get_latest_java():
    """Reads the official Java 8 download page and extracts the current
    update number, its release date, and the direct Windows Offline
    (64-bit) download link."""
    r = requests.get(JAVA_URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    html = r.text
    # Strip tags before matching version/date text, so an inline tag
    # between words (e.g. around just the number) can't break the match.
    text = re.sub(r"<[^>]+>", " ", html)

    version_match = re.search(r"Version\s+8\s+Update\s+(\d+)", text)
    if not version_match:
        raise ValueError("Numero di versione non trovato nella pagina Java")

    date_match = re.search(
        r"Release\s+date:?\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})", text
    )

    # The download link needs the actual href attribute, so this one is
    # matched against the raw HTML rather than the tag-stripped text.
    link_match = re.search(
        r'href="(https://javadl\.oracle\.com/webapps/download/AutoDL\?BundleId=[^"]+)"'
        r'[^>]*title="Download Java software for Windows \(64-bit\)"',
        html,
    )

    return {
        "update": version_match.group(1),
        "release_date": date_match.group(1) if date_match else None,
        "download_url": link_match.group(1) if link_match else JAVA_URL,
    }


def main():
    print(f"Controllo Java: {datetime.now():%d/%m/%Y %H:%M}")
    state = load_json(STATE_FILE, {})
    old_update = state.get("last_update")
    consecutive_errors = state.get("consecutive_errors", 0)
    was_down = consecutive_errors >= ERROR_NOTIFY_THRESHOLD

    try:
        info = get_latest_java()
        consecutive_errors = 0

        if was_down:
            telegram("✅ Il monitor Java è tornato a funzionare correttamente.")

        if old_update is not None and info["update"] != old_update:
            msg = f"☕ Nuovo aggiornamento Java: 8 Update {info['update']}\n"
            if info["release_date"]:
                msg += f"Rilasciato il {info['release_date']}\n"
            msg += f"\nDownload: {info['download_url']}\n"
            msg += f"\n⚠️ {TEMP_REMINDER}"
            telegram(msg)
            print("Notifica inviata")
        else:
            print("Nessun nuovo aggiornamento")

        state["last_update"] = info["update"]
        state["last_release_date"] = info["release_date"]
        state["last_checked"] = datetime.now().isoformat()

    except Exception as e:
        consecutive_errors += 1
        print(f"Errore: {e}")
        if consecutive_errors == ERROR_NOTIFY_THRESHOLD:
            telegram(
                "⚠️ Il monitor Java non riesce a leggere la pagina di "
                f"download da {ERROR_NOTIFY_THRESHOLD} controlli consecutivi.\n"
                f"{JAVA_URL}"
            )

    state["consecutive_errors"] = consecutive_errors

    first_run = state.get("first_run", datetime.now().isoformat())
    state["first_run"] = first_run
    last_heartbeat = state.get("last_heartbeat")

    if last_heartbeat is None:
        state["last_heartbeat"] = datetime.now().isoformat()
    else:
        days_since = (datetime.now() - datetime.fromisoformat(last_heartbeat)).days
        if days_since >= HEARTBEAT_DAYS:
            days_running = (datetime.now() - datetime.fromisoformat(first_run)).days
            telegram(
                "💓 Monitor Java attivo\n"
                f"Ultimo controllo: {datetime.now():%d/%m/%Y %H:%M}\n"
                f"Versione tracciata: 8 Update {state.get('last_update', 'n/d')}\n"
                f"In esecuzione da {days_running} giorni"
            )
            state["last_heartbeat"] = datetime.now().isoformat()

    save_json(STATE_FILE, state)


if __name__ == "__main__":
    main()
