from flask import Flask, request, jsonify
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import base64
from io import BytesIO
import requests

app = Flask(__name__)

def create_driver():
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    driver = webdriver.Chrome(options=options)
    return driver

@app.route('/scrape', methods=['POST'])
def scrape():
    data = request.json
    license_plate = data.get('license_plate')

    if not license_plate:
        return jsonify({"error": "license_plate is required"}), 400

    driver = create_driver()
    try:
        driver.get('https://www.service-public.fr/particuliers/vosdroits/demarches-et-outils/interrogation-fourriere')
        WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.ID, "captchaImage")))

        immatriculation_input = driver.find_element(By.ID, "immatriculation")
        immatriculation_input.send_keys(license_plate)

        time.sleep(2)

        captcha_image = driver.find_element(By.ID, "captchaImage")
        captcha_base64 = captcha_image.get_attribute("src")
        image_data = base64.b64decode(captcha_base64.split(",")[1])

        url = "https://api.solvecaptcha.com/in.php"
        api_key = "6b8eacf216d3f99e789a2a6336597d7c"
        files = {'file': ('captcha.png', BytesIO(image_data), 'image/png')}
        data = {'method': 'post', 'key': api_key}

        response = requests.post(url, data=data, files=files)

        if response.text.startswith("OK|"):
            captcha_id = response.text.split('|')[1]

            for _ in range(10):
                time.sleep(5)
                solution_url = f"http://api.solvecaptcha.com/res.php?key={api_key}&action=get&id={captcha_id}&json=1"
                solution_response = requests.get(solution_url)
                solution_result = solution_response.json()
                if solution_result.get("request") != "CAPCHA_NOT_READY":
                    solution = solution_result.get("request")
                    break
            else:
                return jsonify({"error": "Captcha non résolu à temps"}), 408

            captcha_input = driver.find_element(By.ID, "captchaFormulaireExtInput")
            captcha_input.send_keys(solution)
            submit_button = driver.find_element(By.ID, "fourriere-submit")
            submit_button.click()
            time.sleep(10)

            try:
                WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, "#main > div > article > div.fr-my-4w")))
                success_message = success_element.text

                # Détection si le véhicule est en fourrière
                en_fouriere = "Le véhicule est actuellement en fourrière" in success_message

                if en_fouriere:
                    # Extraire adresse et téléphone
                    lines = success_message.split('\n')
                    adresse = ""
                    telephone = ""

                    for idx, line in enumerate(lines):
                        if "immatriculé " in line:
                            # On prend les 2 lignes suivantes comme adresse
                            adresse = lines[idx + 1] + " " + lines[idx + 2]  + " " + lines[idx + 3]
                        if "+" in line and line.strip().startswith("+"):
                            telephone = line.strip()

                    return jsonify({
                        "license_plate": license_plate,
                        "en_fouriere": True,
                        "adresse": adresse.strip(),
                        "telephone": telephone.strip()
                    })
                else:
                    return jsonify({
                        "license_plate": license_plate,
                        "en_fouriere": False
                    })

            except Exception as e:
                return jsonify({"error": f"Erreur lors de la récupération des informations: {str(e)}"}), 500
        else:
            return jsonify({"error": f"Erreur SolveCaptcha: {response.text}"}), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        driver.quit()

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)
