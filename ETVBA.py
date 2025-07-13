import os
import time
import random
import logging
import requests
import json
import threading
import signal
import re
import sys
import platform
import subprocess

# New import for parsing HTML
from bs4 import BeautifulSoup

# Add the is_channel_live function here to avoid undefined error
def is_channel_live(twitch_name):
    """
    Check if the Twitch channel is live using public endpoint.
    Returns True if live, False if offline or error.
    """
    try:
        url = f"https://www.twitch.tv/{twitch_name}"
        headers = {
            "User-Agent": random.choice(config["user_agents"])
        }
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            logging.warning(f"Failed to fetch Twitch page for {twitch_name}, status code {response.status_code}")
            return False
        # Parse HTML to detect live status
        html = response.text
        # Look for "isLiveBroadcast" or "stream is live" indicators in HTML
        if "isLiveBroadcast" in html or "stream is live" in html.lower():
            return True
        # Alternative: check for presence of "Live" badge or player container
        if 'data-a-player-state="playing"' in html:
            return True
        # Fallback: check for "offline" text or absence of live indicators
        if "offline" in html.lower():
            return False
        # If uncertain, assume offline
        return False
    except Exception as e:
        logging.error(f"Error checking live status for {twitch_name}: {str(e)}")
        return False
# Remove legacy webdriver import
#from selenium import webdriver
from selenium.common.exceptions import WebDriverException, TimeoutException, NoSuchWindowException, StaleElementReferenceException
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
try:
    from retrying import retry
    import undetected_chromedriver as uc
    import psutil
except ImportError as e:
    print(f"\033[91mMissing dependency: {str(e)}. Install with: pip install undetected-chromedriver psutil retrying requests\033[0m")
    sys.exit(1)

# --- Environment Check ---
def check_environment():
    print(f"Python Version: {sys.version}")
    print(f"Platform: {platform.system()} {platform.release()}")
    # Remove strict Chrome version check, just check if Chrome is present in PATH
    chrome_found = False
    chrome_commands = [
        ["chrome.exe", "--version"],
        ["google-chrome", "--version"],
        ["chromium", "--version"],
        ["chromium-browser", "--version"]
    ]
    for cmd in chrome_commands:
        try:
            chrome_version = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT).decode().strip()
            print(f"Chrome detected: {chrome_version}")
            chrome_found = True
            break
        except Exception:
            continue
    if not chrome_found:
        print(f"\033[91mChrome not detected in PATH. Please install Google Chrome from https://www.google.com/chrome/ and ensure it is in your system PATH.\033[0m")
        return False
    try:
        import undetected_chromedriver
        import psutil
        import retrying
        import requests
        print("All required Python packages are installed: undetected_chromedriver, psutil, retrying, requests")
        return True
    except ImportError as e:
        print(f"\033[91mMissing Python package: {str(e)}. Install with: pip install undetected-chromedriver psutil retrying requests\033[0m")
        return False

###############################
# === Timing/Wait Settings === #
###############################
# All wait times and timeouts are defined here for easy tuning (medium for average proxies/sites)
WAIT_PROXY_LOAD = 2.0           # Medium proxy page load
WAIT_AFTER_URL_SUBMIT = 2.0     # Medium URL submit
WAIT_AFTER_TWITCH_LOAD = 6.0    # Medium Twitch load/quality change
WAIT_BETWEEN_TABS = (0.4, 0.8)  # Medium min/max random wait between opening tabs
WAIT_BETWEEN_VIEWERS = (0.4, 0.8) # Medium min/max random wait after viewer loads
WAIT_BETWEEN_THREADS = (0.2, 0.5) # Medium min/max random wait between thread starts
WAIT_SUSTAIN_LOOP = 1.0         # Medium sustain loop

# All timeouts (in seconds)
IFRAME_TIMEOUT = 30
VIDEO_TIMEOUT = 60
INPUT_TIMEOUT = 30

