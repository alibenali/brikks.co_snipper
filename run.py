import requests
import logging, os, json
from bs4 import BeautifulSoup
from time import sleep
from datetime import datetime
import dotenv

dotenv.load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()

LOGIN_URL = "https://app.brikks.co/users/sign_in"
HEADERS = {
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36 Edg/135.0.0.0',
    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'content-type': 'application/x-www-form-urlencoded',
    'origin': 'https://app.brikks.co',
    'referer': LOGIN_URL,
}
DEFAULT_SETTINGS = json.loads(os.getenv("DEFAULT_SETTINGS", None))

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
        req= requests.post(
            "https://api.telegram.org/bot" + os.getenv("TELEGRAM_BOT_TOKEN") + "/sendMessage",
            data={
                "chat_id": os.getenv("CHAT_ID", chat_id),
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            }
        )
def get_auth_token(session: requests.Session) -> str:
    """Fetch the login page and extract the authenticity_token"""
    logger.info("Fetching login page to get authentication token.")
    response = session.get(LOGIN_URL, headers=HEADERS)
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
    """Attempt to log in with the given credentials"""
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

    response = session.post(LOGIN_URL, headers=HEADERS, data=payload)
    if "Se déconnecter" in response.text or response.url != LOGIN_URL:
        logger.info("Login successful.")
        return True

    logger.error("Login failed. Invalid credentials?")
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
    
def check_rides(session: requests.Session, price: float) -> str:
    """Access a page that requires authentication"""
    response = session.get("https://app.brikks.co/d/rides", headers=HEADERS)
    if response.status_code != 200:
        logger.error("Failed to access rides page.")
        raise Exception("Failed to access page")
    
    soup = BeautifulSoup(response.text, 'html.parser')

    price_spans = soup.find_all("span", {"class": "label label-success label-price"})
    for price_span in price_spans:
        price_ = float(price_span.text.replace(",", ".").replace("€", ""))
        logger.debug(f"Found ride with price: {price}")
        if price_ >= price:
            panel_div = price_span.parent.parent.parent.parent.parent
            ride_info = extract_ride_info(panel_div)
            # get crftoken from <meta name="csrf-token" content="...">
            crf_token = soup.find("meta", {"name": "csrf-token"})["content"]
            logger.info("Ride found, ready to accept.")
            return [crf_token, ride_info]
    return False

def accept_ride(session: requests.Session, ride_info: str, crf_token: str = None) -> str:
    logger.info(f"Accepting ride at URL: {ride_info['action_link']}")
    authenticity_token = crf_token
    ride_id = ride_info["action_link"].split("/")[-1]
    url = f"https://app.brikks.co/d/rides/{ride_id}"
    payload = {
        "_method": "put",
        "authenticity_token": authenticity_token
    }
    headers = HEADERS.copy()
    headers.update({
        "referer": "https://app.brikks.co/d/rides",
        "origin": "https://app.brikks.co"
    })

    response = session.post(url, headers=headers, data=payload)
    if response.status_code != 200:
        logger.error(f"Failed to accept ride at {ride_info['action_link']}. Status code: {response.status_code}")
        raise Exception("Failed to accept ride")
    logger.info("Ride accepted successfully.")
    # save response to a file in logs folder
    with open(os.path.join(os.path.dirname(__file__), "logs", f"accept_ride_{datetime.now().timestamp()}.html"), "w") as f:
        f.write(response.text)

    # Send details in the Telegram message
    message = f"✅ Trajet accepté avec succès:\nPrix: {ride_info['price']}€\nAdresse: {ride_info['itinerary']}\nDepart: {ride_info['depart_time']}\nArrivé: {ride_info['arrival_time']}\nTrajets: {ride_info['trajets']}\nType: {ride_info['type']}"
    send_message(chat_id=os.getenv("CHAT_ID"), message=message)

def main():

    email = os.getenv("EMAIL")
    password = os.getenv("PASSWORD")

    while True:
        settings = settings_manager()
        if(settings.get("monitoring", DEFAULT_SETTINGS["monitoring"]) == True):
            try:
                logger.info("Starting the login process.")
                session = requests.Session()
                login_success = login(session, email, password)
                if login_success:
                    logger.info("[+] Logged in successfully.")
                    logging.info("Checking for available rides with price >= %s€...", settings.get("price", DEFAULT_SETTINGS["price"]))
                    while True:
                        settings = settings_manager()
                        if(settings.get("monitoring", DEFAULT_SETTINGS["monitoring"]) == False):
                            break
                        results = check_rides(session,settings.get("price", DEFAULT_SETTINGS["price"]))
                        if results:
                            crf_token, accept_url = results
                            accept_ride(session, accept_url, crf_token)
                        sleep(settings.get("interval", DEFAULT_SETTINGS["interval"]))
                else:
                    logger.error("[-] Login failed.")
            except Exception as e:
                sleep(100)
                logger.error(f"[!] Error: {e}")
        else:
            sleep(1)

if __name__ == "__main__":
    main()
