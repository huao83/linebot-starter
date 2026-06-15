import os
import json
import datetime
import traceback
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from google import genai
from google.genai import types # 👈 幫你新增了這個，用來設定 System Prompt
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

app = Flask(__name__)

LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
SPREADSHEET_ID = os.environ.get('SPREADSHEET_ID')
GOOGLE_CREDENTIALS = os.environ.get('GOOGLE_CREDENTIALS')

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
client = genai.Client(api_key=GEMINI_API_KEY)

# ===================================================
# ★ 你的 AI 教學助理靈魂：考古題分析 System Prompt ★
# ===================================================
SYSTEM_INSTRUCTION = """你是一位專業且充滿熱忱的國小數學「考古題分析老師」，特別擅長解構幾何迷思（如周長與面積的關係）。
當學生傳送任何考試題目給你時，請你務必嚴格按照以下四個標題結構來回覆，展現清晰的邏輯架構：

1. 【核心考點】：用一句話指出這題主要測驗什麼單元或觀念？
2. 【題目詳解】：正確答案是什麼？請提供詳細的邏輯推導與解題步驟。
3. 【陷阱與迷思】：這題的陷阱在哪裡？學生最容易犯的錯誤觀念是什麼？（例如：誤以為周長拉長，面積就會變大等直覺迷思）。
4. 【延伸複習建議】：針對這個考點，建議學生接下來可以去複習哪些相關重點？

請用語氣親切、有邏輯且鼓勵的方式回答。如果學生傳送的不是題目，請溫柔地提醒他：「請傳送你想詢問的考古題或選擇題喔！」
"""

def get_sheets_service():
    try:
        creds_info = json.loads(GOOGLE_CREDENTIALS)
        creds = Credentials.from_service_account_info(
            creds_info,
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
        service = build('sheets', 'v4', credentials=creds)
        return service
    except Exception as e:
        print(f'Sheets 連線錯誤: {e}')
        traceback.print_exc()
        return None

def log_to_sheets(user_msg, bot_reply):
    try:
        service = get_sheets_service()
        if not service:
            return
        now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        values = [[now, user_msg, bot_reply]]
        service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID,
            range='工作表1!A:C',
            valueInputOption='RAW',
            body={'values': values}
        ).execute()
        print(f'記錄成功: {now}')
    except Exception as e:
        print(f'記錄失敗: {e}')
        traceback.print_exc()

@app.route("/webhook", methods=['POST'])
def webhook():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_msg = event.message.text
    try:
        # 👈 這裡幫你把 System Prompt 裝進去了！
        response = client.models.generate_content(
            model='gemini-1.5-flash',
            contents=user_msg,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                temperature=0.7 # 稍微降低一點溫度，讓解題邏輯更穩定
            )
        )
        reply = response.text
    except Exception as e:
        print(f'Gemini error: {e}')
        reply = f'老師的腦袋稍微卡住了，請確認題目完整性後再試一次喔！錯誤代碼：{str(e)}'
        
    log_to_sheets(user_msg, reply)
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply)
    )

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)
