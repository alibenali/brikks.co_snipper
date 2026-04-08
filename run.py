import requests
import logging, os, json, random
from bs4 import BeautifulSoup
from time import sleep
from datetime import datetime
import dotenv

dotenv.load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()

domain_name = "web.convoicar.fr"
LOGIN_URL = f"https://{domain_name}/users/sign_in"
HEADERS = {
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36 Edg/135.0.0.0',
    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'content-type': 'application/x-www-form-urlencoded',
    'origin': f'https://{domain_name}',
    'referer': LOGIN_URL,
}
DEFAULT_SETTINGS = json.loads(os.getenv("DEFAULT_SETTINGS", None))

PROXY_LIST_URL = os.getenv("PROXY_LIST_URL")

# Blocked status codes that trigger a proxy rotation
BLOCKED_STATUS_CODES = {403, 429, 503, 407}


class ProxyManager:
    """Downloads, stores, and rotates proxies from webshare.io."""

    def __init__(self, list_url: str):
        self.list_url = list_url
        self.proxies: list[dict] = []
        self.index = 0
        self.refresh()

    def refresh(self):
        """Download a fresh proxy list and shuffle it."""
        logger.info("Downloading fresh proxy list...")
        try:
            resp = requests.get(self.list_url, timeout=30)
            resp.raise_for_status()
            lines = [l.strip() for l in resp.text.splitlines() if l.strip()]
            parsed = []
            for line in lines:
                parts = line.split(":")
                if len(parts) == 4:
                    host, port, user, pwd = parts
                    parsed.append({
                        "http": f"http://{user}:{pwd}@{host}:{port}",
                        "https": f"http://{user}:{pwd}@{host}:{port}",
                    })
            if not parsed:
                logger.warning("Proxy list download returned no usable proxies.")
                return
            random.shuffle(parsed)
            self.proxies = parsed
            self.index = 0
            logger.info(f"Loaded {len(self.proxies)} proxies.")
        except Exception as e:
            logger.error(f"Failed to download proxy list: {e}")

    def current(self) -> dict | None:
        """Return the current proxy dict, or None if list is empty."""
        if not self.proxies:
            return None
        return self.proxies[self.index % len(self.proxies)]

    def rotate(self):
        """Advance to the next proxy; refresh the list when exhausted."""
        if not self.proxies:
            self.refresh()
            return
        self.index += 1
        if self.index >= len(self.proxies):
            logger.info("All proxies exhausted — refreshing the list.")
            self.refresh()
        else:
            logger.info(f"Rotated to proxy {self.index + 1}/{len(self.proxies)}.")

    def apply_to_session(self, session: requests.Session):
        """Set the current proxy on the given session."""
        proxy = self.current()
        if proxy:
            session.proxies.update(proxy)
        else:
            session.proxies.clear()


# ── Global proxy manager ──────────────────────────────────────────────────────
proxy_manager = ProxyManager(PROXY_LIST_URL)


def new_session() -> requests.Session:
    """Create a fresh requests session with the current proxy applied."""
    session = requests.Session()
    proxy_manager.apply_to_session(session)
    return session


def is_blocked(response: requests.Response) -> bool:
    """Return True if the server is indicating we are rate-limited / banned."""
    if response.status_code in BLOCKED_STATUS_CODES:
        return True
    # Captcha or CAPTCHA-like pages sometimes return 200 with a specific body
    if response.status_code == 200 and "captcha" in response.text.lower():
        return True
    return False


def settings_manager():
    settings_file = os.path.join(os.path.dirname(__file__), "settings.json")
    if not os.path.exists(settings_file):
        with open(settings_file, "w") as f:
            f.write(json.dumps(DEFAULT_SETTINGS, indent=2))
    with open(settings_file, "r") as f:
        settings = json.load(f)
    return settings


def send_message(chat_id, message):
    if os.getenv("TELEGRAM_BOT_TOKEN", None):
        requests.post(
            "https://api.telegram.org/bot" + os.getenv("TELEGRAM_BOT_TOKEN") + "/sendMessage",
            data={
                "chat_id": os.getenv("CHAT_ID", chat_id),
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            }
        )


def get_auth_token(session: requests.Session) -> str:
    """Fetch the login page and extract the authenticity_token."""
    logger.info("Fetching login page to get authentication token.")
    response = session.get(LOGIN_URL, headers=HEADERS, timeout=30)
    if is_blocked(response):
        raise BlockedError(f"Blocked while fetching login page (HTTP {response.status_code})")
    if response.status_code != 200:
        logger.error("Failed to retrieve the login page.")
        raise Exception("Failed to retrieve the login page.")

    soup = BeautifulSoup(response.text, 'html.parser')
    token_input = soup.find("input", {"name": "authenticity_token"})
    if not token_input:
        logger.error("Authenticity token not found.")
        raise Exception("Authenticity token not found.")
    logger.debug("Authenticity token extracted successfully.")
    return token_input["value"]


