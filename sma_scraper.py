# pylint: disable=anomalous-backslash-in-string

import json
import logging
import os
import re
import sys
import time

import paho.mqtt.client as mqtt
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

#Konfigurationsvariablen
BROKER_ADDRESS = os.environ.get("BROKER_ADDRESS", "localhost")
BROKER_PORT = int(os.environ.get("BROKER_PORT", 1883))
TOPIC_PREFIX = os.environ.get("TOPIC_PREFIX", "awtrixlight/custom/")
MQTT_PASSWORD = os.environ.get("MQTTPASSWORD")
MQTT_USERNAME = os.environ.get("MQTTUSERNAME")
USERNAME = os.environ.get("USERNAME")
PASSWORD = os.environ.get("PASSWORD")
ToWatt = 1000

LOGIN_URL = "https://www.sunnyportal.com/Templates/Start.aspx?ReturnUrl=%2f"


start_ascii = r"""
  _                           _    _____                                  _      _____   __  __               __          __         _                                                       
 | |                         | |  / ____|                                (_)    / ____| |  \/  |     /\       \ \        / /        | |                                                      
 | |        ___    _ __    __| | | |  __   _   _    ___   _ __    _ __    _    | (___   | \  / |    /  \       \ \  /\  / /    ___  | |__    ___    ___   _ __    __ _   _ __     ___   _ __ 
 | |       / _ \  | '__|  / _` | | | |_ | | | | |  / _ \ | '_ \  | '_ \  | |    \___ \  | |\/| |   / /\ \       \ \/  \/ /    / _ \ | '_ \  / __|  / __| | '__|  / _` | | '_ \   / _ \ | '__|
 | |____  | (_) | | |    | (_| | | |__| | | |_| | |  __/ | | | | | | | | | |    ____) | | |  | |  / ____ \       \  /\  /    |  __/ | |_) | \__ \ | (__  | |    | (_| | | |_) | |  __/ | |   
 |______|  \___/  |_|     \__,_|  \_____|  \__,_|  \___| |_| |_| |_| |_| |_|   |_____/  |_|  |_| /_/    \_\       \/  \/      \___| |_.__/  |___/  \___| |_|     \__,_| | .__/   \___| |_|   
                                                                                                                                                                        | |                  
                                                                                                                                                                        |_|
"""

# Config Logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# Selenium-Optionen
CHROME_OPTIONS = Options()
CHROME_OPTIONS.add_argument("--headless")
CHROME_OPTIONS.add_argument("--no-sandbox")
CHROME_OPTIONS.add_argument("--disable-notifications")
CHROME_OPTIONS.add_argument(
    "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.6045.159 Safari/537.36"
)


def create_mqtt_client():
    client = mqtt.Client()
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    client.connect(BROKER_ADDRESS, BROKER_PORT)
    client.on_connect = on_connect
    return client


def on_connect(client, userdata, flags, rc):
    logging.info("Connected with Result Code " + str(rc))


def get_battery_icon(batterie_stand):
    match batterie_stand:
        # full battery
        case 100:
            batterie_stand_icon = "13735"

        # battery between 80 and 100
        case n if n >= 80:
            batterie_stand_icon = "13732"

        # battery between 50 and 80
        case n if n >= 50:
            batterie_stand_icon = "12124"

        # battery between 30 and 50
        case n if n >= 10:
            batterie_stand_icon = "13733"
        # battery between 10 and 30
        case n if n <= 10:
            batterie_stand_icon = "13734"
        # battery between 0 and 10
        case 0:
            batterie_stand_icon = "20630"

    return batterie_stand_icon


def get_consumption_icon(used_power):
    match used_power:
        case n if n >= 3000:
            used_power_icon = "54673"

        case n if n >= 1500:
            used_power_icon = "54672"

        case n if n >= 500:
            used_power_icon = "54708"

        case n if n >= 0:
            used_power_icon = "54671"

    return used_power_icon


def send_custom_message(use_case, value):
    try:
        client = create_mqtt_client()
        client.loop_start()

        topic = TOPIC_PREFIX + get_topic_for_use_case(use_case)

        match use_case:
            case "verbrauch":
                numeric_value = int(value.rstrip("W"))
                numeric_value = get_consumption_icon(numeric_value)
                zustand = {f"text": value, "icon": numeric_value}

            case "speicherstand":
                numeric_value = int(value.rstrip("%"))
                zustand = {f"text": value, "icon": get_battery_icon(numeric_value)}

            case _:
                zustand = {f"text": value, "icon": get_icon_for_use_case(use_case)}

        json_string = json.dumps(zustand)

        logging.info(f"Sende an {topic}: {json_string}")
        client.publish(topic, json_string)

        time.sleep(1)
    except Exception as e:
        logging.error(f"Error while sending Message {e}")
    finally:
        client.disconnect()


