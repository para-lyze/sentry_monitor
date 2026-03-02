import requests
import json
import os
import smtplib
from email.mime.text import MIMEText
from email.header import Header

# ================= 配置区域 =================
# 1. 填入你想要监控的课程名称 (支持模糊匹配)
TARGET_COURSE_NAMES = [
    "操作系统","大学物理实验B2","面向对象程序设计","大数据原理与技术","计算机组成与系统结构"
]

# 2. 从 GitHub Secrets 读取环境变量 (请勿在代码中硬编码)
FULL_COOKIE = os.environ.get("FULL_COOKIE")
MAIL_USER = os.environ.get("MAIL_USER")
MAIL_PASS = os.environ.get("MAIL_PASS")
RECEIVER = os.environ.get("RECEIVER")

# 3. 接口与状态文件
URL = "https://jwxt.sztu.edu.cn/jsxsd/xsxkkc/xsxkFawxk"
STATUS_FILE = "course_status.json"


# ===========================================

def send_email(msg_content):
    """发送邮件提醒"""
    msg = MIMEText(msg_content, 'plain', 'utf-8')
    msg['From'] = Header("SZTU选课哨兵", 'utf-8')
    msg['To'] = Header("张同学", 'utf-8')
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
    if not FULL_COOKIE:
        print("❌ 错误：环境变量 FULL_COOKIE 为空，请检查 GitHub Secrets 配置。")
        return

    # 读取历史状态
    if os.path.exists(STATUS_FILE):
        with open(STATUS_FILE, "r") as f:
            last_status = json.load(f)
    else:
        last_status = {}

    current_status = {}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.5845.97 Safari/537.36",
        "Cookie": FULL_COOKIE,  # 使用你提供的完整 Cookie 字符串
        "Referer": "https://jwxt.sztu.edu.cn/jsxsd/xsxkkc/comeInFawxk",
        "X-Requested-With": "XMLHttpRequest"
    }

    for name in TARGET_COURSE_NAMES:
        # 对应你“反选过滤器”的需求：不进行满额、冲突、限选过滤
        query_params = {
            "kcxx": name,
            "skls": "",
            "skxq": "",
            "skjc": "",
            "endJc": "",
            "sfym": "",  # 反选：过滤已满课程
            "sfct": "false",  # 反选：过滤冲突课程 (避开周三物理实验冲突判定)
            "sfxx": "false",  # 反选：过滤限选课程
            "skfs": ""
        }

        payload = {
            "sEcho": "1",
            "iDisplayStart": "0",
            "iDisplayLength": "500",
        }

        try:
            resp = requests.post(URL, params=query_params, data=payload, headers=headers, timeout=15)

            if "login" in resp.text:
                print(f"❌ Cookie已失效，请更新 FULL_COOKIE。")
                continue

            data = resp.json().get("aaData", [])
            for item in data:
                course_name = str(item.get("kcmc", ""))
                # 只有当搜索结果中包含指定的课程名称时才处理
                if name in course_name:
                    course_id = str(item.get("kch"))
                    teacher = str(item.get("skls"))
                    # 重点提取“剩余非主选”人数
                    count = int(item.get("syfzxwrs", 0))

                    current_status[course_id] = count

                    # 判定：当前有名额，且比上次记录的多（或是从0变多）
                    if count > 0 and count > last_status.get(course_id, 0):
                        msg = (f"发现空位！\n"
                               f"课程：{course_name}\n"
                               f"教师：{teacher}\n"
                               f"当前非主选余量：{count}\n"
                               f"课程编号：{course_id}")
                        print(f"🚩 {msg}")
                        send_email(msg)
                    else:
                        print(f"⏳ {course_name} (@{teacher}) 当前非主选名额: {count}")
        except Exception as e:
            print(f"💥 检查 [{name}] 异常: {e}")

    # 保存新状态
    with open(STATUS_FILE, "w") as f:
        json.dump(current_status, f)


if __name__ == "__main__":
    run_monitor()