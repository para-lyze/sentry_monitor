import os
import time
import json
import smtplib
import requests
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ================= 配置区 =================
USERNAME = os.environ.get("STU_ID")
PASSWORD = os.environ.get("STU_PWD")
MAIL_HOST = "smtp.qq.com"
MAIL_USER = os.environ.get("MAIL_USER")
MAIL_PASS = os.environ.get("MAIL_PASS")
MAIL_RECEIVER = os.environ.get("MAIL_RECEIVER")

TARGET_COURSES = [
    {"name": "大学物理实验B2", "teachers": [], "times": []},
    {"name": "操作系统", "teachers": ["李蒙", "孙瑞泽", "刘成健", "郑俊虹", "马军超"], "times": []},
    {"name": "面向对象程序设计", "teachers": ["许强华", "刘会芬", "李青", "郭文佳", "安晓欣"], "times": []},
    {"name": "大数据原理与技术", "teachers": [], "times": []},
    {"name": "计算机组成与系统结构", "teachers": [], "times": []},
    {"name": "计算机论题", "teachers": [], "times": []}
]

STATUS_FILE = "course_status.json"
# 关键修改：跨专业选课必须使用 Kzyxk 接口
URL_BASE = "https://jwxt.sztu.edu.cn/jsxsd/xsxkkc/xsxkKzyxk"
REFERER_URL = "https://jwxt.sztu.edu.cn/jsxsd/xsxkkc/comeInKzyxk"
# ==========================================

def send_email(title, content):
    if not MAIL_USER or not MAIL_PASS: return
    try:
        message = MIMEText(content, 'plain', 'utf-8')
        message['From'] = formataddr(["SZTU选课哨兵", MAIL_USER])
        message['To'] = formataddr(["君泽同学", MAIL_RECEIVER])
        message['Subject'] = Header(title, 'utf-8')
        smtpObj = smtplib.SMTP_SSL(MAIL_HOST, 465)
        smtpObj.login(MAIL_USER, MAIL_PASS)
        smtpObj.sendmail(MAIL_USER, [MAIL_RECEIVER], message.as_string())
        smtpObj.quit()
        print("📨 邮件发送成功")
    except Exception as e:
        print(f"❌ 邮件发送失败: {e}")

def get_automated_cookies():
    print("🔑 启动自动化导航登录流程...")
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1920,1080")
    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 15)
    
    try:
        # 1. SSO 登录
        driver.get('https://auth.sztu.edu.cn/idp/authcenter/ActionAuthChain?entityId=jiaowu')
        wait.until(EC.presence_of_element_located((By.ID, "j_username"))).send_keys(USERNAME)
        driver.find_element(By.ID, "j_password").send_keys(PASSWORD)
        driver.find_element(By.ID, "loginButton").click()
        time.sleep(5)

        # 2. 进入选课首页并激活
        print("🚀 正在激活选课 Session...")
        driver.get("https://jwxt.sztu.edu.cn/jsxsd/xsxk/xsxk_index")
        time.sleep(3)
        
        # 3. 访问跨专业选课入口页
        driver.get(REFERER_URL)
        time.sleep(5)

        cookies = driver.get_cookies()
        print("✨ 权限激活成功")
        return "; ".join([f"{c['name']}={c['value']}" for c in cookies])
    except Exception as e:
        print(f"💥 自动化导航异常: {e}")
        return None
    finally:
        driver.quit()

def run_monitor():
    full_cookie = get_automated_cookies()
    if not full_cookie or "JSESSIONID" not in full_cookie:
        print("❌ 未获取到有效 Cookie，请检查账号密码")
        return

    last_status = {}
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r") as f: last_status = json.load(f)
        except: pass

    # 使用 session 保持会话
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Cookie": full_cookie,
        "Referer": REFERER_URL,
        "X-Requested-With": "XMLHttpRequest"
    })

    # 重要：先进行一次 GET 预热，获取服务器信任
    session.get(REFERER_URL)

    current_status = {}
    for target in TARGET_COURSES:
        params = {
            "kcxx": target['name'],
            "sfym": "false", # 如果依然报错 HTML，尝试将此处改为 "false"
            "sfct": "false",
            "sfxx": "false"
        }
        payload = {"sEcho": "1", "iDisplayStart": "0", "iDisplayLength": "500"}

        try:
            resp = session.post(URL_BASE, params=params, data=payload, timeout=15)
            
            # 如果返回 HTML，尝试第二次机会：切换接口
            if "<html" in resp.text:
                # 备用接口切换逻辑
                alt_url = "https://jwxt.sztu.edu.cn/jsxsd/xsxkkc/xsxkFawxk"
                resp = session.post(alt_url, params=params, data=payload, timeout=15)

            if "aaData" not in resp.text:
                print(f"⚠️ [{target['name']}] 依然返回非法内容，跳过。")
                continue
            
            data = resp.json().get("aaData", [])
            for item in data:
                r_name, r_teacher = str(item.get("kcmc", "")), str(item.get("skls", ""))
                if target['name'] in r_name:
                    teacher_match = not target['teachers'] or any(t in r_teacher for t in target['teachers'])
                    if teacher_match:
                        cid = str(item.get("kch"))
                        count = int(item.get("syfzxwrs", 0))
                        current_status[cid] = count

                        if count > 0 and count > last_status.get(cid, 0):
                            msg = f"发现名额！\n课程：{r_name}\n老师：{r_teacher}\n名额：{count}"
                            send_email("🚨 选课哨兵提醒", msg)
                        print(f"🕒 {r_name} (@{r_teacher}): {count}")
        except Exception as e:
            print(f"💥 检查 {target['name']} 异常: {e}")

    with open(STATUS_FILE, "w") as f: json.dump(current_status, f)

if __name__ == "__main__":
    run_monitor()