def get_icon_for_use_case(use_case):
    cases = {
        "erzeugung": "54089",
        "ladestaerke": "27283",
        "endladestärke": "21586",
        "grid": "52462",
    }
    return cases.get(use_case, None)


def get_topic_for_use_case(use_case):
    cases = {
        "erzeugung": "1",
        "verbrauch": "2",
        "ladestaerke": "3",
        "endladestärke": "3",
        "grid": "4",
        "speicherstand": "5",
    }
    return cases.get(use_case, "0")  # Standardwert "0" für ungültige Fälle


def extract_data(text):
    pattern = re.compile(r"([^\n]+)\n([\d.]+)\s*([^\n]+)")
    matches = pattern.findall(text)
    return [
        (name.strip(), value.strip(), unit.strip()) for name, value, unit in matches
    ]


def convert_to_watt_and_integer(value, conversion_factor):
    try:
        return int(float(value) * conversion_factor)
    except ValueError:
        return value


def extract_battery_data(container_text):
    data_list = extract_data(container_text)
    pv_gen = (
        consumption
    ) = grid_pull = battery_charge = battery_status = battery_discharge = None

    for name, value, unit in data_list:
        match name:
            case "PV power generation":
                pv_gen = convert_to_watt_and_integer(value, ToWatt)
            case "Total consumption":
                consumption = convert_to_watt_and_integer(value, ToWatt)
            case "Purchased electricity" if grid_pull is None:
                grid_pull = convert_to_watt_and_integer(value, ToWatt)
            case "Grid feed-in" if grid_pull is None:
                grid_pull = convert_to_watt_and_integer(value, ToWatt)
            case "Battery discharging":
                battery_discharge = convert_to_watt_and_integer(value, ToWatt)
            case "Battery charging":
                battery_charge = convert_to_watt_and_integer(value, ToWatt)
            case "Battery state of charge":
                battery_status = value

    return (
        pv_gen,
        consumption,
        grid_pull,
        battery_charge,
        battery_discharge,
        battery_status,
    )


def initialize_selenium_driver_and_login():
    global driver
    driver = webdriver.Chrome(options=CHROME_OPTIONS)
    logging.info("Webdriver Initialized")
    driver.get(LOGIN_URL)
    time.sleep(2)

    # If Cookie Banner Exists reject cookies
    wait = WebDriverWait(driver, 2)
    reject_button = wait.until(
        EC.element_to_be_clickable((By.ID, "onetrust-reject-all-handler"))
    )
    reject_button.click()

    username_input = driver.find_element(By.ID, "txtUserName")
    password_input = driver.find_element(By.ID, "txtPassword")
    username_input.send_keys(USERNAME)
    password_input.send_keys(PASSWORD)

    login_button = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable(
            (By.ID, "ctl00_ContentPlaceHolder1_Logincontrol1_LoginBtn")
        )
    )
    login_button.click()

    time.sleep(3)


def process_battery_data():
    extrating_starttime = time.time()
    battery_container = driver.find_element(By.CLASS_NAME, "batteryStatus-container")
    (
        pv_gen,
        consumption,
        grid_pull,
        battery_charge,
        battery_discharge,
        battery_status,
    ) = extract_battery_data(battery_container.text)

    send_custom_message("erzeugung", f"{pv_gen} W")
    send_custom_message("verbrauch", f"{consumption} W")

    if battery_discharge is None:
        send_custom_message("ladestaerke", f"{battery_charge} W")

    elif battery_charge is None:
        send_custom_message("endladestärke", f"{battery_discharge} W")

    send_custom_message("grid", f"{grid_pull} W")
    send_custom_message("speicherstand", f"{battery_status} %")

    time.sleep(27.5 - ((time.time() - extrating_starttime) % 27.5))


if __name__ == "__main__":
    time.sleep(2)
    print(start_ascii)

    while True:
        time.sleep(2)
        starttime = time.time()
        runtime = 0
        initialize_selenium_driver_and_login()
        while runtime < 60 * 60:
            try:
                runtime = time.time() - starttime
                process_battery_data()
                time.sleep(27.5)
            except KeyboardInterrupt:
                break
            except Exception as e:
                logging.error(f"Error at main(): {e}")
        
        driver.delete_all_cookies()
        driver.close()
        driver.quit()
        logging.info("Iteration abgeschlossen")
