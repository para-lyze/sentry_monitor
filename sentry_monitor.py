import requests
import json
import os
import smtplib
from email.mime.text import MIMEText
from email.header import Header

# ================= 配置区域 =================
# 1. 填入你想要监控的课程完整名称或关键词
TARGET_COURSE_NAMES = [
    "操作系统","大学物理实验B2","面向对象程序设计","大数据原理与技术","计算机组成与系统结构"
]

# 2. 从 GitHub Secrets 读取敏感信息 (无需改动)
JSESSIONID = os.environ.get("JSESSIONID")
MAIL_USER = os.environ.get("MAIL_USER")
MAIL_PASS = os.environ.get("MAIL_PASS")
RECEIVER = os.environ.get("RECEIVER")

URL = "https://jwxt.sztu.edu.cn/jsxsd/xsxkkc/xsxkFawxk"
STATUS_FILE = "course_status.json"
# ===========================================

def send_email(msg_content):
    msg = MIMEText(msg_content, 'plain', 'utf-8')
    msg['From'] = Header("选课哨兵", 'utf-8')
    msg['To'] = Header("同学", 'utf-8')
    msg['Subject'] = Header("🚨 发现选课空位！", 'utf-8')

    try:
        server = smtplib.SMTP_SSL("smtp.qq.com", 465)
        server.login(MAIL_USER, MAIL_PASS)
        server.sendmail(MAIL_USER, [RECEIVER], msg.as_string())
        server.quit()
        print("✅ 邮件提醒已发送")
    except Exception as e:
        print(f"❌ 邮件发送失败: {e}")


def run_monitor():
    # 读取历史状态（按课程编号记录名额，确保多班级独立监测）
    if os.path.exists(STATUS_FILE):
        with open(STATUS_FILE, "r") as f:
            last_status = json.load(f)
    else:
        last_status = {}

    current_status = {}
    headers = {
        "Cookie": f"JSESSIONID={JSESSIONID}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "X-Requested-With": "XMLHttpRequest"
    }

    for name in TARGET_COURSE_NAMES:
        # 使用名称作为搜索关键词，反选所有过滤器以获取实时全量数据
        params = {
            "kcxx": name,
            "sfym": "",  # 必须为空，否则已满课程不会显示在数据中
            "sfct": "false",  # 必须为 false，避免和你已选课程（如物理实验）冲突导致不显示
            "sfxx": "false"
        }
        payload = {"sEcho": "1", "iDisplayStart": "0", "iDisplayLength": "50"}

        try:
            resp = requests.post(URL, params=params, data=payload, headers=headers, timeout=15)
            if "login" in resp.text:
                print(f"❌ Cookie失效，无法监测课程：{name}")
                continue

            data = resp.json().get("aaData", [])
            for item in data:
                course_name = str(item.get("kcmc", ""))
                # 只有当返回结果中确实包含你搜索的名称时才处理
                if name in course_name:
                    course_id = str(item.get("kch"))
                    teacher = str(item.get("skls"))
                    # 第二轮核心指标：剩余非主选
                    count = int(item.get("syfzxwrs", 0))

                    current_status[course_id] = count

                    # 判定提醒：当前有名额，且比上次记录的多（或上次是0）
                    if count > 0 and count > last_status.get(course_id, 0):
                        print(f"🚩 命中！{course_name} (@{teacher}) 发现名额: {count}")
                        send_email(
                            f"发现空位！\n课程：{course_name}\n教师：{teacher}\n当前非主选余量：{count}\n课程编号：{course_id}"
                        )
                    else:
                        print(f"⏳ {course_name} (@{teacher}) 当前名额: {count}")
        except Exception as e:
            print(f"💥 检查 [{name}] 过程中发生异常: {e}")

    # 保存新状态
    with open(STATUS_FILE, "w") as f:
        json.dump(current_status, f)


if __name__ == "__main__":
    if not JSESSIONID:
        print("❌ 错误：未检测到环境变量 JSESSIONID，请在 Secrets 中配置。")
    else:
        run_monitor()