# --- Configurable settings ---
CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'viewbot_config.json')
DEFAULT_CONFIG = {
    "user_agents": [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.1 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/117.0",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
    ],
    "proxies": [
        "https://www.croxyproxy.com",
        "https://www.croxyproxy.rocks",
        "https://www.croxy.network",
        "https://www.croxy.org",
        "https://www.croxyproxy.net",
    ],
    "activity_interval": 30,
    "min_viewer_duration": 1000,
    "max_viewer_duration": 2000,
    "input_selectors": [
        "input#url",  # Most robust
        "input[name='url']",
        "input[id='url']",
        "input[type='url']",
        "input[name*='url']",
        "input[id*='url']",
        "input[placeholder*='url']",
        "input[placeholder*='URL']",
        "input[placeholder*='link']",
        "input[placeholder*='website']",
        "input[placeholder*='address']",
        "input[type='text']",
        "input[autocomplete*='url']",
        "input[class*='url']",
        "input[aria-label*='url']",
    ],
    "action_labels": [
        'Continue', 'OK', 'Accept', 'Proceed', 'Go', 'Submit', 'Enter', 'I Understand', 'Start Watching',
    ],
    "mature_button_xpath": "//button[@data-a-target='player-mature-accept-button']",
    "start_watching_button_xpath": "//button[@data-a-target='content-classification-gate-overlay-start-watching-button']",
    "video_player_xpath": "//div[@data-a-target='player-overlay-click-handler']",
    "settings_button_xpath": "//button[@data-a-target='player-settings-button']",
    "quality_menu_item_xpath": "//div[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'quality')]",
    # New: List of robust/fallback XPaths for Twitch quality options
    "quality_options_xpaths": [
        "//div[@role='menuitemradio']//span",  # Most common
        "//div[@data-a-target='tw-core-button-label-text']",  # Fallback for new UI
        "//div[@role='menuitemradio']",  # Fallback: select the whole item
        "//span[contains(text(), 'Quality')]//following::div[@role='menuitemradio']//span",  # Relative to Quality label
        "//div[contains(@class, 'quality-option')]//span",  # Class-based fallback
    ],
    # For backward compatibility, keep the first as the default
    "quality_options_xpath": "//div[@role='menuitemradio']//span",
    "iframe_timeout": IFRAME_TIMEOUT,
    "video_timeout": VIDEO_TIMEOUT,
    "input_timeout": INPUT_TIMEOUT,
    "failure_threshold": 5,
    "window_size_range": {"min_width": 800, "max_width": 1280, "min_height": 600, "max_height": 720},
    "retry_attempts": 3,
    "reconnect_delay": 5,
}

def load_config():
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r') as f:
                config = json.load(f)
                for key, value in DEFAULT_CONFIG.items():
                    if key not in config:
                        config[key] = value
                return config
        else:
            logging.warning(f"Config file {CONFIG_PATH} not found, using default config")
            return DEFAULT_CONFIG
    except Exception as e:
        logging.error(f"Failed to load config: {str(e)}")
        return DEFAULT_CONFIG

config = load_config()

# --- Logging setup ---
logging.basicConfig(
    filename=os.path.join(os.path.dirname(__file__), 'error_log.txt'),
    filemode='a',
    format='%(asctime)s %(levelname)s: %(message)s',
    level=logging.DEBUG
)

# --- Proxy health tracking ---
PROXY_HEALTH = {proxy: {'success': 0, 'fail': 0} for proxy in config["proxies"]}
FAILED_PROXIES = set()

def update_proxy_health(proxy, success):
    PROXY_HEALTH[proxy]['success' if success else 'fail'] += 1
    logging.debug(f"Proxy {proxy} health: {PROXY_HEALTH[proxy]}")

def get_best_proxy(valid_proxies):
    available = [p for p in valid_proxies if p not in FAILED_PROXIES]
    if not available:
        FAILED_PROXIES.clear()
        available = valid_proxies
    return min(available, key=lambda p: PROXY_HEALTH.get(p, {'fail': 0})['fail'])

# --- Graceful shutdown handler ---
shutdown_flag = threading.Event()
def handle_sigint(sig, frame):
    print("\n\033[91mShutting down...\033[0m")
    shutdown_flag.set()
signal.signal(signal.SIGINT, handle_sigint)

def is_interactable(element):
    try:
        return element.is_displayed() and element.is_enabled()
    except Exception:
        return False

def find_element_in_iframes(driver, xpath, timeout):
    try:
        element = WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.XPATH, xpath)))
        logging.info("Element found in main frame")
        return element
    except TimeoutException:
        logging.info("Element not found in main frame, checking iframes")  # Changed from warning to info
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        for iframe in iframes:
            try:
                driver.switch_to.frame(iframe)
                element = WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.XPATH, xpath)))
                logging.info(f"Element found in iframe {iframe.get_attribute('src')}")
                return element
            except Exception:
                driver.switch_to.default_content()
        raise TimeoutException("Element not found in any iframe")

