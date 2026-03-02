import os
import time
import json
import smtplib
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


def run_monitor():
    print("🔑 启动浏览器级全栈监控...")
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")

    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 15)

    # 设置 JS 异步脚本的超时时间
    driver.set_script_timeout(15)

    try:
        # 1. 登录
        driver.get('https://auth.sztu.edu.cn/idp/authcenter/ActionAuthChain?entityId=jiaowu')
        wait.until(EC.presence_of_element_located((By.ID, "j_username"))).send_keys(USERNAME)
        driver.find_element(By.ID, "j_password").send_keys(PASSWORD)
        driver.find_element(By.ID, "loginButton").click()
        time.sleep(3)

        # 2. 进入选课页激活会话
        driver.get("https://jwxt.sztu.edu.cn/jsxsd/xsxk/xsxk_index")
        time.sleep(2)

        # 3. 进入目标搜索页 (方案内 或 跨专业)
        # 这一步让浏览器拥有了合法的上下文环境
        driver.get("https://jwxt.sztu.edu.cn/jsxsd/xsxkkc/comeInFawxk")
        time.sleep(3)
        print("✨ 浏览器已进入选课环境，准备注入查询脚本...")

        # 读取上次名额记录
        last_status = {}
        if os.path.exists(STATUS_FILE):
            try:
                with open(STATUS_FILE, "r") as f:
                    last_status = json.load(f)
            except:
                pass

        current_status = {}

        # 4. 遍历查询：利用 JS fetch 在浏览器内部发请求
        for target in TARGET_COURSES:
            # 这段 JS 代码会被注入到浏览器中执行
            js_code = """
            var done = arguments[0]; // Selenium 异步回调函数
            var params = new URLSearchParams({
                'sEcho': '1',
                'iDisplayStart': '0',
                'iDisplayLength': '500',
                'kcxx': '%s',
                'sfym': 'false', 
                'sfct': 'false',
                'sfxx': 'false'
            });
            // 浏览器直接用当前完美的身份调用接口
            fetch('/jsxsd/xsxkkc/xsxkFawxk', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: params
            })
            .then(response => response.json())
            .then(data => done(data))
            .catch(error => done({'error': error.toString()}));
            """ % target['name']

            try:
                # 执行 JS 并等待 JSON 结果传回 Python
                data = driver.execute_async_script(js_code)

                if "error" in data:
                    print(f"⚠️ [{target['name']}] JS请求异常: {data['error']}")
                    continue

                if "aaData" not in data:
                    print(f"⚠️ [{target['name']}] 未返回预期数据。")
                    continue

                courses = data.get("aaData", [])
                for item in courses:
                    r_name = str(item.get("kcmc", ""))
                    r_teacher = str(item.get("skls", ""))
                    r_time = str(item.get("sksj", "")).replace("<br/>", " ")

                    if target['name'] in r_name:
                        teacher_match = not target['teachers'] or any(t in r_teacher for t in target['teachers'])
                        if teacher_match:
                            cid = str(item.get("kch"))
                            count = int(item.get("syfzxwrs", 0))
                            current_status[cid] = count

                            if count > 0 and count > last_status.get(cid, 0):
                                msg = f"发现名额！\n课程：{r_name}\n老师：{r_teacher}\n时间：{r_time}\n名额：{count}"
                                print(f"🚩 报警: {r_name}")
                                send_email(f"🚨 哨兵发现 {r_name} 有空位！", msg)
                            else:
                                print(f"🕒 {r_name} (@{r_teacher}): {count}")

            except Exception as e:
                print(f"💥 执行 {target['name']} 查询脚本超时或崩溃: {e}")

        # 保存状态
        with open(STATUS_FILE, "w") as f:
            json.dump(current_status, f)

    except Exception as e:
        print(f"💥 浏览器主进程异常: {e}")
    finally:
        driver.quit()
        print("🛑 任务结束，释放浏览器资源。")


if __name__ == "__main__":
    run_monitor()
