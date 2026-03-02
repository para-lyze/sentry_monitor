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

# 监控课程配置
TARGET_COURSES = [
    {
        "name": "大学物理实验B2",
        "teachers": [],
        "times": []
    },
    {
        "name": "操作系统",
        "teachers": ["李蒙,孙瑞泽", "刘成健,郑俊虹", "马军超,郑俊虹"],
        "times": []
    },
    {
        "name": "面向对象程序设计",
        "teachers": ["许强华,刘会芬", "李青,郭文佳", "安晓欣,刘会芬"],
        "times": []
    },
    {
        "name": "大数据原理与技术",
        "teachers": [],
        "times": []
    },
    {
        "name": "计算机组成与系统结构",
        "teachers": [],
        "times": []
    },
    {
        "name": "计算机论题",
        "teachers": [],
        "times": []
    }
]

STATUS_FILE = "course_status.json"
URL_BASE = "https://jwxt.sztu.edu.cn/jsxsd/xsxkkc/xsxkFawxk"


# ==========================================

def send_email(title, content):
    """通用邮件发送"""
    if not MAIL_USER or not MAIL_PASS: return
    try:
        message = MIMEText(content, 'plain', 'utf-8')
        message['From'] = formataddr(["选课哨兵", MAIL_USER])
        message['To'] = formataddr(["君泽同学", MAIL_RECEIVER])
        message['Subject'] = Header(title, 'utf-8')
        smtpObj = smtplib.SMTP_SSL(MAIL_HOST, 465)
        smtpObj.login(MAIL_USER, MAIL_PASS)
        smtpObj.sendmail(MAIL_USER, [MAIL_RECEIVER], message.as_string())
        smtpObj.quit()
        print("📨 邮件发送成功")
    except Exception as e:
        print(f"❌ 邮件错误: {e}")


def get_automated_cookies():
    """使用 Selenium 模拟登录并提取 Cookie"""
    print("🔑 正在执行自动化 SSO 登录...")
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36")

    driver = webdriver.Chrome(options=options)
    try:
        # SSO 登录流程
        driver.get('https://auth.sztu.edu.cn/idp/authcenter/ActionAuthChain?entityId=jiaowu')
        wait = WebDriverWait(driver, 30)
        wait.until(EC.presence_of_element_located((By.ID, "j_username"))).send_keys(USERNAME)
        driver.find_element(By.ID, "j_password").send_keys(PASSWORD)
        driver.find_element(By.ID, "loginButton").click()

        # 等待跳转回教务系统主页
        time.sleep(5)

        # 提取所有 Cookie 并拼接成 requests 可用的格式
        cookies = driver.get_cookies()
        cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
        print("✅ 成功获取最新 Cookie")
        return cookie_str
    except Exception as e:
        print(f"❌ 自动登录失败: {e}")
        return None
    finally:
        driver.quit()


def run_monitor():
    # 1. 自动获取 Cookie
    full_cookie = get_automated_cookies()
    if not full_cookie:
        send_email("🚨 警告：监控登录失败", "哨兵无法通过 SSO 登录获取 Cookie，请检查学号密码或网络。")
        return

    # 2. 读取历史状态
    last_status = {}
    if os.path.exists(STATUS_FILE):
        with open(STATUS_FILE, "r") as f: last_status = json.load(f)

    current_status = {}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)...",
        "Cookie": full_cookie,
        "Referer": "https://jwxt.sztu.edu.cn/jsxsd/xsxkkc/comeInFawxk",
        "X-Requested-With": "XMLHttpRequest"
    }

    # 3. 执行监测逻辑
    for target in TARGET_COURSES:
        query_params = {
            "kcxx": target['name'],
            "sfym": "", "sfct": "false", "sfxx": "false"
        }
        payload = {"sEcho": "1", "iDisplayStart": "0", "iDisplayLength": "500"}

        try:
            resp = requests.post(URL_BASE, params=query_params, data=payload, headers=headers, timeout=15)
            data = resp.json().get("aaData", [])
            for item in data:
                real_name = str(item.get("kcmc", ""))
                real_teacher = str(item.get("skls", ""))
                real_time = str(item.get("sksj", "")).replace("<br/>", " ")

                # 多重过滤匹配
                if target['name'] in real_name:
                    teacher_match = not target['teachers'] or any(t in real_teacher for t in target['teachers'])
                    time_match = not target['times'] or all(t in real_time for t in target['times'])

                    if teacher_match and time_match:
                        cid = str(item.get("kch"))
                        count = int(item.get("syfzxwrs", 0))
                        current_status[cid] = count

                        if count > 0 and count > last_status.get(cid, 0):
                            send_email("🚨 发现选课空位！",
                                       f"课程：{real_name}\n老师：{real_teacher}\n时间：{real_time}\n名额：{count}")
                        print(f"🕒 {real_name} (@{real_teacher}): {count}")
        except Exception as e:
            print(f"💥 检查 {target['name']} 异常: {e}")

    with open(STATUS_FILE, "w") as f:
        json.dump(current_status, f)


if __name__ == "__main__":
    run_monitor()