def input_url(driver, enterurl, twitch_url):
    input_methods = [
        ("standard", lambda: [enterurl.clear(), enterurl.send_keys(twitch_url)]),
        ("javascript", lambda: [
            driver.execute_script("arguments[0].value = arguments[1];", enterurl, twitch_url),
            driver.execute_script("arguments[0].dispatchEvent(new Event('input'));", enterurl),
            driver.execute_script("arguments[0].dispatchEvent(new Event('change'));", enterurl),
            driver.execute_script("arguments[0].dispatchEvent(new Event('blur'));", enterurl)
        ])
    ]
    for method_name, method in input_methods:
        try:
            method()
            logging.info(f"URL input successful via {method_name} method")
            return True
        except Exception as e:
            logging.warning(f"URL input failed via {method_name} method: {str(e)}")
    return False

def submit_form(driver, enterurl):
    submit_methods = [
        ("enter_key", lambda: enterurl.send_keys(Keys.RETURN)),
        ("form_submit", lambda: enterurl.find_element(By.XPATH, "./ancestor::form").submit()),
        ("submit_button", lambda: driver.find_elements(By.XPATH, "//button[@type='submit'] | //input[@type='submit']")[0].click()),
        ("javascript_enter", lambda: driver.execute_script("arguments[0].dispatchEvent(new KeyboardEvent('keydown', {'key': 'Enter'}));", enterurl))
    ]
    for method_name, method in submit_methods:
        try:
            method()
            logging.info(f"Form submission successful via {method_name} method")
            time.sleep(1)
            return True
        except Exception as e:
            logging.warning(f"Form submission failed via {method_name}: {str(e)}")
    return False

