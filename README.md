A modular Python application for monitoring electricity meters via the iBilik API.

## Quick Setup

### 1. Get Your Merchant Token

**Super Simple Method:**
1. Copy this bookmarklet code:
   ```js
   javascript:(function(){try{var currentDomain=window.location.hostname;var currentURL=window.location.href;if(currentDomain!=='apu.ibilik.com'){alert('ERROR: Wrong domain!\n\nPlease run this bookmarklet on https://apu.ibilik.com (any page like /en/home) after logging in.\n\nCurrent page: '+currentURL);return;}if(!window.localStorage){alert('ERROR: localStorage not available.\n\nThis might be due to:\n• Private browsing mode\n• Browser security settings\n• Content Security Policy\n\nTry using regular browsing mode on https://apu.ibilik.com');return;}if(window.self!==window.top){alert('ERROR: Cannot run in iframe.\n\nPlease open https://apu.ibilik.com directly in a new tab, not in an embedded frame.');return;}var token=localStorage.getItem('MyToken');if(token){var popup=window.open('','ibilik_token','width=750,height=350');popup.document.write('<html><head><title>iBilik Merchant Token</title><style>body{font-family:Arial,sans-serif;padding:20px;background:#f0f8ff;color:#333;max-width:650px;margin:0 auto;}.header{background:#007cba;color:white;padding:15px;border-radius:8px;margin-bottom:20px;text-align:center;}.token-box{background:white;border:2px solid #007cba;border-radius:8px;padding:20px;margin:20px 0;box-shadow:0 2px 10px rgba(0,0,0,0.1);}.token{font-family:monospace;font-size:13px;background:#f8f9fa;padding:15px;border-radius:5px;border:1px solid #dee2e6;word-break:break-all;margin:10px 0;color:#495057;max-height:100px;overflow-y:auto;}.copy-btn{background:#28a745;color:white;border:none;padding:12px 24px;border-radius:5px;cursor:pointer;font-size:16px;margin:10px 5px 0 0;}.copy-btn:hover{background:#218838;}.close-btn{background:#6c757d;color:white;border:none;padding:12px 24px;border-radius:5px;cursor:pointer;font-size:16px;margin:10px 5px 0 0;}.close-btn:hover{background:#5a6268;}</style></head><body><div class="header"><h2>iBilik Merchant Token Extracted</h2></div><div class="token-box"><p><strong>SUCCESS!</strong> Your merchant token was found on '+currentDomain+'.</p><p><strong>Token:</strong></p><div class="token" id="tokenDisplay">'+token+'</div><button class="copy-btn" onclick="copyToken()">Copy Token</button><button class="close-btn" onclick="closePopup()">Close</button></div><div style="font-size:12px;color:#666;margin-top:20px;text-align:center;">Paste this token into your <code>config.json</code> file under <code>merchant_token</code></div><script>function copyToken(){var tokenText=document.getElementById("tokenDisplay").textContent;navigator.clipboard.writeText(tokenText).then(()=>{alert("Token copied to clipboard!\n\nNow paste it into your config.json file.");}).catch(()=>{var textArea=document.createElement("textarea");textArea.value=tokenText;document.body.appendChild(textArea);textArea.select();document.execCommand("copy");document.body.removeChild(textArea);alert("Token copied to clipboard!\n\nNow paste it into your config.json file.");});}function closePopup(){window.close();}</script></body></html>');popup.focus();}else{alert('ERROR: No merchant token found.\n\nPlease make sure you are logged into https://apu.ibilik.com and try again.\n\nIf you just logged in, try refreshing the page first.\n\nCurrent page: '+currentURL);}}catch(e){alert('ERROR: Error accessing token:\n\n'+e.message+'\n\nPossible causes:\n• Browser security restrictions\n• Private browsing mode\n• Content Security Policy\n• Running in an iframe\n\nTry:\n1. Using regular browsing mode\n2. Opening https://apu.ibilik.com in a new tab\n3. Disabling browser extensions temporarily');}})();
   ```
2. Add it as a bookmark in your browser
3. Go to https://apu.ibilik.com/en/home and login to your account
4. Click the bookmarklet you just added
5. A popup will appear with your token - click "Copy Token"
6. Paste the token into your `config.json` file

### 2. Configure the Application

Edit `config.json` and replace the `merchant_token` value:

```json
{
  "api": {
    "merchant_token": "YOUR_TOKEN_HERE"
  }
}
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the Monitor

```bash
python main.py
```

## Usage

1. Run `python main.py`
2. Select meters to monitor (single meter or all)
3. View real-time data in the console
4. Data is automatically saved to `data/meter_monitoring.db`

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.