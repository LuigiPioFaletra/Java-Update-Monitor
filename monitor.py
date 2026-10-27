import os
import re
import sys
import json
from datetime import datetime

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

STATE_FILE = "state.json"
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
TEST_NOTIFICATION = os.getenv("TEST_NOTIFICATION") == "true"

JAVA_URL = "https://www.java.com/en/download/manual.jsp"
ERROR_NOTIFY_THRESHOLD = 2
HEARTBEAT_DAYS = 7

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

# (connect, read) timeouts in seconds.
JAVA_TIMEOUT = (10, 30)
TELEGRAM_TIMEOUT = (10, 30)


def make_session(total_retries):
    """Session that automatically retries transient network errors
    (timeouts, dropped connections, 429/5xx) with exponential backoff."""
    retry = Retry(
        total=total_retries,
        connect=total_retries,
        read=total_retries,
        status=total_retries,
        backoff_factor=3,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


JAVA_SESSION = make_session(total_retries=3)
# Fewer retries for Telegram: a read timeout may mean the message was
# actually delivered, so retrying too much could produce duplicates.
TELEGRAM_SESSION = make_session(total_retries=2)

# Reminder specific to the laptop where updates otherwise fail with error 1603.
# Edit or remove this if it stops being relevant.
TEMP_REMINDER = (
    "Procedura di aggiornamento sul portatile:\n"
    "1) Se non esiste, crea la cartella C:\\Temp (non importa se è vuota "
    "o piena).\n"
    "2) Apri 'Modifica le variabili d'ambiente relative al tuo account' "
    "(cercalo nel menu Start) e, tra le variabili dell'utente, cambia TEMP "
    "e TMP da %USERPROFILE%\\AppData\\Local\\Temp a C:\\Temp. "
    "Conferma con OK e riavvia il PC.\n"
    "3) Apri il Pannello di controllo Java (cerca 'Rileva aggiornamenti' "
    "nel menu Start), clicca 'Aggiorna ora' e completa l'aggiornamento.\n"
    "4) Riporta le variabili TEMP e TMP dell'utente a "
    "%USERPROFILE%\\AppData\\Local\\Temp e conferma con OK.\n"
    "5) Elimina la cartella C:\\Temp (se qualche file risulta in uso, "
    "riavvia il PC e riprova)."
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
    """Sends a Telegram message. Never raises: returns True on success,
    False on failure, so a Telegram outage can't crash the monitor."""
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram non configurato")
        return False
    try:
        TELEGRAM_SESSION.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={
                "chat_id": CHAT_ID,
                "text": message,
                "disable_web_page_preview": True,
            },
            timeout=TELEGRAM_TIMEOUT,
        ).raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        # Print only the exception type: the message could contain the
        # URL with the bot token.
        print(f"Invio Telegram fallito ({type(e).__name__})")
        return False


def get_latest_java():
    """Reads the official Java 8 download page and extracts the current
    update number, its release date, and the direct Windows Offline
    (64-bit) download link."""
    r = JAVA_SESSION.get(JAVA_URL, headers=HEADERS, timeout=JAVA_TIMEOUT)
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


def update_message(info, previous_date=None):
    """previous_date is set for a re-release: same update number, new
    release date (Oracle sometimes republishes an update with a new build)."""
    if previous_date:
        msg = (f"🔁 Java 8 Update {info['update']} ripubblicato "
               "(nuova build)\n")
        msg += (f"Nuova data di rilascio: {info['release_date']} "
                f"(prima: {previous_date})\n")
    else:
        msg = f"☕ Nuovo aggiornamento Java: 8 Update {info['update']}\n"
        if info["release_date"]:
            msg += f"Rilasciato il {info['release_date']}\n"
    msg += f"\nDownload: {info['download_url']}\n"
    msg += f"\n⚠️ {TEMP_REMINDER}"
    return msg


def main():
    if TEST_NOTIFICATION:
        # Manual test from "Run workflow": sends the update notification for
        # the current version without touching state.json.
        info = get_latest_java()
        if not telegram("🧪 Messaggio di prova\n\n" + update_message(info)):
            print("Notifica di prova NON inviata")
            sys.exit(1)
        print("Notifica di prova inviata")
        return

    print(f"Controllo Java: {datetime.now():%d/%m/%Y %H:%M}")
    state = load_json(STATE_FILE, {})
    old_update = state.get("last_update")
    old_release_date = state.get("last_release_date")
    consecutive_errors = state.get("consecutive_errors", 0)
    # Backward compatible with state.json files written before this flag
    # existed: the old logic notified exactly when the threshold was hit.
    error_notified = state.get(
        "error_notified", consecutive_errors >= ERROR_NOTIFY_THRESHOLD
    )

    try:
        info = get_latest_java()
    except Exception as e:
        info = None
        consecutive_errors += 1
        print(f"Errore lettura pagina Java: {e}")
        if consecutive_errors >= ERROR_NOTIFY_THRESHOLD and not error_notified:
            # Retried on every run until it actually goes through.
            error_notified = telegram(
                "⚠️ Il monitor Java non riesce a leggere la pagina di "
                f"download da {consecutive_errors} controlli consecutivi.\n"
                f"{JAVA_URL}"
            )

    if info is not None:
        consecutive_errors = 0
        if error_notified:
            telegram("✅ Il monitor Java è tornato a funzionare correttamente.")
            error_notified = False

        is_new_update = old_update is not None and info["update"] != old_update
        # Both dates must be known: a date the regex failed to read is not
        # a re-release.
        is_republished = (
            not is_new_update
            and old_update is not None
            and old_release_date is not None
            and info["release_date"] is not None
            and info["release_date"] != old_release_date
        )

        if is_new_update or is_republished:
            message = update_message(
                info, old_release_date if is_republished else None
            )
            if telegram(message):
                print("Notifica inviata")
                state["last_update"] = info["update"]
                state["last_release_date"] = info["release_date"]
            else:
                # Keep the old version/date in state.json so the next run
                # detects the change again and retries the notification.
                print("Novità trovata ma notifica non inviata: "
                      "verrà ritentata al prossimo controllo")
        else:
            print("Nessun nuovo aggiornamento")
            state["last_update"] = info["update"]
            # Keep the last known date if this read missed it, so a later
            # re-release is still compared against it.
            if info["release_date"] is not None:
                state["last_release_date"] = info["release_date"]

        state["last_checked"] = datetime.now().isoformat()

    state["consecutive_errors"] = consecutive_errors
    state["error_notified"] = error_notified

    first_run = state.get("first_run", datetime.now().isoformat())
    state["first_run"] = first_run
    last_heartbeat = state.get("last_heartbeat")

    if last_heartbeat is None:
        state["last_heartbeat"] = datetime.now().isoformat()
    else:
        days_since = (datetime.now() - datetime.fromisoformat(last_heartbeat)).days
        if days_since >= HEARTBEAT_DAYS:
            days_running = (datetime.now() - datetime.fromisoformat(first_run)).days
            sent = telegram(
                "💓 Monitor Java attivo\n"
                f"Ultimo controllo: {datetime.now():%d/%m/%Y %H:%M}\n"
                f"Versione tracciata: 8 Update {state.get('last_update', 'n/d')}\n"
                f"In esecuzione da {days_running} giorni"
            )
            # If it fails, last_heartbeat is left as is and the heartbeat
            # is retried on the next run.
            if sent:
                state["last_heartbeat"] = datetime.now().isoformat()

    save_json(STATE_FILE, state)


if __name__ == "__main__":
    main()
