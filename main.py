import feedparser
import configparser
import os
import datetime
import requests
import google.generativeai as genai
from jinja2 import Template
from bs4 import BeautifulSoup
import re
from fake_useragent import UserAgent

# --- 基础配置读取 ---
config = configparser.ConfigParser()
config.read('config.ini')
secs = config.sections()

# 从 GitHub Secrets 获取变量
# 注意：现在这里直接放你的 Gemini API Key
GEMINI_API_KEY = os.environ.get('OPENAI_API_KEY') 
WECHAT_WEBHOOK = os.environ.get('WECHAT_WEBHOOK')
U_NAME = os.environ.get('U_NAME')

BASE = config.get('cfg', 'BASE', fallback='docs/').strip('"')
keyword_length = int(config.get('cfg', 'keyword_length', fallback='5'))
summary_length = int(config.get('cfg', 'summary_length', fallback='800'))
language = config.get('cfg', 'language', fallback='zh')

# --- 功能函数 ---

def send_wechat(title, link, summary):
    """把好消息发到企业微信"""
    if not WECHAT_WEBHOOK:
        return
    clean_summary = summary.replace('<br>', '\n').replace('总结:', '📌 设计总监简报:')
    content = f"🚀 **发现新动态！**\n\n**标题**: {title}\n**原文**: {link}\n\n{clean_summary}"
    try:
        requests.post(WECHAT_WEBHOOK, json={"msgtype": "markdown", "markdown": {"content": content}}, timeout=10)
    except: pass

def gpt_summary(text):
    """调用 Gemini 官方大脑进行总结"""
    if not GEMINI_API_KEY:
        return "未配置 API Key"
    
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        # 使用最适合小白、免费额度大的 flash 模型
        model = genai.GenerativeModel('gemini-1.5-flash')
