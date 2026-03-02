import requests
import json
import os
import smtplib
from email.mime.text import MIMEText
from email.header import Header

# ================= 配置区域 =================
# 1. 填入你想要监控的课程、老师及特定时间
# teachers: 留空 [] 监控所有老师
# times: 填入时间关键词（如 ["星期四", "11-14"]），留空 [] 监控所有时间段
TARGET_COURSES = [
    {
        "name": "大学物理实验B2", 
        "teachers": [], 
        "times": [] 
    },
    {
        "name": "操作系统", 
        "teachers": ["李蒙,孙瑞泽","刘成健,郑俊虹","马军超,郑俊虹"], 
        "times": [] 
    },
    {
        "name": "面向对象程序设计", 
        "teachers": ["许强华,刘会芬","李青,郭文佳","安晓欣,刘会芬"], 
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

# 2. 从 GitHub Secrets 读取环境变量
FULL_COOKIE = os.environ.get("FULL_COOKIE")
MAIL_USER = os.environ.get("MAIL_USER")
MAIL_PASS = os.environ.get("MAIL_PASS")
RECEIVER = os.environ.get("RECEIVER")

URL = "https://jwxt.sztu.edu.cn/jsxsd/xsxkkc/xsxkFawxk"
STATUS_FILE = "course_status.json"

# ===========================================

def send_email(subject, msg_content):
    msg = MIMEText(msg_content, 'plain', 'utf-8')
    msg['From'] = Header("选课哨兵", 'utf-8')
    msg['To'] = Header("张同学", 'utf-8')
    msg['Subject'] = Header(subject, 'utf-8')

    try:
        server = smtplib.SMTP_SSL("smtp.qq.com", 465)
        server.login(MAIL_USER, MAIL_PASS)
        server.sendmail(MAIL_USER, [RECEIVER], msg.as_string())
        server.quit()
        print(f"✅ 邮件发送成功: {subject}")
    except Exception as e:
        print(f"❌ 邮件发送失败: {e}")

def run_monitor():
    if not FULL_COOKIE:
        print("❌ 错误：环境变量 FULL_COOKIE 为空。")
        return

    if os.path.exists(STATUS_FILE):
        with open(STATUS_FILE, "r") as f:
            last_status = json.load(f)
    else:
        last_status = {}

    current_status = {}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Cookie": FULL_COOKIE,
        "Referer": "https://jwxt.sztu.edu.cn/jsxsd/xsxkkc/comeInFawxk",
        "X-Requested-With": "XMLHttpRequest"
    }

    for target in TARGET_COURSES:
        course_keyword = target['name']
        allowed_teachers = target['teachers']
        allowed_times = target['times']

        query_params = {
            "kcxx": course_keyword,
            "sfym": "", 
            "sfct": "false", 
            "sfxx": "false"
        }
        payload = {"sEcho": "1", "iDisplayStart": "0", "iDisplayLength": "500"}

        try:
            resp = requests.post(URL, params=query_params, data=payload, headers=headers, timeout=15)
            
            if "login" in resp.text or "用户登录" in resp.text:
                error_msg = "🚨 警告：教务系统 Cookie 已失效，监控停止！请更新 FULL_COOKIE。"
                send_email("🚨 警告：监控 Cookie 已失效", error_msg)
                return 

            data = resp.json().get("aaData", [])
            for item in data:
                real_name = str(item.get("kcmc", ""))
                real_teacher = str(item.get("skls", ""))
                real_time = str(item.get("sksj", "")).replace("<br/>", " ")
                
                # 校验课程名
                if course_keyword in real_name:
                    # 校验老师 (如果名单不为空)
                    teacher_match = not allowed_teachers or any(t in real_teacher for t in allowed_teachers)
                    # 校验时间 (如果名单不为空，需满足所有关键词)
                    time_match = not allowed_times or all(t in real_time for t in allowed_times)
                    
                    if teacher_match and time_match:
                        course_id = str(item.get("kch"))
                        count = int(item.get("syfzxwrs", 0))
                        current_status[course_id] = count

                        if count > 0 and count > last_status.get(course_id, 0):
                            msg = (f"发现空位！\n"
                                   f"课程：{real_name}\n"
                                   f"教师：{real_teacher}\n"
                                   f"时间：{real_time}\n"
                                   f"非主选余量：{count}\n"
                                   f"编号：{course_id}")
                            print(f"🚩 {msg}")
                            send_email("🚨 发现选课空位！", msg)
                        else:
                            print(f"⏳ {real_name} (@{real_teacher}) [{real_time}] 名额: {count}")
                            
        except Exception as e:
            print(f"💥 检查 [{course_keyword}] 异常: {e}")

    with open(STATUS_FILE, "w") as f:
        json.dump(current_status, f)

if __name__ == "__main__":
    run_monitor()