def create_viewer(driver, proxy, twitch_url, proxy_failures):
    try:
        logging.info(f"Opening proxy: {proxy}")
        # Open a new tab and navigate to the proxy URL (all in same browser)
        driver.execute_script("window.open('about:blank', '_blank');")
        time.sleep(0.5)
        handles = driver.window_handles
        driver.switch_to.window(handles[-1])
        # No need to set window size here; it's set once in setup_driver
        driver.get(proxy)
        time.sleep(1)
        # Find input field
        enterurl = None
        input_attempts = 0
        max_input_attempts = 3
        url_keywords = ["url", "link", "website", "address"]
        while input_attempts < max_input_attempts:
            # Refresh the page if this is not the first attempt
            if input_attempts > 0:
                try:
                    driver.refresh()
                    time.sleep(2)
                except Exception as e:
                    logging.warning(f"Page refresh failed on input attempt {input_attempts+1}: {str(e)}")
            for selector in config["input_selectors"]:
                try:
                    logging.info(f"Attempt {input_attempts + 1}/{max_input_attempts} - Trying selector: {selector}")
                    el = WebDriverWait(driver, config['input_timeout']).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    if is_interactable(el):
                        enterurl = el
                        logging.info(f"Found interactable input with selector: {selector}")
                        break
                except Exception as e:
                    logging.warning(f"Selector {selector} failed: {str(e)}")
            if enterurl:
                break
            # Smart scan: look for any input with url-like attributes
            try:
                all_inputs = driver.find_elements(By.TAG_NAME, "input")
                for inp in all_inputs:
                    if not is_interactable(inp):
                        continue
                    attrs = [
                        inp.get_attribute("placeholder") or "",
                        inp.get_attribute("name") or "",
                        inp.get_attribute("id") or "",
                        inp.get_attribute("aria-label") or "",
                        inp.get_attribute("type") or "",
                    ]
                    attrs = [a.lower() for a in attrs]
                    if any(any(kw in a for kw in url_keywords) for a in attrs):
                        enterurl = inp
                        logging.info(f"Smart scan: Found input with url-like attribute: {attrs}")
                        break
                # Fallback: first visible and enabled <input> field
                if not enterurl:
                    for inp in all_inputs:
                        if is_interactable(inp):
                            enterurl = inp
                            logging.info("Fallback: Found first visible and enabled <input> field on page.")
                            break
            except Exception as e:
                logging.warning(f"Smart scan/fallback input search failed: {str(e)}")
            if enterurl:
                break
            input_attempts += 1
            time.sleep(2)
        if not enterurl:
            # Try a final hard refresh and one last scan
            try:
                driver.refresh()
                time.sleep(3)
                all_inputs = driver.find_elements(By.TAG_NAME, "input")
                for inp in all_inputs:
                    if is_interactable(inp):
                        enterurl = inp
                        logging.info("Final fallback: Found input after hard refresh.")
                        break
            except Exception as e:
                logging.warning(f"Final fallback input search failed: {str(e)}")
        if not enterurl:
            raise Exception("Input field not found after retries, smart scan, and fallback.")
        # Input the URL
        if not input_url(driver, enterurl, twitch_url):
            raise Exception("Failed to input URL")
        # Submit the form
        if not submit_form(driver, enterurl):
            raise Exception("Failed to submit URL")
        # Handle buttons
        for label in config["action_labels"]:
            try:
                btns = driver.find_elements(By.XPATH, f"//button[contains(text(), '{label}')]")
                for btn in btns:
                    if is_interactable(btn):
                        try:
                            btn.click()
                            logging.info(f"Clicked button with label: {label}")
                        except Exception:
                            driver.execute_script("arguments[0].click();", btn)
                            logging.info(f"JavaScript click successful for {label}")
                        time.sleep(0.5)
            except Exception as e:
                logging.warning(f"Error handling button {label}: {str(e)}")
        # Handle mature content button
        mature_btns = driver.find_elements(By.XPATH, config["mature_button_xpath"])
        mature_clicked = False
        for btn in mature_btns:
            if is_interactable(btn):
                try:
                    btn.click()
                    logging.info("Clicked mature content button")
                    mature_clicked = True
                except Exception:
                    driver.execute_script("arguments[0].click();", btn)
                    logging.info("JavaScript click successful for mature button")
                    mature_clicked = True
                time.sleep(0.5)
        # Always try to click the start watching button after mature content
        start_watching_btns = driver.find_elements(By.XPATH, config["start_watching_button_xpath"])
        for btn in start_watching_btns:
            if is_interactable(btn):
                try:
                    btn.click()
                    logging.info("Clicked start watching button")
                except Exception:
                    driver.execute_script("arguments[0].click();", btn)
                    logging.info("JavaScript click successful for start watching button")
                time.sleep(2)
        # Handle cookies acceptance and proceed button on Twitch
        try:
            # Accept Cookies
            cookie_buttons = driver.find_elements(By.XPATH, "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'accept') and contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'cookie')]")
            for btn in cookie_buttons:
                if is_interactable(btn):
                    try:
                        btn.click()
                        logging.info("Clicked 'Accept Cookies' button on Twitch")
                    except Exception:
                        driver.execute_script("arguments[0].click();", btn)
                        logging.info("JavaScript click successful for 'Accept Cookies' button on Twitch")
                    time.sleep(0.5)
            # Proceed Button (for consent/cookies)
            proceed_buttons = driver.find_elements(By.XPATH, "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'proceed')]")
            for btn in proceed_buttons:
                if is_interactable(btn):
                    try:
                        btn.click()
                        logging.info("Clicked 'Proceed' button on Twitch")
                    except Exception:
                        driver.execute_script("arguments[0].click();", btn)
                        logging.info("JavaScript click successful for 'Proceed' button on Twitch")
                    time.sleep(0.5)
        except Exception as e:
            logging.warning(f"Error handling 'Accept Cookies' or 'Proceed' button: {str(e)}")
        # Wait for video player to appear before setting quality, with more robust retry
        video = None
        for attempt in range(5):
            try:
                video = find_element_in_iframes(driver, config["video_player_xpath"], config["video_timeout"])
                if is_interactable(video):
                    ActionChains(driver).move_to_element(video).perform()
                    logging.info(f"Video player interaction successful (attempt {attempt+1})")
                    break
            except Exception as e:
                logging.warning(f"Video player not found (attempt {attempt+1}): {str(e)}")
                time.sleep(3)
        if not video:
            logging.error("Failed to find video player after retries, will not close browser immediately.")
            print("\033[93mWarning: Could not find video player after retries. Viewer will remain open for debugging.\033[0m")
        # Now set quality based on available options, with extra retries and all fallback XPaths
        quality_success = False
        for attempt in range(3):
            try:
                settings_button = WebDriverWait(driver, 15).until(
                    EC.element_to_be_clickable((By.XPATH, config["settings_button_xpath"]))
                )
                driver.execute_script("arguments[0].scrollIntoView(true);", settings_button)
                try:
                    settings_button.click()
                    logging.info(f"Clicked settings button (attempt {attempt+1})")
                except Exception:
                    driver.execute_script("arguments[0].click();", settings_button)
                    logging.info(f"JavaScript click successful for settings button (attempt {attempt+1})")
                time.sleep(1)
                quality_menu_item = WebDriverWait(driver, 15).until(
                    EC.element_to_be_clickable((By.XPATH, config["quality_menu_item_xpath"]))
                )
                driver.execute_script("arguments[0].scrollIntoView(true);", quality_menu_item)
                try:
                    quality_menu_item.click()
                    logging.info(f"Clicked quality menu item (attempt {attempt+1})")
                except Exception:
                    driver.execute_script("arguments[0].click();", quality_menu_item)
                    logging.info(f"JavaScript click successful for quality menu item (attempt {attempt+1})")
                time.sleep(1)
                # Try all fallback XPaths for quality options
                for xpath in config.get("quality_options_xpaths", [config["quality_options_xpath"]]):
                    try:
                        quality_options = WebDriverWait(driver, 8).until(
                            EC.presence_of_all_elements_located((By.XPATH, xpath))
                        )
                        if quality_options:
                            if len(quality_options) == 1:
                                # Only one quality option, select it silently and break (no errors/warnings)
                                quality_to_select = quality_options[0]
                                driver.execute_script("arguments[0].scrollIntoView(true);", quality_to_select)
                                try:
                                    quality_to_select.click()
                                except Exception:
                                    driver.execute_script("arguments[0].click();", quality_to_select)
                                quality_success = True
                                break  # Do not try any other resolutions or print errors
                            else:
                                available_qualities = [q.text for q in quality_options]
                                logging.info(f"Available quality options (xpath {xpath}): {available_qualities}")
                                quality_to_select = quality_options[-1]
                                logging.info(f"Multiple quality options available, selecting the lowest: {quality_to_select.text}")
                                driver.execute_script("arguments[0].scrollIntoView(true);", quality_to_select)
                                try:
                                    quality_to_select.click()
                                    logging.info(f"Selected quality: {quality_to_select.text} (attempt {attempt+1})")
                                    quality_success = True
                                    break
                                except StaleElementReferenceException:
                                    logging.warning("StaleElementReferenceException: re-finding quality options and retrying click")
                                    continue  # Try next xpath or re-find
                                except Exception:
                                    driver.execute_script("arguments[0].click();", quality_to_select)
                                    logging.info(f"JavaScript click successful for quality selection: {quality_to_select.text} (attempt {attempt+1})")
                                    quality_success = True
                                    break
                        else:
                            logging.info(f"No quality options found for xpath: {xpath}")
                    except Exception as e:
                        logging.info(f"Exception for xpath {xpath}: {e}")
                    if quality_success:
                        break
                if quality_success:
                    time.sleep(1)
                    break
                else:
                    raise Exception("No quality options found with any xpath")
            except Exception as e:
                logging.warning(f"Could not set quality (attempt {attempt+1}): {str(e)}")
                time.sleep(2)
        if not quality_success:
            # Log page source for debugging
            try:
                with open('quality_debug.html', 'w', encoding='utf-8') as f:
                    f.write(driver.page_source)
                logging.info("Saved page source to quality_debug.html for troubleshooting.")
            except Exception as log_e:
                logging.error(f"Failed to save page source: {log_e}")
            print(f"\033[93mWarning: Could not set quality after retries.\033[0m")
        # Switch back to default content
        driver.switch_to.default_content()
        return driver.current_window_handle
    except Exception as e:
        logging.error(f"create_viewer (proxy: {proxy}): {str(e)}")
        proxy_failures[proxy] = proxy_failures.get(proxy, 0) + 1
        try:
            driver.switch_to.default_content()
            driver.close()
        except Exception:
            pass
        return None

