import feedparser
import configparser
import os
import httpx
from openai import OpenAI
from jinja2 import Template
from bs4 import BeautifulSoup
import re
import datetime
import requests
from fake_useragent import UserAgent

def get_cfg(sec, name, default=None):
    value=config.get(sec, name, fallback=default)
    if value:
        return value.strip('"')

config = configparser.ConfigParser()
config.read('config.ini')
secs = config.sections()
max_entries = 1000

OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
U_NAME = os.environ.get('U_NAME')
OPENAI_PROXY = os.environ.get('OPENAI_PROXY')
OPENAI_BASE_URL = os.environ.get('OPENAI_BASE_URL', 'https://api.openai.com/v1')
custom_model = os.environ.get('CUSTOM_MODEL')
# 获取企业微信 Webhook
WECHAT_WEBHOOK = os.environ.get('WECHAT_WEBHOOK')

deployment_url = f'https://{U_NAME}.github.io/RSS-GPT/'
BASE = get_cfg('cfg', 'BASE')
keyword_length = int(get_cfg('cfg', 'keyword_length'))
summary_length = int(get_cfg('cfg', 'summary_length'))
language = get_cfg('cfg', 'language')

def send_wechat_message(title, link, summary):
    """新增：发送消息到企业微信机器人"""
    if not WECHAT_WEBHOOK:
        return
    
    # 清理一下总结中的 HTML 换行符，方便微信展示
    clean_summary = summary.replace('<br>', '\n').replace('总结:', '📌 深度总结:')
    
    content = f"🎨 **设计总监 AI 简报**\n\n" \
              f"🔗 **标题**: {title}\n" \
              f"🌐 **原文**: {link}\n" \
              f"{clean_summary}"
    
    data = {
        "msgtype": "markdown",
        "markdown": {"content": content}
    }
    try:
        requests.post(WECHAT_WEBHOOK, json=data, timeout=10)
    except Exception as e:
        print(f"推送微信失败: {e}")

def fetch_feed(url, log_file):
    feed = None
    headers = {}
    try:
        ua = UserAgent()
        headers['User-Agent'] = ua.random.strip()
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code == 200:
            feed = feedparser.parse(response.text)
            return {'feed': feed, 'status': 'success'}
        return {'feed': None, 'status': response.status_code}
    except Exception as e:
        return {'feed': None, 'status': 'failed'}

def generate_untitled(entry):
    try: return entry.title
    except: 
        try: return entry.article[:50]
        except: return entry.link

def clean_html(html_content):
    soup = BeautifulSoup(html_content, "html.parser")
    for s in ["script", "style", "img", "a", "video", "audio", "iframe", "input"]:
        for t in soup.find_all(s): t.decompose()
    return soup.get_text()

def filter_entry(entry, filter_apply, filter_type, filter_rule):
    if filter_apply == 'title': text = entry.title
    elif filter_apply == 'article': text = entry.article
    elif filter_apply == 'link': text = entry.link
    elif not filter_apply: return True
    else: return True

    if filter_type == 'include': return re.search(filter_rule, text)
    elif filter_type == 'exclude': return not re.search(filter_rule, text)
    return True

def read_entry_from_file(sec):
    out_dir = os.path.join(BASE, get_cfg(sec, 'name'))
    try:
        with open(out_dir + '.xml', 'r') as f:
            rss = f.read()
        return feedparser.parse(rss).entries
    except: return []

def gpt_summary(query, model, language):
    system_prompt = f"""你现在是一位拥有10年经验的资深设计总监和AI原住民。
请用中文深度总结这篇文章：
1. 【最新AI消息】：提炼核心技术突破点。
2. 【实用工作流】：拆解“输入-处理-输出”的具体步骤。
3. 【行业思考】：分析该动态对设计师是替代还是赋能？给出行动建议。
先提取{keyword_length}个关键词在同一行，然后在{summary_length}字内按点输出。
必须以 '<br><br>总结:' 开头。"""

    messages = [{"role": "user", "content": f"{system_prompt}\n\n文章内容: {query}"}]
    
    client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
    completion = client.chat.completions.create(model=model, messages=messages)
    return completion.choices[0].message.content

def output(sec, language):
    log_file = os.path.join(BASE, get_cfg(sec, 'name') + '.log')
    out_dir = os.path.join(BASE, get_cfg(sec, 'name'))
    rss_urls = get_cfg(sec, 'url').split(',')
    max_items = int(get_cfg(sec, 'max_items') or 0)
    
    existing_entries = read_entry_from_file(sec)
    existing_links = [x.link for x in existing_entries]
    append_entries = []
    cnt = 0

    for rss_url in rss_urls:
        feed = fetch_feed(rss_url, log_file)['feed']
        if not feed: continue
        
        for entry in feed.entries:
            if entry.link in existing_links or cnt >= max_items: continue
            
            entry.title = generate_untitled(entry)
            try: entry.article = entry.content[0].value
            except: entry.article = getattr(entry, 'description', entry.title)

            cleaned_article = clean_html(entry.article)
            
            # AI 总结
            try:
                model_to_use = custom_model if custom_model else "gpt-4o-mini"
                entry.summary = gpt_summary(cleaned_article, model_to_use, language)
                
                # ✨ 核心改进：只要有新内容，立刻发微信
                send_wechat_message(entry.title, entry.link, entry.summary)
                
                append_entries.append(entry)
                cnt += 1
            except Exception as e:
                print(f"总结失败: {e}")

    # 渲染 XML (保持网页更新)
    if append_entries:
        template = Template(open('template.xml').read())
        rss = template.render(feed=feed, append_entries=append_entries, existing_entries=existing_entries)
        with open(out_dir + '.xml', 'w') as f: f.write(rss)

# 启动执行
try: os.mkdir(BASE)
except: pass

for x in secs[1:]:
    output(x, language=language)
