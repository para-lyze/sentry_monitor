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
# 从 GitHub Secrets 获取
USERNAME = os.environ.get("STU_ID")
PASSWORD = os.environ.get("STU_PWD")
MAIL_HOST = "smtp.qq.com"
MAIL_USER = os.environ.get("MAIL_USER")
MAIL_PASS = os.environ.get("MAIL_PASS")
MAIL_RECEIVER = os.environ.get("MAIL_RECEIVER")

# 监控名单：名称需准确，老师名单支持包含匹配
TARGET_COURSES = [
    {"name": "大学物理实验B2", "teachers": [], "times": []},
    {"name": "操作系统", "teachers": ["李蒙", "孙瑞泽", "刘成健", "郑俊虹", "马军超"], "times": []},
    {"name": "面向对象程序设计", "teachers": ["许强华", "刘会芬", "李青", "郭文佳", "安晓欣"], "times": []},
    {"name": "大数据原理与技术", "teachers": [], "times": []},
    {"name": "计算机组成与系统结构", "teachers": [], "times": []},
    {"name": "计算机论题", "teachers": [], "times": []}
]

STATUS_FILE = "course_status.json"
# 接口 URL
URL_BASE = "https://jwxt.sztu.edu.cn/jsxsd/xsxkkc/xsxkFawxk"


# ==========================================

def send_email(title, content):
    if not MAIL_USER or not MAIL_PASS: return
    try:
        message = MIMEText(content, 'plain', 'utf-8')
        message['From'] = formataddr(["SZTU选课哨兵", MAIL_USER])
        message['To'] = formataddr(["同学", MAIL_RECEIVER])
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

    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 20)

    try:
        # 1. 登录 SSO
        driver.get('https://auth.sztu.edu.cn/idp/authcenter/ActionAuthChain?entityId=jiaowu')
        wait.until(EC.presence_of_element_located((By.ID, "j_username"))).send_keys(USERNAME)
        driver.find_element(By.ID, "j_password").send_keys(PASSWORD)
        driver.find_element(By.ID, "loginButton").click()
        time.sleep(5)

        # 2. 模拟进入选课页
        print("🚀 寻找选课入口并尝试激活权限...")
        driver.get("https://jwxt.sztu.edu.cn/jsxsd/xsxk/xsxk_index")
        time.sleep(3)

        # 3. 递归寻找“进入选课”按钮 (解决 Frame 嵌套问题)
        def click_enter_btn():
            frames = driver.find_elements(By.TAG_NAME, "iframe") + driver.find_elements(By.TAG_NAME, "frame")
            for f in frames:
                try:
                    driver.switch_to.frame(f)
                    btns = driver.find_elements(By.XPATH, "//*[contains(text(), '进入选课')]")
                    if btns:
                        driver.execute_script("arguments[0].click();", btns[0])
                        print("   ✅ 点击‘进入选课’成功")
                        driver.switch_to.default_content()
                        return True
                    if click_enter_btn(): return True  # 深度遍历
                    driver.switch_to.default_content()
                except:
                    driver.switch_to.default_content()
            return False

        click_enter_btn()
        time.sleep(3)

        # 4. 强制跳转到跨专业选课页面，确保 JWXT 域下的 Cookie 完全生成
        print("🔗 正在同步【跨专业选课】权限状态...")
        driver.get("https://jwxt.sztu.edu.cn/jsxsd/xsxkkc/comeInFawxk")
        time.sleep(5)

        # 5. 获取 Cookie
        cookies_list = driver.get_cookies()
        cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies_list])

        if "JSESSIONID" in cookie_str:
            print("✨ 权限激活成功，Cookie 获取就绪")
            return cookie_str
        else:
            print("❌ 未捕获到 JSESSIONID，权限激活可能失败")
            return None

    except Exception as e:
        print(f"💥 自动化导航异常: {e}")
        return None
    finally:
        driver.quit()


def run_monitor():
    full_cookie = get_automated_cookies()
    if not full_cookie: return

    # 读取状态
    last_status = {}
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r") as f:
                last_status = json.load(f)
        except:
            last_status = {}

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Cookie": full_cookie,
        "Referer": "https://jwxt.sztu.edu.cn/jsxsd/xsxkkc/comeInFawxk",
        "X-Requested-With": "XMLHttpRequest"
    }

    current_status = {}
    for target in TARGET_COURSES:
        # 参数配置：反选过滤器
        params = {"kcxx": target['name'], "sfym": "", "sfct": "false", "sfxx": "false"}
        payload = {"sEcho": "1", "iDisplayStart": "0", "iDisplayLength": "500"}

        try:
            resp = requests.post(URL_BASE, params=params, data=payload, headers=headers, timeout=15)

            # 诊断：如果不是 JSON 格式则打印前 100 字报错
            if "aaData" not in resp.text:
                print(f"⚠️ [{target['name']}] 接口返回非数据内容: {resp.text[:100].strip()}")
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
                        # 盯死“非主选”余额
                        count = int(item.get("syfzxwrs", 0))
                        current_status[cid] = count

                        if count > 0 and count > last_status.get(cid, 0):
                            msg = f"发现空位！\n课程：{r_name}\n老师：{r_teacher}\n时间：{r_time}\n名额：{count}\n编号：{cid}"
                            print(f"🚩 报警: {r_name}")
                            send_email("🚨 选课哨兵发现名额！", msg)
                        else:
                            print(f"🕒 {r_name} (@{r_teacher}): {count}")
        except Exception as e:
            print(f"💥 检查 {target['name']} 异常: {e}")

    # 更新持久化状态
    with open(STATUS_FILE, "w") as f:
        json.dump(current_status, f)


if __name__ == "__main__":
    run_monitor()