def setup_driver(twitch_name, viewer_count, config, headless_mode):
    # Use undetected_chromedriver (uc.Chrome) for all browser automation
    chrome_options = uc.ChromeOptions()
    # Always use native Twitch player size (1280x720)
    window_width, window_height = 1280, 720
    if headless_mode:
        chrome_options.add_argument('--headless')
    chrome_options.add_argument(f'--window-size={window_width},{window_height}')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-logging')
    chrome_options.add_argument('--lang=en')
    chrome_options.add_argument('--log-level=3')
    chrome_options.add_argument('--disable-extensions')
    chrome_options.add_argument('--mute-audio')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument(f'--user-agent={random.choice(config["user_agents"])}')

    driver = uc.Chrome(options=chrome_options, use_subprocess=True)
    driver.set_window_size(window_width, window_height)
    twitch_url = f"https://www.twitch.tv/{twitch_name}"
    viewer_tabs = []
    proxy_failures = {}
    failure_threshold = config["failure_threshold"]

    valid_proxies = [proxy for proxy in config["proxies"] if validate_proxy(proxy)]
    if not valid_proxies:
        print("\033[91mNo valid proxies available. Exiting.\033[0m")
        driver.quit()
        return

    # --- Robust: Always maintain viewer_count viewers, reconnecting as needed ---
    while len(viewer_tabs) < viewer_count and valid_proxies and not shutdown_flag.is_set():
        proxy = min(valid_proxies, key=lambda p: proxy_failures.get(p, 0))
        if proxy_failures.get(proxy, 0) >= failure_threshold:
            valid_proxies.remove(proxy)
            logging.warning(f"Proxy {proxy} removed due to excessive failures")
            print(f"\033[91mProxy {proxy} removed after {failure_threshold} failures.\033[0m")
            continue
        tab = create_viewer(driver, proxy, twitch_url, proxy_failures)
        if tab:
            viewer_tabs.append(tab)
            print(f"\033[92mA viewer created {len(viewer_tabs)}/{viewer_count}.\033[0m")
        else:
            print(f"\033[91mFailed to create viewer with proxy {proxy}.\033[0m")
        time.sleep(1)

    print("\033[93mAll viewers created, press 'Ctrl + C' to exit when done.\033[0m")

    # --- Sustain all viewers and always keep viewer_count active ---
    while not shutdown_flag.is_set():
        # Check if channel is live
        if not is_channel_live(twitch_name):
            print(f"\033[93mChannel {twitch_name} is offline. Closing all viewers and waiting...\033[0m")
            # Close all viewer tabs
            for tab in viewer_tabs:
                try:
                    driver.switch_to.window(tab)
                    driver.close()
                except Exception:
                    pass
            viewer_tabs.clear()
            # Wait before checking again
            time.sleep(60)
            continue

        # Reconnect any lost viewers to always maintain viewer_count
        while len(viewer_tabs) < viewer_count and valid_proxies:
            proxy = min(valid_proxies, key=lambda p: proxy_failures.get(p, 0))
            if proxy_failures.get(proxy, 0) >= failure_threshold:
                valid_proxies.remove(proxy)
                logging.warning(f"Proxy {proxy} removed due to excessive failures (sustain)")
                continue
            tab = create_viewer(driver, proxy, twitch_url, proxy_failures)
            if tab:
                viewer_tabs.append(tab)
                # Silently reconnect lost viewers (no print)
            time.sleep(1)

        for tab in viewer_tabs[:]:
            try:
                driver.switch_to.window(tab)
                try:
                    video = find_element_in_iframes(driver, config["video_player_xpath"], config["video_timeout"])
                    if not is_interactable(video):
                        raise Exception("Video player not interactable")
                except Exception:
                    # Silently reconnect lost viewers
                    if not valid_proxies:
                        viewer_tabs.remove(tab)
                        continue
                    proxy = min(valid_proxies, key=lambda p: proxy_failures.get(p, 0))
                    new_tab = create_viewer(driver, proxy, twitch_url, proxy_failures)
                    if new_tab:
                        viewer_tabs.remove(tab)
                        viewer_tabs.append(new_tab)
                    else:
                        viewer_tabs.remove(tab)
            except NoSuchWindowException:
                print(f"\033[91mTab {tab} no longer exists.\033[0m")
                viewer_tabs.remove(tab)
            except Exception as e:
                logging.error(f"sustain viewers: {str(e)}")
        # Perform random actions
        for tab in viewer_tabs:
            try:
                driver.switch_to.window(tab)
                video = find_element_in_iframes(driver, config["video_player_xpath"], config["video_timeout"])
                ActionChains(driver).move_to_element(video).perform()
                if random.random() < 0.3:
                    ActionChains(driver).move_by_offset(random.randint(-10,10), random.randint(-10,10)).perform()
                if random.random() < 0.2:
                    driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ARROW_DOWN)
                driver.switch_to.default_content()
            except Exception:
                pass
        time.sleep(config["activity_interval"])
    try:
        driver.quit()
    except Exception as e:
        logging.error(f"Shutdown error: {str(e)}")

    if len(viewer_tabs) < viewer_count:
        print(f"\033[91mOnly created {len(viewer_tabs)}/{viewer_count} viewers. No valid proxies remaining or shutdown requested.\033[0m")
        if viewer_tabs:
            print("\033[93mProceeding with available viewers, press 'Ctrl + C' to exit when done.\033[0m")
        else:
            driver.quit()
            return

    print("\033[93mAll viewers created, press 'Ctrl + C' to exit when done.\033[0m")

    while not shutdown_flag.is_set():
        for tab in viewer_tabs[:]:
            try:
                driver.switch_to.window(tab)
                try:
                    video = find_element_in_iframes(driver, config["video_player_xpath"], config["video_timeout"])
                    if not is_interactable(video):
                        raise Exception("Video player not interactable")
                except Exception:
                    print(f"\033[93mViewer in tab {tab} lost connection, attempting to reconnect...\033[0m")
                    if not valid_proxies:
                        print(f"\033[91mNo valid proxies available for reconnect.\033[0m")
                        viewer_tabs.remove(tab)
                        continue
                    proxy = min(valid_proxies, key=lambda p: proxy_failures.get(p, 0))
                    new_tab = create_viewer(driver, proxy, twitch_url, proxy_failures)
                    if new_tab:
                        viewer_tabs.remove(tab)
                        viewer_tabs.append(new_tab)
                        print(f"\033[92mViewer reconnected in new tab {new_tab}.\033[0m")
                    else:
                        print(f"\033[91mFailed to reconnect viewer in tab {tab}.\033[0m")
                        viewer_tabs.remove(tab)
            except NoSuchWindowException:
                print(f"\033[91mTab {tab} no longer exists.\033[0m")
                viewer_tabs.remove(tab)
            except Exception as e:
                logging.error(f"sustain viewers: {str(e)}")
        # Perform random actions
        for tab in viewer_tabs:
            try:
                driver.switch_to.window(tab)
                video = find_element_in_iframes(driver, config["video_player_xpath"], config["video_timeout"])
                ActionChains(driver).move_to_element(video).perform()
                if random.random() < 0.3:
                    ActionChains(driver).move_by_offset(random.randint(-10,10), random.randint(-10,10)).perform()
                if random.random() < 0.2:
                    driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ARROW_DOWN)
                driver.switch_to.default_content()
            except Exception:
                pass
        time.sleep(config["activity_interval"])
    try:
        driver.quit()
    except Exception as e:
        logging.error(f"Shutdown error: {str(e)}")