def login(session: requests.Session, email: str, password: str) -> bool:
    """Attempt to log in with the given credentials."""
    logger.info(f"Attempting to log in with email: {email}")
    authenticity_token = get_auth_token(session)
    payload = {
        'utf8': '✓',
        'authenticity_token': authenticity_token,
        'user[email]': email,
        'user[password]': password,
        'user[remember_me]': '1',
        'commit': 'Connexion'
    }

    response = session.post(LOGIN_URL, headers=HEADERS, data=payload, timeout=30)
    if is_blocked(response):
        raise BlockedError(f"Blocked during login (HTTP {response.status_code})")
    if "Se déconnecter" in response.text or response.url != LOGIN_URL:
        logger.info("Login successful.")
        return True

    logger.error("Login failed. Invalid credentials or blocked.")
    return False


def extract_ride_info(html_panel: BeautifulSoup) -> dict:
    try:
        depart_time = html_panel.find("div", class_="col-md-1").find_all("div", class_="row")[1].text.strip()
        trajets = html_panel.find_all("div", class_="col-md-1")[1].text.strip()
        type_label = html_panel.find_all("div", class_="col-md-1")[2].text.strip()
        itinerary = html_panel.find("div", class_="col-md-7").text.strip()
        arrival_time = html_panel.find_all("div", class_="col-md-1")[3].find_all("div", class_="row")[1].text.strip()
        price = html_panel.find("span", class_="label-price").text.strip()
        action_link = html_panel.find("a", class_="btn btn-block")["href"]

        return {
            "depart_time": depart_time,
            "trajets": trajets,
            "type": type_label,
            "itinerary": itinerary,
            "arrival_time": arrival_time,
            "price": price,
            "action_link": action_link
        }
    except Exception as e:
        print("Error while parsing ride info:", e)
        return {}


def check_rides(session: requests.Session, price: float):
    """Access a page that requires authentication."""
    response = session.get(f"https://{domain_name}/d/rides", headers=HEADERS, timeout=30)
    if is_blocked(response):
        raise BlockedError(f"Blocked on rides page (HTTP {response.status_code})")
    if response.status_code != 200:
        logger.error("Failed to access rides page.")
        raise Exception("Failed to access page")

    # Detect session expiry — site redirected us back to login
    if "sign_in" in response.url or "Connexion" in response.text[:500]:
        raise SessionExpiredError("Session expired — need to re-login.")

    soup = BeautifulSoup(response.text, 'html.parser')

    price_spans = soup.find_all("span", {"class": "label label-success label-price"})
    for price_span in price_spans:
        price_ = float(price_span.text.replace(",", ".").replace("€", ""))
        logger.debug(f"Found ride with price: {price_}")
        if price_ >= price:
            panel_div = price_span.parent.parent.parent.parent.parent
            ride_info = extract_ride_info(panel_div)
            ride_id = ride_info["action_link"].split("/")[-1]

            file_path = os.path.join(os.path.dirname(__file__), "saved_rides.json")
            if not os.path.exists(file_path):
                with open(file_path, "w") as f:
                    json.dump([], f)
            with open(file_path, "r") as f:
                try:
                    saved_rides = json.load(f)
                except json.JSONDecodeError:
                    saved_rides = []

            if ride_id in saved_rides:
                logger.info(f"Ride {ride_id} already accepted.")
                return False

            crf_token = soup.find("meta", {"name": "csrf-token"})["content"]
            logger.info("Ride found, ready to accept.")
            return [crf_token, ride_info]

    return False


def accept_ride(session: requests.Session, ride_info: str, crf_token: str = None) -> str:
    logger.info(f"Accepting ride at URL: {ride_info['action_link']}")
    ride_id = ride_info["action_link"].split("/")[-1]
    url = f"https://{domain_name}/d/rides/{ride_id}"
    payload = {
        "_method": "put",
        "authenticity_token": crf_token
    }
    headers = HEADERS.copy()
    headers.update({
        "referer": f"https://{domain_name}/d/rides",
        "origin": f"https://{domain_name}"
    })

    response = session.post(url, headers=headers, data=payload, timeout=30)
    if is_blocked(response):
        raise BlockedError(f"Blocked while accepting ride (HTTP {response.status_code})")
    if response.status_code != 200:
        logger.error(f"Failed to accept ride. Status code: {response.status_code}")
        raise Exception("Failed to accept ride")
    logger.info("Ride accepted successfully.")

    file_path = os.path.join(os.path.dirname(__file__), "saved_rides.json")
    if not os.path.exists(file_path):
        with open(file_path, "w") as f:
            f.write("[]")
    with open(file_path, "r") as f:
        saved_rides = json.load(f)
    saved_rides.append(ride_id)
    with open(file_path, "w") as f:
        json.dump(saved_rides, f)

    with open(os.path.join(os.path.dirname(__file__), "logs", f"accept_ride_{datetime.now().timestamp()}.html"), "w") as f:
        f.write(response.text)

    message = (
        f"✅ Trajet accepté avec succès:\n"
        f"Prix: {ride_info['price']}€\n"
        f"Adresse: {ride_info['itinerary']}\n"
        f"Depart: {ride_info['depart_time']}\n"
        f"Arrivé: {ride_info['arrival_time']}\n"
        f"Trajets: {ride_info['trajets']}\n"
        f"Type: {ride_info['type']}"
    )
    send_message(chat_id=os.getenv("CHAT_ID"), message=message)


