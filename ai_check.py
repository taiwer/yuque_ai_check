from DrissionPage import Chromium
from DrissionPage import ChromiumOptions
from DrissionPage import SessionOptions
import random
import uuid
import requests
import re
import time
import threading
from queue import Queue, Empty
import glob
import os
import json
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from datetime import datetime

USE_PROXY = True
# 是否注入指纹
USE_FP = True

PROXY_FILE = "proxy.json"
PROXY_LOCK = threading.Lock()
GLOBAL_PROXIES = []  # 列表结构 [{"ip": "...", "exhausted": False, "count": 0}, ...]


# ----------------------------------------------------------------
# 保留的注释代码 (按要求不删除)
# ----------------------------------------------------------------
# def generate_random_fp(length=32):
#     """生成随机的指纹字符串"""
#     characters = "0123456789abcdef"
#     return "".join(random.choices(characters, k=length))


# def mutate_hex(s):
#     """
#     对 16 进制字符串进行微调变异（修改其中一位）
#     """
#     # 基础校验
#     if not s or not isinstance(s, str) or len(s) == 0:
#         return s

#     chars = "0123456789abcdef"

#     # 1. 随机选择一个索引位置
#     i = random.randint(0, len(s) - 1)

#     # 2. 获取该位置的旧字符（转小写以匹配 chars 列表）
#     old = s[i].lower()

#     # 3. 随机选择一个新字符
#     c = random.choice(chars)

#     # 4. 如果新旧字符相同，则强制取下一个字符（确保一定发生了变化）
#     if c == old:
#         idx = chars.index(old)
#         c = chars[(idx + 1) % len(chars)]

#     # 5. 返回拼接后的新字符串
#     return s[:i] + c + s[i + 1 :]


# def generate_uuid():
#     """生成UUID字符串"""
#     return str(uuid.uuid4())


# def generate_fp(page):
#     """浏览器指纹注入"""
#     if USE_FP:
#         # new_fp = generate_random_fp()

#         # 设置指纹
#         # page.set.local_storage("fp", new_fp)

#         # local_storage_after = page.local_storage()
#         # print(f"设置后指纹: {local_storage_after}")
#         # 在页面初始化时注入脚本，设置 localStorage 中的 fp 值
#         # 获取当前 指纹
#         current_fp = page.run_js('return localStorage.getItem("fp");')

#         # 微调变异当前指纹
#         if current_fp:
#             new_fp = mutate_hex(current_fp)

#         # 构造注入脚本
#         init_js = f'localStorage.setItem("fp", "{new_fp}"); console.log("Zhuque Reset Active: {new_fp}");'
#         page.add_init_js(init_js)

#     else:
#         new_fp = None
# ----------------------------------------------------------------