def validate_twitch_name(twitch_name):
    if not twitch_name or not re.match(r'^[a-zA-Z0-9_]{4,25}$', twitch_name):
        return False, "Invalid Twitch username"
    return True, ""

def validate_proxy(proxy):
    """Check if a proxy is accessible."""
    try:
        response = requests.get(proxy, timeout=5)
        if response.status_code == 200:
            logging.info(f"Proxy {proxy} is accessible")
            return True
        else:
            logging.warning(f"Proxy {proxy} returned status code {response.status_code}")
            return False
    except Exception as e:
        logging.error(f"Proxy {proxy} failed validation: {str(e)}")
        return False

def main():
    if not check_environment():
        sys.exit(1)
    os.system("cls" if os.name == "nt" else "clear")
    print("\033[93mWARNING: Viewbots may violate Twitch ToS (https://www.twitch.tv/p/en/legal/terms-of-service/). Use responsibly.\033[0m")
    # Read headless mode from environment variable, default True
    headless_env = os.getenv("HEADLESS_MODE", "true").lower()
    headless_mode = headless_env in ("1", "true", "yes", "y")
    twitch_name = "eradicationism"
    valid, error = validate_twitch_name(twitch_name)
    if not valid:
        print(f"\033[91m{error}\033[0m")
        return
    # Read viewer count from environment variable, default 15
    try:
        viewer_count = int(os.getenv("VIEWER_COUNT", "15"))
        if viewer_count <= 0:
            raise ValueError("Viewer count must be positive")
    except ValueError as e:
        print(f"\033[91mInvalid viewer count: {str(e)}\033[0m")
        return
    print(f"\033[93mCreating {viewer_count} viewers in {'headless' if headless_mode else 'headed'} mode...\033[0m")
    setup_driver(twitch_name, viewer_count, config, headless_mode)

if __name__ == "__main__":
    main()