# ── Custom exceptions ─────────────────────────────────────────────────────────

class BlockedError(Exception):
    """Raised when the server actively blocks us (rate-limit, ban, captcha)."""

class SessionExpiredError(Exception):
    """Raised when the session cookie is no longer valid."""


# ── Main loop with proxy rotation ─────────────────────────────────────────────

MAX_PROXY_RETRIES = 5   # rotate at most this many times before sleeping
BLOCK_SLEEP = 15        # seconds to wait after exhausting retries

def login_with_rotation(email: str, password: str) -> tuple[requests.Session, bool]:
    """Try to log in, rotating proxies on failure. Returns (session, success)."""
    for attempt in range(MAX_PROXY_RETRIES):
        session = new_session()
        try:
            success = login(session, email, password)
            if success:
                return session, True
            # Login returned False (bad creds or silent block) — rotate
            logger.warning(f"Login returned False on attempt {attempt + 1}, rotating proxy.")
            proxy_manager.rotate()
        except BlockedError as e:
            logger.warning(f"Blocked on login attempt {attempt + 1}: {e} — rotating proxy.")
            proxy_manager.rotate()
        except Exception as e:
            logger.error(f"Unexpected error on login attempt {attempt + 1}: {e} — rotating proxy.")
            proxy_manager.rotate()
    return new_session(), False


def main():
    email = os.getenv("EMAIL")
    password = os.getenv("PASSWORD")

    while True:
        settings = settings_manager()
        if not settings.get("monitoring", DEFAULT_SETTINGS["monitoring"]):
            sleep(1)
            continue

        logger.info("Starting the login process.")
        session, login_success = login_with_rotation(email, password)

        if not login_success:
            logger.error(f"[-] All {MAX_PROXY_RETRIES} login attempts failed. Sleeping {BLOCK_SLEEP}s before retry.")
            sleep(BLOCK_SLEEP)
            continue

        logger.info("[+] Logged in successfully.")
        logger.info("Checking for available rides with price >= %s€...",
                    settings.get("price", DEFAULT_SETTINGS["price"]))

        consecutive_failures = 0

        while True:
            settings = settings_manager()
            if not settings.get("monitoring", DEFAULT_SETTINGS["monitoring"]):
                break

            try:
                results = check_rides(session, settings.get("price", DEFAULT_SETTINGS["price"]))
                consecutive_failures = 0  # reset on success

                if results:
                    crf_token, ride_info = results
                    try:
                        accept_ride(session, ride_info, crf_token)
                    except BlockedError as e:
                        logger.warning(f"Blocked while accepting ride: {e} — rotating proxy and re-logging in.")
                        proxy_manager.rotate()
                        break  # break inner loop → outer loop will re-login

            except SessionExpiredError as e:
                logger.warning(f"Session expired: {e} — re-logging in.")
                break  # break inner loop → outer loop will re-login with fresh proxy

            except BlockedError as e:
                consecutive_failures += 1
                logger.warning(f"Blocked on check_rides (failure #{consecutive_failures}): {e} — rotating proxy.")
                proxy_manager.rotate()
                if consecutive_failures >= MAX_PROXY_RETRIES:
                    logger.error(f"Too many consecutive blocks. Sleeping {BLOCK_SLEEP}s.")
                    sleep(BLOCK_SLEEP)
                    break  # re-login with fresh proxy
                # Apply new proxy to the existing session
                proxy_manager.apply_to_session(session)
                continue  # retry immediately with new proxy

            except Exception as e:
                consecutive_failures += 1
                logger.error(f"[!] Unexpected error (failure #{consecutive_failures}): {e}")
                if consecutive_failures >= MAX_PROXY_RETRIES:
                    logger.error(f"Too many consecutive errors. Sleeping {BLOCK_SLEEP}s and re-logging in.")
                    sleep(BLOCK_SLEEP)
                    break
                proxy_manager.rotate()
                proxy_manager.apply_to_session(session)
                sleep(5)
                continue

            sleep(settings.get("interval", DEFAULT_SETTINGS["interval"]))


if __name__ == "__main__":
    main()
