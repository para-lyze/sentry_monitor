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
# 恢复到你最初手动测试成功的方案内接口
URL_BASE = "https://jwxt.sztu.edu.cn/jsxsd/xsxkkc/xsxkFawxk"
REFERER_URL = "https://jwxt.sztu.edu.cn/jsxsd/xsxkkc/comeInFawxk"
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
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    # 伪装成真实浏览器
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 30)
    
    try:
        # 1. 登录 SSO
        driver.get('https://auth.sztu.edu.cn/idp/authcenter/ActionAuthChain?entityId=jiaowu')
        wait.until(EC.presence_of_element_located((By.ID, "j_username"))).send_keys(USERNAME)
        driver.find_element(By.ID, "j_password").send_keys(PASSWORD)
        driver.find_element(By.ID, "loginButton").click()
        
        # 【全场最核心的修复点】
        # 绝不能用 sleep 死等，必须等待 URL 正式变更为 jwxt 域名，这代表 SSO 握手完成！
        print("⏳ 正在等待 SSO 门票验证与重定向...")
        wait.until(EC.url_contains("jwxt.sztu.edu.cn/jsxsd"))
        print("✅ 成功进入教务系统主页，身份已核实！")
        time.sleep(2) # 稍微缓冲一下，让服务器种下 Cookie

        # 2. 访问选课页，激活选课 Session
        print("🔗 正在激活方案内选课权限...")
        driver.get(REFERER_URL)
        time.sleep(3)

        # 3. 提取此时的真·Cookie
        cookies = driver.get_cookies()
        cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
        
        if "JSESSIONID" in cookie_str:
            print("✨ 权限激活成功，获取到有效 Cookie！")
            return cookie_str
        else:
            print("❌ 获取 Cookie 失败")
            return None

    except Exception as e:
        print(f"💥 自动化登录异常: {e}")
        return None
    finally:
        driver.quit()

def run_monitor():
    full_cookie = get_automated_cookies()
    if not full_cookie: return

    last_status = {}
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r") as f: last_status = json.load(f)
        except: pass

    # 构造请求头，与你手动抓包时一模一样
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Cookie": full_cookie,
        "Referer": REFERER_URL,
        "X-Requested-With": "XMLHttpRequest"
    }

    current_status = {}
    for target in TARGET_COURSES:
        # 请求参数，模拟反选过滤已满和冲突
        params = {"kcxx": target['name'], "sfym": "", "sfct": "false", "sfxx": "false"}
        payload = {"sEcho": "1", "iDisplayStart": "0", "iDisplayLength": "500"}

        try:
            # 发送 POST 请求
            resp = requests.post(URL_BASE, params=params, data=payload, headers=headers, timeout=15)
            
            # 校验返回内容
            if "aaData" not in resp.text:
                print(f"⚠️ [{target['name']}] 接口被拦截！前50字: {resp.text[:50].strip()}")
                continue
            
            data = resp.json().get("aaData", [])
            for item in data:
                r_name = str(item.get("kcmc", ""))
                r_teacher = str(item.get("skls", ""))
                r_time = str(item.get("sksj", "")).replace("<br/>", " ")
                
                # 匹配逻辑
                if target['name'] in r_name:
                    teacher_match = not target['teachers'] or any(t in r_teacher for t in target['teachers'])
                    if teacher_match:
                        cid = str(item.get("kch"))
                        count = int(item.get("syfzxwrs", 0))
                        current_status[cid] = count

                        if count > 0 and count > last_status.get(cid, 0):
                            msg = f"发现空位！\n课程：{r_name}\n老师：{r_teacher}\n时间：{r_time}\n名额：{count}"
                            print(f"🚩 报警: {r_name} (@{r_teacher})")
                            send_email(f"🚨 哨兵发现 {r_name} 有空位！", msg)
                        else:
                            print(f"🕒 {r_name} (@{r_teacher}): {count}")
        except Exception as e:
            print(f"💥 检查 {target['name']} 异常: {e}")

    with open(STATUS_FILE, "w") as f:
        json.dump(current_status, f)

if __name__ == "__main__":
    run_monitor()
