import os
import re
import urllib.request
import json
import subprocess
import sys

INSTALL_DIR = r'C:\bale_course_survey_final'

# 1. Fix config.py to use dynamic URL from environment variable
config_path = os.path.join(INSTALL_DIR, 'src', 'config.py')
with open(config_path, 'r', encoding='utf-8') as f:
    content = f.read()

content = re.sub(
    r'WEB_APP_URL = "https://[a-z0-9-]+\.trycloudflare\.com"',
    'WEB_APP_URL = os.environ.get("WEB_APP_URL", "")',
    content
)
with open(config_path, 'w', encoding='utf-8') as f:
    f.write(content)
print('OK: config.py fixed to use dynamic URL')

# 2. Remove admin hint from login.html
login_path = os.path.join(INSTALL_DIR, 'templates', 'admin', 'login.html')
with open(login_path, 'r', encoding='utf-8') as f:
    content = f.read()

content = re.sub(
    r'<div class="login-hint">.*?</div>',
    '<!-- Admin hint removed for production -->',
    content,
    flags=re.DOTALL
)
with open(login_path, 'w', encoding='utf-8') as f:
    f.write(content)
print('OK: Admin hint removed from login.html')

# 3. Update Bot Menu Button with the correct HTTPS URL
try:
    # Get the URL from the NSSM service environment variable
    result = subprocess.run(['nssm', 'get', 'SurveyBot', 'AppEnvironmentExtra'], capture_output=True, text=True)
    env_str = result.stdout
    match = re.search(r'WEB_APP_URL=(https://[a-z0-9-]+\.trycloudflare\.com)', env_str)
    web_app_url = match.group(1) if match else ""
    
    if web_app_url:
        sys.path.insert(0, INSTALL_DIR)
        from src.config import BALE_BOT_TOKEN
        
        url = f'https://tapi.bale.ai/bot{BALE_BOT_TOKEN}/setChatMenuButton'
        data = {
            'menu_button': {
                'type': 'web_app',
                'text': '📱 ورود به مینی‌اپ',
                'web_app': {'url': web_app_url}
            }
        }
        req = urllib.request.Request(url, data=json.dumps(data).encode(), headers={'Content-Type': 'application/json'})
        resp = urllib.request.urlopen(req, timeout=10)
        print(f'OK: Bot Menu Updated with URL: {web_app_url}')
    else:
        print('WARNING: Could not find WEB_APP_URL in NSSM service')
except Exception as e:
    print(f'Error updating bot menu: {e}')
