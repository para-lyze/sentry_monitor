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
# 账户与邮件信息 (从 GitHub Secrets 获取)
USERNAME = os.environ.get("STU_ID")
PASSWORD = os.environ.get("STU_PWD")
MAIL_HOST = "smtp.qq.com"
MAIL_USER = os.environ.get("MAIL_USER")
MAIL_PASS = os.environ.get("MAIL_PASS")
MAIL_RECEIVER = os.environ.get("MAIL_RECEIVER")

# 监控课程配置: 包含名称、老师白名单、时间关键词
TARGET_COURSES = [
    {"name": "大学物理实验B2", "teachers": [], "times": []},
    {"name": "操作系统", "teachers": ["李蒙", "孙瑞泽", "刘成健", "郑俊虹", "马军超"], "times": []},
    {"name": "面向对象程序设计", "teachers": ["许强华", "刘会芬", "李青", "郭文佳", "安晓欣"], "times": []},
    {"name": "大数据原理与技术", "teachers": [], "times": []},
    {"name": "计算机组成与系统结构", "teachers": [], "times": []},
    {"name": "计算机论题", "teachers": [], "times": []}
]

STATUS_FILE = "course_status.json"
# 关键：跨专业选课的 API 接口地址
URL_BASE = "https://jwxt.sztu.edu.cn/jsxsd/xsxkkc/xsxkKzyxk"
# ==========================================

def send_email(title, content):
    """通用邮件发送函数"""
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
    """模拟“三连击”进入跨专业选课界面并提取 Cookie"""
    print("🔑 启动自动化导航登录...")
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 20)
    
    try:
        # 1. SSO 统一认证登录
        driver.get('https://auth.sztu.edu.cn/idp/authcenter/ActionAuthChain?entityId=jiaowu')
        wait.until(EC.presence_of_element_located((By.ID, "j_username"))).send_keys(USERNAME)
        driver.find_element(By.ID, "j_password").send_keys(PASSWORD)
        driver.find_element(By.ID, "loginButton").click()
        time.sleep(3)

        # 2. 模拟点击进入选课系统 (处理“三连击”逻辑)
        print("🚀 执行选课系统多级跳转...")
        # 尝试直接访问选课轮次列表页
        driver.get("https://jwxt.sztu.edu.cn/jsxsd/xsxk/xsxk_index")
        time.sleep(2)

        # 尝试寻找并点击“进入选课”按钮 (循环点击 3 次以模拟多层确认)
        for i in range(1, 4):
            try:
                enter_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), '进入选课')]")))
                driver.execute_script("arguments[0].click();", enter_btn)
                print(f"   ✅ 第 {i} 次点击“进入选课”成功")
                time.sleep(2)
            except:
                print(f"   ⚠️ 第 {i} 次点击未找到，尝试直接跳转...")
                driver.get("https://jwxt.sztu.edu.cn/jsxsd/xsxkkc/comeInKzyxk")
                break

        # 3. 最终确认进入“跨专业选课”模块以激活权限
        print("🔗 正在激活【跨专业选课】权限...")
        driver.get("https://jwxt.sztu.edu.cn/jsxsd/xsxkkc/comeInKzyxk")
        time.sleep(3)

        # 4. 提取完全授权的 Cookie
        cookies = driver.get_cookies()
        cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
        
        if "JSESSIONID" in cookie_str:
            print("✅ 跨专业权限已激活，获取 Cookie 成功")
            return cookie_str
        else:
            print("❌ 获取的 Cookie 缺少核心凭证")
            return None

    except Exception as e:
        print(f"❌ 导航登录失败: {e}")
        return None
    finally:
        driver.quit()

def run_monitor():
    # 1. 自动化获取 Cookie
    full_cookie = get_automated_cookies()
    if not full_cookie:
        send_email("🚨 警告：监控登录失败", "哨兵无法通过自动导航获取权限。可能原因：密码错误、系统维护或验证码拦截。")
        return

    # 2. 读取上次名额状态
    last_status = {}
    if os.path.exists(STATUS_FILE):
        with open(STATUS_FILE, "r") as f: last_status = json.load(f)

    current_status = {}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Cookie": full_cookie,
        "Referer": "https://jwxt.sztu.edu.cn/jsxsd/xsxkkc/comeInKzyxk",
        "X-Requested-With": "XMLHttpRequest"
    }

    # 3. 执行监测
    for target in TARGET_COURSES:
        # 反选所有过滤器以监控全量数据
        query_params = {
            "kcxx": target['name'],
            "sfym": "", "sfct": "false", "sfxx": "false"
        }
        payload = {"sEcho": "1", "iDisplayStart": "0", "iDisplayLength": "500"}

        try:
            resp = requests.post(URL_BASE, params=query_params, data=payload, headers=headers, timeout=15)
            # 诊断返回内容是否为 JSON
            if resp.status_code != 200 or "login" in resp.text:
                print(f"❌ 接口访问受限: {target['name']}")
                continue

            data = resp.json().get("aaData", [])
            for item in data:
                r_name = str(item.get("kcmc", ""))
                r_teacher = str(item.get("skls", ""))
                r_time = str(item.get("sksj", "")).replace("<br/>", " ")

                # 匹配逻辑: 课程名包含关键词 + 老师(若有) + 时间(若有)
                if target['name'] in r_name:
                    teacher_match = not target['teachers'] or any(t in r_teacher for t in target['teachers'])
                    time_match = not target['times'] or all(t in r_time for t in target['times'])

                    if teacher_match and time_match:
                        cid = str(item.get("kch"))
                        # 第二轮捡漏核心：提取非主选人数
                        count = int(item.get("syfzxwrs", 0))
                        current_status[cid] = count

                        # 判定：名额增加则报警
                        if count > 0 and count > last_status.get(cid, 0):
                            alert_msg = f"发现空位！\n课程：{r_name}\n老师：{r_teacher}\n时间：{r_time}\n非主选名额：{count}\n编号：{cid}"
                            send_email("🚨 发现跨专业选课空位！", alert_msg)
                            print(f"🚩 发现名额: {r_name} (@{r_teacher})")
                        else:
                            print(f"🕒 {r_name} (@{r_teacher}): {count}")
        except Exception as e:
            print(f"💥 检查 {target['name']} 异常: {e}")

    # 保存状态
    with open(STATUS_FILE, "w") as f:
        json.dump(current_status, f)

if __name__ == "__main__":
    run_monitor()
