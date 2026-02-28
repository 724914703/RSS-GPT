import feedparser
import configparser
import os
import requests
import google.generativeai as genai
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

# --- 1. 配置读取 ---
config = configparser.ConfigParser()
config.read('config.ini')
secs = config.sections()

GEMINI_API_KEY = os.environ.get('OPENAI_API_KEY') 
WECHAT_WEBHOOK = os.environ.get('WECHAT_WEBHOOK')
BASE = config.get('cfg', 'BASE', fallback='docs/').strip('"')

# --- 2. 功能函数 ---

def send_wechat(title, link, summary):
    if not WECHAT_WEBHOOK: return
    clean_summary = summary.replace('<br>', '\n').replace('总结:', '📌 AI 简报:')
    content = f"🚀 **全网新发现**\n\n**标题**: {title}\n**原文**: {link}\n\n{clean_summary}"
    try:
        requests.post(WECHAT_WEBHOOK, json={"msgtype": "markdown", "markdown": {"content": content}}, timeout=10)
    except: pass

def gpt_summary(text):
    if not GEMINI_API_KEY: return "未配置 API Key"
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = f"你是一位资深设计总监，请用中文总结以下内容的AI工具突破、工作流和建议，300字内，以'总结:'开头：\n\n{text}"
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"总结失败: {str(e)}"

def clean_html(html):
    soup = BeautifulSoup(html, "html.parser")
    for s in soup(["script", "style", "img", "a", "video"]): s.decompose()
    return soup.get_text()

def process_feed(sec):
    name = config.get(sec, 'name').strip('"')
    url_list = config.get(sec, 'url').strip('"').split(',')
    for url in url_list:
        try:
            ua = UserAgent()
            resp = requests.get(url, headers={'User-Agent': ua.random}, timeout=30)
            feed = feedparser.parse(resp.text)
            if feed.entries:
                entry = feed.entries[0]
                content = clean_html(getattr(entry, 'summary', getattr(entry, 'description', entry.title)))
                summary_text = gpt_summary(content)
                if "总结失败" not in summary_text:
                    send_wechat(entry.title, entry.link, summary_text)
                    print(f"✅ 发送成功: {entry.title}")
        except Exception as e:
            print(f"❌ 出错: {e}")

if __name__ == "__main__":
    if not os.path.exists(BASE): os.mkdir(BASE)
    for section in secs:
        if section.startswith('source'): process_feed(section)