def load_proxies():
    """从文件加载代理"""
    global GLOBAL_PROXIES
    if not os.path.exists(PROXY_FILE):
        print(f"代理文件 {PROXY_FILE} 不存在")
        return

    with PROXY_LOCK:
        try:
            with open(PROXY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                # 兼容原有结构 {"data": [{"ip": "..."}]}
                if (
                    isinstance(data, dict)
                    and "data" in data
                    and isinstance(data["data"], list)
                ):
                    GLOBAL_PROXIES = data["data"]
                elif isinstance(data, list):
                    GLOBAL_PROXIES = data
                else:
                    print("代理文件格式无法识别")
                    GLOBAL_PROXIES = []

                # 初始化缺失的字段
                now = datetime.now()
                for p in GLOBAL_PROXIES:
                    if "exhausted" not in p:
                        p["exhausted"] = False
                    if "count" not in p:
                        p["count"] = 0

                    # 检查过期状态
                    p["expired"] = False
                    expire_time_str = p.get("expire_time", "")
                    if expire_time_str:
                        try:
                            # 尝试解析 yyyy-MM-dd HH:mm:ss
                            exp_dt = datetime.strptime(
                                str(expire_time_str).strip(), "%Y-%m-%d %H:%M:%S"
                            )
                            if now > exp_dt:
                                p["expired"] = True
                        except ValueError:
                            # 尝试无秒格式
                            try:
                                exp_dt = datetime.strptime(
                                    str(expire_time_str).strip(), "%Y-%m-%d %H:%M"
                                )
                                if now > exp_dt:
                                    p["expired"] = True
                            except:
                                pass
                        except Exception:
                            pass

                print(f"已加载 {len(GLOBAL_PROXIES)} 个代理")

                # 调试打印
                # print(f"加载的代理: {GLOBAL_PROXIES}")

        except Exception as e:
            print(f"加载代理文件失败: {e}")


def clean_chrome_user_data():
    """清理 Chrome 用户数据目录"""
    dirs = glob.glob("chrome_user_data*")
    for d in dirs:
        try:
            if os.path.isdir(d):
                print(f"删除目录: {d}")
                import shutil

                shutil.rmtree(d)
        except Exception as e:
            print(f"删除目录 {d} 失败: {e}")


def save_proxies():
    """保存代理状态到文件"""
    with PROXY_LOCK:
        try:
            # 读取原始文件以保持格式完整（如果有外层结构）
            original_data = {}
            if os.path.exists(PROXY_FILE):
                try:
                    with open(PROXY_FILE, "r", encoding="utf-8") as f:
                        original_data = json.load(f)
                except Exception:
                    pass

            # 更新 data 字段
            # 如果 original_data 是 dict，更新 original_data['data']
            if isinstance(original_data, dict):
                original_data["data"] = GLOBAL_PROXIES
                # 确保其他字段存在
                if "success" not in original_data:
                    original_data["success"] = "true"
                if "code" not in original_data:
                    original_data["code"] = 0
            else:
                original_data = {
                    "data": GLOBAL_PROXIES,
                    "code": 0,
                    "msg": "",
                    "success": "true",
                }

            with open(PROXY_FILE, "w", encoding="utf-8") as f:
                json.dump(original_data, f, indent=4, ensure_ascii=False)

        except Exception as e:
            print(f"保存代理文件失败: {e}")


def mark_proxy_exhausted(ip):
    """标记代理次数用尽"""
    with PROXY_LOCK:
        found = False
        for p in GLOBAL_PROXIES:
            if p.get("ip") == ip:
                p["exhausted"] = True
                print(f"代理 {ip} 已标记为耗尽")
                found = True
                break
        if not found:
            print(f"警告：尝试标记未知的代理 {ip}")
    save_proxies()


def increment_proxy_count(ip):
    """增加代理使用次数"""
    with PROXY_LOCK:
        for p in GLOBAL_PROXIES:
            if p.get("ip") == ip:
                p["count"] = p.get("count", 0) + 1
                break
    save_proxies()


def check_proxy(proxy):
    if "://" not in proxy:
        proxy_url = f"socks5://{proxy}"
    else:
        proxy_url = proxy

    test_url = "http://httpbin.org/ip"
    proxies = {
        "http": proxy_url,
        "https": proxy_url,
    }
    try:
        response = requests.get(test_url, proxies=proxies, timeout=5)
        if response.status_code == 200:
            print(f"代理可用: {proxy_url}")
            return True, proxy_url
        else:
            print(f"代理不可用: {proxy_url}，状态码: {response.status_code}")
            return False, proxy_url
    except requests.RequestException as e:
        print(f"代理不可用: {proxy_url}，错误: {e}")
        return False, proxy_url


def get_valid_proxy():
    """从全局代理列表中获取一个可用的代理（排除已耗尽且未过期的）"""
    with PROXY_LOCK:
        # 筛选未耗尽且未过期的代理
        available = [
            p
            for p in GLOBAL_PROXIES
            if not p.get("exhausted", False) and not p.get("expired", False)
        ]

    if not available:
        return False, None, None

    # 随机打乱
    local_available = list(available)
    random.shuffle(local_available)

    for proxy_info in local_available:
        raw_ip = proxy_info["ip"]
        is_valid, proxy_with_scheme = check_proxy(raw_ip)
        if is_valid:
            return True, proxy_with_scheme, raw_ip

    return False, None, None


def get_count_from_page(page):
    try:
        tmp_count = page.ele("text:今日剩余")
        if tmp_count:
            print(f"页面显示今日剩余: {tmp_count.text}")

            text = tmp_count.text

            # 解析剩余次数 的数字
            match = re.search(r"\d+", text)
            if match:
                remaining_count = int(match.group(0))
                print(f"解析到今日剩余次数: {remaining_count}")
                return remaining_count
        else:
            no_count = page.ele("text:今日次数已用完")
            if no_count:
                print("页面显示今日次数已用完。")
                return 0
            print("未找到今日剩余元素，可能需要登录或页面有问题。")
    except Exception as e:
        print(f"获取今日次数失败: {e}")
    return None


def open_ai_check_page(browser, url=None):
    """打开 AI 检测页面，并进行指纹注入和清理"""
    try:
        page = browser.latest_tab

        # 访问页面
        page.get(url)

        # 注入 Canvas 干扰脚本
        canvas_noise_js = """
        const set_noise = (proto, name) => {
            const old_func = proto[name];
            proto[name] = function() {
                const res = old_func.apply(this, arguments);
                return res + (Math.random() > 0.5 ? " " : "");
            };
        };
        """
        page.add_init_js(canvas_noise_js)

        # 清空 localStorage
        page.add_init_js("localStorage.clear(); sessionStorage.clear();")

        # 访问页面
        page.get(url)

        # 查看指纹（可选）
        current_fp = page.run_js('return localStorage.getItem("fp");')
        print(f"当前指纹: {current_fp}")

        # 获取今日剩余次数
        remaining_count = get_count_from_page(page)

        if remaining_count is None:
            print("未能获取今日剩余次数。")
            return page, False, "error"

        if remaining_count <= 0:
            print("今日次数已用完。")
            return page, False, "exhausted"

        return page, True, "ok"
    except Exception as e:
        print(f"打开页面出错: {e}")
        return None, False, "error"


def check_upload_status(log_text):
    match = re.search(r"(\d+(?:\.\d+)?)%", log_text)
    if match:
        percent_val = float(match.group(1))
        print(f"当前解析进度: {percent_val}%")
        if percent_val >= 100.0:
            return True
    return False


def upload_file(page, file_path):
    """长传图片和保存结果"""
    print(f"准备上传文件: {file_path}")

    # 设置监听上传
    page.set.upload_files(file_path)

    full_selector = "css:div.img-wrapper.show-gesture"
    print(f"正在查找元素: {full_selector}")

    target_ele = page.ele(full_selector, timeout=15)

    if target_ele:
        print("找到元素，准备上传...")
        page.set.upload_files(file_path)
        target_ele.click()
        print("已点击，等待路径自动填充...")

        try:
            # 启动控制台日志监听
            page.console.start()

            page.wait.upload_paths_inputted()
            print(f"上传路径{file_path}填入成功！")

            data = page.console.steps()

            print("等待上传完成...")
            for log in data:
                log_text = log.text
                if "上传进度" in log_text:
                    match = re.search(r"(\d+(?:\.\d+)?)%", log_text)
                    if match:
                        percent = float(match.group(1))
                        # print(f"当前上传进度: {percent}%")
                        if percent >= 100.0:
                            print("上传已完成。")
                            break
                else:
                    print(f"控制台日志: {log_text}")
                    pass

            time.sleep(10)

            ai_score_ele = page.ele("text:嗅探到AI浓度", timeout=60)  # 嗅探到AI浓度元素

            if not ai_score_ele:
                print("等待结果超时！")
                return
            else:
                print("检测界面已生成。")

            # 循环等待服务器返回结果
            start_time = time.time()
            found_result = False

            # 等待结果出现数字
            while time.time() - start_time < 300:  # 最多等待5分钟
                ai_score_ele = page.ele("text:嗅探到AI浓度")
                ai_score_ele_text = ai_score_ele.parent(2).text if ai_score_ele else ""

                print(f"当前检测结果文本: {ai_score_ele_text}")

                # 正则检查里面是否有数字
                print("检查结果中是否包含数字...")
                if re.search(r"\d+", ai_score_ele_text):
                    found_result = True
                    print("检测结果已生成。")
                    break

                # 延迟5秒后重试
                time.sleep(5)

            if not found_result:
                print("等待结果超时！")
                return

            # 找 ai_score_ele 三级父元素
            ai_score_par_ele = ai_score_ele.parent(3)
            res = ai_score_par_ele.text

            # 提取视频的名字作为文件名
            video_name = os.path.basename(file_path).split(".")[0]

            # 结果存放
            res_dir = "results"
            if not os.path.exists(res_dir):
                os.makedirs(res_dir)

            res_file = os.path.join(res_dir, f"{video_name}.txt")
            with open(res_file, "w", encoding="utf-8") as f:
                f.write(res)

            print(f"检测结果已保存到 {res_file}")

            # 刷新页面准备下一次（虽然外层逻辑可能会重启）
            page.refresh()

            # 等待 30 秒
            print("等待 30 秒后继续...防止上传过快")
            time.sleep(2 * 60)

        except Exception as e:
            print(f"上传或保存过程中出错: {e}")
            raise e
    else:
        print("错误：未找到上传元素。")
        raise Exception("Upload element not found")


def setOptions(thread_id=None):
    """
    设置浏览器选项
    """
    co = ChromiumOptions()

    # 为每个线程设置独立的用户数据目录，避免锁冲突
    # 获取当前日期时间作为目录名的一部分
    now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    user_data_dir = rf"chrome_user_data_{now_str}"
    if thread_id is not None:
        user_data_dir = f"{user_data_dir}"

    co.set_user_data_path(user_data_dir)

    co.use_system_user_path(False)
    co.set_cache_path(os.path.join(user_data_dir, "cache"))

    co.auto_port()  # 自动分配端口
    co.set_user_agent(
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
    )

    co.new_env()
    co.incognito()

    co.set_argument("--disable-reading-from-canvas")
    co.set_argument("--disable-webrtc")

    return co


def worker_task(thread_id, task_queue, url, app_log_func=None, update_proxy_ui=None):
    """
    工作线程函数
    """
    import os

    def log(msg):
        # 增加 Process ID 和 Thread ID
        process_id = os.getpid()
        # thread_id 已经在闭包里，这里主要是为了显示更完整的系统级线程 ID（可选）
        thread_native_id = threading.get_native_id()
        msg = f"[PID:{process_id}][TID:{thread_native_id}][线程 {thread_id}] {msg}"
        print(msg)
        if app_log_func:
            app_log_func(msg)

    log("启动...")

    browser = None
    current_proxy_raw_ip = None  # 用于记录当前使用的原始IP，以便标记耗尽

    while True:
        # 获取任务
        try:
            # 如果浏览器没准备好，先不取任务，或者取了之后再处理浏览器
            if task_queue.empty():
                log("任务队列为空，尝试退出...")
                break

            file_path = task_queue.get(timeout=3)
            log(f"获取任务成功: {file_path}")
        except Empty:
            log("获取任务超时(Empty)，退出...")
            break

        # 确保浏览器可用且有次数
        retry_browser_count = 0
        while retry_browser_count < 5:
            if browser is None:
                log("浏览器未初始化，正在初始化...")
                # 初始化浏览器
                co = setOptions(thread_id)

                if USE_PROXY:
                    log("正在获取可用代理...")
                    is_valid, ip_proxy_scheme, raw_ip = get_valid_proxy()
                    if is_valid:
                        log(f"获取代理成功: {raw_ip}")
                        co.set_proxy(ip_proxy_scheme)
                        current_proxy_raw_ip = raw_ip
                    else:
                        log("无可用代理，等待 5s 重试...")
                        time.sleep(5)
                        retry_browser_count += 1
                        continue

                try:
                    log("正在启动 Chromium 实例...")
                    browser = Chromium(addr_or_opts=co)
                    log("Chromium 实例启动成功")
                except Exception as e:
                    log(f"启动浏览器失败: {e}")
                    browser = None
                    retry_browser_count += 1
                    time.sleep(2)
                    continue

            # 检查次数
            log(f"正在打开检测页面: {url}")
            page, has_count, reason = open_ai_check_page(browser, url)

            if not has_count:
                log(f"检测到无次数或页面错误({reason})，关闭浏览器重试...")

                # 如果是因为耗尽，标记并在全局中禁用该代理
                if reason == "exhausted" and current_proxy_raw_ip:
                    log(f"代理 {current_proxy_raw_ip} 次数耗尽，标记并在UI刷新")
                    mark_proxy_exhausted(current_proxy_raw_ip)
                    if update_proxy_ui:
                        update_proxy_ui()
                    current_proxy_raw_ip = None  # Reset

                if browser:
                    log("正在退出当前浏览器实例...")
                    browser.quit()
                    browser = None
                retry_browser_count += 1
                continue
            else:
                log("页面状态正常，次数可用，准备执行任务")
                # 浏览器正常且有次数
                break

        # 如果重试多次还是没有可用浏览器，放弃当前任务（或者放回队列）
        if browser is None:
            log(f"无法建立有效浏览器环境，放弃任务: {file_path}")
            task_queue.task_done()
            continue

        # 执行任务
        try:
            log(f"开始处理: {os.path.basename(file_path)}")
            upload_file(page, file_path)
            log(f"完成处理: {os.path.basename(file_path)}")
            if current_proxy_raw_ip:
                increment_proxy_count(current_proxy_raw_ip)
                if update_proxy_ui:
                    update_proxy_ui()

        except Exception as e:
            log(f"处理 {os.path.basename(file_path)} 失败: {e}")
            # 这里的异常可能是页面崩溃等，尝试重启浏览器
            if browser:
                log("因为任务处理异常，尝试重启浏览器...")
                try:
                    browser.quit()
                except:
                    pass
                browser = None

        finally:
            log(f"任务 {file_path} 标记完成")
            task_queue.task_done()

    # 退出前清理
    if browser:
        log("清理资源: 关闭浏览器")
        browser.quit()
    log("线程结束")


class ProxyManagerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("AI Check 代理管理与执行")
        self.root.geometry("800x600")

        self.setup_ui()

        # 清理旧的 Chrome 用户数据
        clean_chrome_user_data()

        # 加载数据
        load_proxies()
        self.refresh_table()

    def setup_ui(self):
        # 顶部：代理表格
        frame_top = ttk.LabelFrame(self.root, text="代理列表")
        frame_top.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # 定义列
        columns = ("ip", "port", "expire_time", "status", "connectivity", "count")
        self.tree = ttk.Treeview(frame_top, columns=columns, show="headings")
        self.tree.heading("ip", text="IP")
        self.tree.heading("port", text="端口")
        self.tree.heading("expire_time", text="过期时间")
        self.tree.heading("status", text="状态")
        self.tree.heading("connectivity", text="连通性")
        self.tree.heading("count", text="使用次数")

        self.tree.column("ip", width=150)
        self.tree.column("port", width=60)
        self.tree.column("expire_time", width=140)
        self.tree.column("status", width=80)
        self.tree.column("connectivity", width=80)
        self.tree.column("count", width=60)

        # 滚动条
        scrollbar = ttk.Scrollbar(
            frame_top, orient=tk.VERTICAL, command=self.tree.yview
        )
        self.tree.configure(yscroll=scrollbar.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 中部：操作按钮
        frame_mid = ttk.Frame(self.root)
        frame_mid.pack(fill=tk.X, padx=10, pady=5)

        ttk.Button(frame_mid, text="添加代理", command=self.add_proxy).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(frame_mid, text="批量添加", command=self.batch_add_proxy).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(frame_mid, text="编辑选定", command=self.edit_proxy).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(frame_mid, text="删除选定", command=self.delete_proxy).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(frame_mid, text="重置状态", command=self.reset_status).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(frame_mid, text="刷新列表", command=self.refresh_table).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(
            frame_mid, text="检查联通性", command=self.check_all_connectivity
        ).pack(side=tk.LEFT, padx=5)

        # 底部：日志与控制
        frame_bottom = ttk.LabelFrame(self.root, text="执行控制")
        frame_bottom.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # 启动配置区域
        frame_ctrl = ttk.Frame(frame_bottom)
        frame_ctrl.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(frame_ctrl, text="视频目录:").pack(side=tk.LEFT)
        self.video_dir_var = tk.StringVar(value="测试视频")
        ttk.Entry(frame_ctrl, textvariable=self.video_dir_var, width=20).pack(
            side=tk.LEFT, padx=5
        )

        ttk.Label(frame_ctrl, text="线程数:").pack(side=tk.LEFT)
        self.workers_var = tk.StringVar(value="1")
        ttk.Entry(frame_ctrl, textvariable=self.workers_var, width=5).pack(
            side=tk.LEFT, padx=5
        )

        self.start_btn = ttk.Button(
            frame_ctrl, text="开始处理任务", command=self.start_processing
        )
        self.start_btn.pack(side=tk.LEFT, padx=20)

        # 日志区域
        self.log_text = tk.Text(frame_bottom, height=10)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def log(self, msg):
        """Append log to text widget, thread-safe way"""

        def _append():
            self.log_text.insert(tk.END, msg + "\n")
            self.log_text.see(tk.END)

        self.root.after(0, _append)

    def refresh_table(self):
        """刷新代理列表显示"""
        # 清空
        for i in self.tree.get_children():
            self.tree.delete(i)

        with PROXY_LOCK:
            # 读取 global proxies
            for idx, p in enumerate(GLOBAL_PROXIES):
                ip_raw = p.get("ip", "")
                if ":" in ip_raw:
                    ip_part, port_part = ip_raw.split(":", 1)
                else:
                    ip_part, port_part = ip_raw, ""

                exhausted = p.get("exhausted", False)
                expired = p.get("expired", False)
                expire_time = p.get("expire_time", "")

                connectivity = p.get("connectivity", "未检查")

                if expired:
                    status = "过期"
                elif exhausted:
                    status = "耗尽"
                else:
                    status = "正常"

                count = p.get("count", 0)

                # 插入树
                # 存储 idx 在 tags 或 values 里方便后续查找
                # 这里用 iid=idx
                self.tree.insert(
                    "",
                    tk.END,
                    iid=str(idx),
                    values=(
                        ip_part,
                        port_part,
                        expire_time,
                        status,
                        connectivity,
                        count,
                    ),
                )

    def update_proxy_ui_safe(self):
        """从线程安全调用刷新"""
        self.root.after(0, self.refresh_table)

    def check_all_connectivity(self):
        """检查所有代理的连通性"""

        def _check_task():
            self.log("开始检查所有代理连通性...")

            with PROXY_LOCK:
                proxies_to_check = list(GLOBAL_PROXIES)

            total = len(proxies_to_check)
            for idx, p in enumerate(proxies_to_check):
                self.log(f"正在检查代理 ({idx + 1}/{total}): {p['ip']}")
                try:
                    is_valid, _ = check_proxy(p["ip"])
                    with PROXY_LOCK:
                        p["connectivity"] = "通" if is_valid else "不通"
                except Exception as e:
                    with PROXY_LOCK:
                        p["connectivity"] = "错误"

            self.log("所有代理检查完成")
            self.update_proxy_ui_safe()

        threading.Thread(target=_check_task, daemon=True).start()

    def edit_proxy(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("提示", "请先选择要编辑的行")
            return

        if len(selected) > 1:
            messagebox.showinfo("提示", "一次只能编辑一行")
            return

        iid = selected[0]
        item = self.tree.item(iid)
        # values: (ip, port, expire_time, status, count)
        vals = item["values"]
        current_ip_part = str(vals[0])
        current_port_part = str(vals[1])
        current_expire_time = str(vals[2]) if str(vals[2]) != "None" else ""
        current_status_str = str(vals[3])

        # 还原原始 full_ip 用以查找
        original_full_ip = current_ip_part
        if current_port_part and current_port_part != "None":
            original_full_ip += f":{current_port_part}"

        # 创建编辑窗口
        dialog = tk.Toplevel(self.root)
        dialog.title("编辑代理")
        dialog.geometry("300x400")

        # Make modal
        dialog.transient(self.root)
        dialog.grab_set()

        # IP
        ttk.Label(dialog, text="IP地址:").pack(pady=(10, 0), padx=20, anchor=tk.W)
        ip_var = tk.StringVar(value=current_ip_part)
        ttk.Entry(dialog, textvariable=ip_var).pack(pady=5, padx=20, fill=tk.X)

        # Port
        ttk.Label(dialog, text="端口:").pack(pady=(10, 0), padx=20, anchor=tk.W)
        port_display = current_port_part if current_port_part != "None" else ""
        port_var = tk.StringVar(value=port_display)
        ttk.Entry(dialog, textvariable=port_var).pack(pady=5, padx=20, fill=tk.X)

        # Expire Time
        ttk.Label(dialog, text="过期时间 (YYYY-MM-DD HH:MM:SS):").pack(
            pady=(10, 0), padx=20, anchor=tk.W
        )
        expire_var = tk.StringVar(value=current_expire_time)
        ttk.Entry(dialog, textvariable=expire_var).pack(pady=5, padx=20, fill=tk.X)

        # Status
        ttk.Label(dialog, text="状态:").pack(pady=(10, 0), padx=20, anchor=tk.W)
        # Handle "过期" status in combo
        combo_vals = ["正常", "耗尽", "过期"]
        if current_status_str not in combo_vals:
            current_status_str = "正常"
        status_var = tk.StringVar(value=current_status_str)
        status_combo = ttk.Combobox(
            dialog, textvariable=status_var, values=combo_vals, state="readonly"
        )
        status_combo.pack(pady=5, padx=20, fill=tk.X)

        def save_edit():
            new_ip = ip_var.get().strip()
            new_port = port_var.get().strip()
            new_expire = expire_var.get().strip()
            new_status_str = status_var.get()

            if not new_ip:
                messagebox.showerror("错误", "IP不能为空", parent=dialog)
                return

            new_full_ip = new_ip
            if new_port:
                new_full_ip += f":{new_port}"

            new_exhausted = new_status_str == "耗尽"

            if new_expire:
                try:
                    datetime.strptime(new_expire, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    try:
                        datetime.strptime(new_expire, "%Y-%m-%d %H:%M")
                    except ValueError:
                        messagebox.showerror(
                            "错误",
                            "过期时间格式错误，应为 YYYY-MM-DD HH:MM:SS",
                            parent=dialog,
                        )
                        return

            def _run_save():
                try:
                    warning_msg = None
                    error_msg = None
                    should_save = False

                    # 1. 内存修改（持有锁）
                    with PROXY_LOCK:
                        # 查重
                        if new_full_ip != original_full_ip:
                            for p in GLOBAL_PROXIES:
                                if p["ip"] == new_full_ip:
                                    warning_msg = "该代理(IP:Port)已存在"
                                    break

                        if not warning_msg:
                            found = False
                            for p in GLOBAL_PROXIES:
                                if p["ip"] == original_full_ip:
                                    p["ip"] = new_full_ip
                                    p["exhausted"] = new_exhausted
                                    p["expire_time"] = new_expire

                                    # Update expired status immediately
                                    p["expired"] = False
                                    if new_expire:
                                        try:
                                            exp_dt = datetime.strptime(
                                                new_expire, "%Y-%m-%d %H:%M:%S"
                                            )
                                            if datetime.now() > exp_dt:
                                                p["expired"] = True
                                        except:
                                            try:
                                                exp_dt = datetime.strptime(
                                                    new_expire, "%Y-%m-%d %H:%M"
                                                )
                                                if datetime.now() > exp_dt:
                                                    p["expired"] = True
                                            except:
                                                pass

                                    found = True
                                    should_save = True
                                    break
                            if not found:
                                error_msg = "原代理未找到，可能已被其它线程修改"

                    # 2. 界面反馈与保存（释放锁后）
                    if warning_msg:
                        self.root.after(
                            0,
                            lambda: messagebox.showwarning(
                                "提示", warning_msg, parent=dialog
                            ),
                        )
                        return

                    if error_msg:
                        self.root.after(
                            0,
                            lambda: messagebox.showerror(
                                "错误", error_msg, parent=dialog
                            ),
                        )
                        return

                    if should_save:
                        # save_proxies 内部会再次获取锁，所以必须在 with PROXY_LOCK 块之外调用，防止死锁
                        save_proxies()
                        self.root.after(
                            0, lambda: [self.refresh_table(), dialog.destroy()]
                        )

                except Exception as e:
                    print(f"保存异常: {e}")

            threading.Thread(target=_run_save, daemon=True).start()

        ttk.Button(dialog, text="保存修改", command=save_edit).pack(pady=20)

    def add_proxy(self):
        proxy_str = simpledialog.askstring("添加代理", "请输入代理 (IP:Port):")
        if proxy_str:
            proxy_str = proxy_str.strip()
            # 简单的验证
            if ":" not in proxy_str and len(proxy_str) > 0:
                # 也许是socks5 ip? 假设用户输入标准 ip:port
                pass

            if proxy_str:
                with PROXY_LOCK:
                    # 检查重复
                    for p in GLOBAL_PROXIES:
                        if p["ip"] == proxy_str:
                            messagebox.showinfo("提示", "该代理已存在")
                            return

                    GLOBAL_PROXIES.append(
                        {"ip": proxy_str, "exhausted": False, "count": 0}
                    )

                save_proxies()
                self.refresh_table()

    def batch_add_proxy(self):
        # 创建新的顶级窗口
        top = tk.Toplevel(self.root)
        top.title("批量添加代理")
        top.geometry("600x500")

        ttk.Label(top, text="请粘贴 JSON 格式的代理数据:").pack(
            padx=10, pady=5, anchor=tk.W
        )
        ttk.Label(
            top,
            text="示例结构: {'success': 'true', 'data': [{'ip': '1.2.3.4:8080'}, ...]}",
        ).pack(padx=10, pady=(0, 5), anchor=tk.W)

        text_area = tk.Text(top, wrap=tk.WORD)
        text_area.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # 预填示例
        example_json = """{
  "msg": "",
  "code": 0,
  "data": [
    {
      "ip": "218.92.146.4:44839"
    },
    {
      "ip": "218.92.146.7:44698"
    }
  ],
  "success": "true"
}"""
        text_area.insert("1.0", example_json)

        def confirm_batch():
            content = text_area.get("1.0", tk.END).strip()
            if not content:
                return

            try:
                data_obj = json.loads(content)
                new_proxies = []

                # 解析逻辑：主要寻找 list
                proxy_list = []
                if isinstance(data_obj, dict):
                    if "data" in data_obj and isinstance(data_obj["data"], list):
                        proxy_list = data_obj["data"]
                    # 也可以尝试直接查找有没有 list 类型的 value
                elif isinstance(data_obj, list):
                    proxy_list = data_obj

                if not proxy_list:
                    # 尝试寻找包含 IP 的列表
                    pass

                count_added = 0
                with PROXY_LOCK:
                    current_ips = set(p["ip"] for p in GLOBAL_PROXIES)

                    for item in proxy_list:
                        ip_val = None
                        if isinstance(item, dict):
                            ip_val = item.get("ip")
                        elif isinstance(item, str):
                            ip_val = item

                        if ip_val and ip_val not in current_ips:
                            GLOBAL_PROXIES.append(
                                {"ip": ip_val, "exhausted": False, "count": 0}
                            )
                            current_ips.add(ip_val)
                            count_added += 1

                if count_added > 0:
                    save_proxies()
                    self.refresh_table()
                    messagebox.showinfo("成功", f"成功添加 {count_added} 个新代理")
                    top.destroy()
                else:
                    messagebox.showinfo("提示", "未找到新代理或格式不匹配")

            except json.JSONDecodeError:
                messagebox.showerror("错误", "JSON 格式解析失败")
            except Exception as e:
                messagebox.showerror("错误", f"处理失败: {e}")

        ttk.Button(top, text="确认添加", command=confirm_batch).pack(pady=10)

    def delete_proxy(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("提示", "请先选择要删除的行")
            return

        if messagebox.askyesno("确认", f"确定删除选中的 {len(selected)} 个代理?"):
            with PROXY_LOCK:
                # 注意：从后往前删防止索引错乱，但这里 iid 是 str(index)
                # 重新保存需要小心，因为 iid 是 load 时的 index，如果中间有删除，iid 会对应不上
                # 更好的方法是根据 ip 来删

                ips_to_delete = []
                for iid in selected:
                    item = self.tree.item(iid)
                    # values: (ip, port, status, count)
                    full_ip = (
                        f"{item['values'][0]}:{item['values'][1]}"
                        if item["values"][1]
                        else item["values"][0]
                    )
                    ips_to_delete.append(full_ip)

                # 过滤
                global GLOBAL_PROXIES
                GLOBAL_PROXIES = [
                    p for p in GLOBAL_PROXIES if p["ip"] not in ips_to_delete
                ]

            save_proxies()
            self.refresh_table()

    def reset_status(self):
        """重置所有代理为正常状态"""
        with PROXY_LOCK:
            for p in GLOBAL_PROXIES:
                p["exhausted"] = False
        save_proxies()
        self.refresh_table()
        messagebox.showinfo("成功", "所有代理状态已重置为正常")

    def start_processing(self):
        video_dir = self.video_dir_var.get()
        if not os.path.exists(video_dir):
            messagebox.showerror("错误", f"目录不存在: {video_dir}")
            return

        try:
            max_workers = int(self.workers_var.get())
        except ValueError:
            messagebox.showerror("错误", "线程数必须是整数")
            return

        self.start_btn.config(state=tk.DISABLED, text="运行中...")

        # 启动后台线程来运行 main logic
        threading.Thread(
            target=self.run_background_tasks, args=(video_dir, max_workers), daemon=True
        ).start()

    def run_background_tasks(self, video_dir, max_workers):
        self.log(f"开始扫描目录: {video_dir}")
        TARGET_URL = "https://matrix.tencent.com/ai-detect/ai_gen"

        files = []
        for ext in ["*.mp4", "*.avi", "*.mov", "*.mkv"]:
            files.extend(glob.glob(os.path.join(video_dir, ext)))

        self.log(f"扫描到 {len(files)} 个视频文件")

        if not files:
            self.log("没有文件需要处理")
            self.reset_btn_state()
            return

        task_queue = Queue()
        res_dir = "results"

        count_added = 0
        for f in files:
            file_path_abs = os.path.abspath(f)

            # 检查结果是否已存在
            video_name = os.path.basename(f).split(".")[0]
            res_file_check = os.path.join(res_dir, f"{video_name}.txt")
            if os.path.exists(res_file_check):
                # self.log(f"跳过(已存在): {os.path.basename(f)}")
                continue

            # 检查文件大小
            try:
                size_mb = os.path.getsize(file_path_abs) / (1024 * 1024)
                if size_mb > 200:
                    self.log(f"跳过(>200MB): {os.path.basename(f)}")
                    continue
            except Exception as e:
                self.log(f"文件错误: {f}, {e}")
                continue

            task_queue.put(file_path_abs)
            count_added += 1

        self.log(f"实际进入队列任务数: {count_added}")
        if count_added == 0:
            self.log("所有文件均已处理或被跳过。")
            self.reset_btn_state()
            return

        threads = []
        for i in range(max_workers):
            t = threading.Thread(
                target=worker_task,
                args=(i, task_queue, TARGET_URL, self.log, self.update_proxy_ui_safe),
            )
            t.start()
            threads.append(t)

        for t in threads:
            t.join()

        self.log("--- 所有任务处理完成 ---")
        self.reset_btn_state()

    def reset_btn_state(self):
        self.root.after(
            0, lambda: self.start_btn.config(state=tk.NORMAL, text="开始处理任务")
        )


if __name__ == "__main__":
    if "DISPLAY" not in os.environ and os.name != "nt":
        # 针对某些无头环境的提示，虽然用户说要界面
        pass

    root = tk.Tk()
    app = ProxyManagerApp(root)
    root.mainloop()
