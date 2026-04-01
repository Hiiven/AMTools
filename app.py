import os
import uuid
import subprocess
import time
import threading
import tempfile
import zipfile
import shutil
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file, after_this_request, make_response

app = Flask(__name__)
app.secret_key = os.urandom(24)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "Apple Music")
COOKIES_FILE = os.path.join(BASE_DIR, "cookies.txt")
OUTPUT_DIR = os.path.join(BASE_DIR, "歌单")

tasks = {}
tasks_lock = threading.Lock()


def get_session_id():
    sid = request.cookies.get("am_session_id")
    if not sid:
        sid = str(uuid.uuid4())
    return sid


def get_task(sid):
    with tasks_lock:
        if sid not in tasks:
            tasks[sid] = {
                "running": False,
                "progress": 0,
                "status": "就绪",
                "logs": [],
                "result": None,
                "zip_path": None,
                "stop_flag": False,
            }
        return tasks[sid]


def append_log(sid, msg):
    with tasks_lock:
        if sid in tasks:
            tasks[sid]["logs"].append(msg)


@app.after_request
def set_session_cookie(response):
    sid = request.cookies.get("am_session_id")
    if not sid:
        sid = str(uuid.uuid4())
        response.set_cookie("am_session_id", sid, max_age=60*60*24*30)
    return response


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/cookies", methods=["POST"])
def handle_cookies():
    if "file" not in request.files:
        return jsonify({"ok": False, "msg": "未选择文件"})
    f = request.files["file"]
    if not f.filename:
        return jsonify({"ok": False, "msg": "未选择文件"})
    content = f.read().decode("utf-8", errors="replace")
    with open(COOKIES_FILE, "w", encoding="utf-8") as fw:
        fw.write(content)
    return jsonify({"ok": True, "msg": "Cookies 已保存"})


@app.route("/api/reset", methods=["POST"])
def reset():
    sid = get_session_id()
    task = get_task(sid)
    with tasks_lock:
        task["logs"] = []
        task["result"] = None
        task["zip_path"] = None
        task["progress"] = 0
        task["status"] = "就绪"
    return jsonify({"ok": True})


@app.route("/api/status")
def status():
    sid = get_session_id()
    task = get_task(sid)
    return jsonify({
        "running": task["running"],
        "progress": task["progress"],
        "status": task["status"],
        "logs": task["logs"],
        "result": task["result"],
    })


@app.route("/api/download", methods=["GET"])
def download():
    sid = get_session_id()
    task = get_task(sid)
    zip_path = task.get("zip_path")
    if not zip_path or not os.path.isfile(zip_path):
        return jsonify({"ok": False, "msg": "无可下载的文件"})
    task["zip_path"] = None

    @after_this_request
    def cleanup(response):
        try:
            os.remove(zip_path)
        except Exception:
            pass
        return response

    return send_file(zip_path, as_attachment=True, download_name="AMTools_MP3.zip", conditional=True)


@app.route("/api/start", methods=["POST"])
def start():
    sid = get_session_id()
    task = get_task(sid)
    if task["running"]:
        return jsonify({"ok": False, "msg": "任务正在运行中"})
    data = request.json or {}
    links = data.get("links", [])
    skip_existing = data.get("skip_existing", True)
    if not links:
        return jsonify({"ok": False, "msg": "请添加至少一个链接"})
    if not os.path.isfile(COOKIES_FILE):
        return jsonify({"ok": False, "msg": "请先上传 cookies.txt"})

    task["running"] = True
    task["progress"] = 0
    task["status"] = "正在启动..."
    task["logs"] = []
    task["result"] = None
    task["zip_path"] = None
    task["stop_flag"] = False

    threading.Thread(target=run_job, args=(sid, links, skip_existing), daemon=True).start()
    return jsonify({"ok": True, "msg": "任务已启动"})


@app.route("/api/stop", methods=["POST"])
def stop():
    sid = get_session_id()
    task = get_task(sid)
    task["running"] = False
    task["stop_flag"] = True
    task["status"] = "已停止"
    return jsonify({"ok": True})


def run_job(sid, links, skip_existing):
    task = get_task(sid)
    t0 = time.time()
    processed = skipped = failed = 0

    def prog(p, s):
        with tasks_lock:
            task["progress"] = p
            task["status"] = s

    def log(msg):
        append_log(sid, msg)

    temp_out = tempfile.mkdtemp(prefix="amtools_")

    existing_mp3 = set()
    if skip_existing and os.path.isdir(OUTPUT_DIR):
        for f in os.listdir(OUTPUT_DIR):
            if f.lower().endswith(".mp3"):
                existing_mp3.add(Path(f).stem.lower())
        if existing_mp3:
            log(f"[增量] 发现 {len(existing_mp3)} 首已有歌曲，将跳过重复下载")

    tmp_urls = os.path.join(tempfile.gettempdir(), f"amdl_urls_{sid[:8]}.txt")
    with open(tmp_urls, "w", encoding="utf-8") as f:
        for link in links:
            f.write(link.strip() + "\n")
    log(f"[配置] 已写入 {len(links)} 个链接")

    log("\n>>> 步骤 1: 开始获取音乐...")
    prog(10, "正在下载...")
    gamdl_cmd = "gamdl"
    proc = None
    try:
        proc = subprocess.Popen(
            [gamdl_cmd, "-r", tmp_urls],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
        )
        for line in proc.stdout:
            line = line.decode('utf-8', errors='replace').strip()
            if line:
                log(f"  {line}")
        proc.wait(timeout=3600)
        if proc.returncode != 0:
            log(f"[警告] gamdl 退出码: {proc.returncode}")
    except subprocess.TimeoutExpired:
        proc.kill()
        log("[错误] 下载超时（>1小时）")
        prog(0, "错误")
        task["running"] = False
        task["result"] = {"ok": False, "processed": 0, "skipped": 0, "failed": 0, "time": "0分0秒"}
        shutil.rmtree(temp_out, ignore_errors=True)
        return
    except Exception as e:
        log(f"[错误] 下载失败: {e}")
        prog(0, "错误")
        task["running"] = False
        task["result"] = {"ok": False, "processed": 0, "skipped": 0, "failed": 0, "time": "0分0秒"}
        shutil.rmtree(temp_out, ignore_errors=True)
        return

    prog(30, "正在转换...")

    log("\n>>> 步骤 2: 转换 MP3 并清理...")
    if os.path.isdir(DOWNLOAD_DIR):
        all_m4a = []
        for root, _, files in os.walk(DOWNLOAD_DIR):
            for file in files:
                if file.lower().endswith(".m4a"):
                    all_m4a.append((root, file))
        total = len(all_m4a)
        if total == 0:
            log("[提示] 未找到任何 m4a 文件")
            prog(100, "完成")
            elapsed = time.time() - t0
            m, s = int(elapsed // 60), int(elapsed % 60)
            task["running"] = False
            task["result"] = {"ok": True, "processed": 0, "skipped": 0, "failed": 0, "time": f"{m}分{s}秒"}
            shutil.rmtree(temp_out, ignore_errors=True)
            return

        log(f"[统计] 共发现 {total} 个音频文件待处理")
        for idx, (root, file) in enumerate(all_m4a):
            with tasks_lock:
                stopped = task["stop_flag"]
            if stopped:
                log("[已停止] 用户取消了任务")
                prog(0, "已停止")
                task["running"] = False
                task["result"] = {"ok": False, "processed": processed, "skipped": skipped, "failed": failed, "time": "已取消"}
                shutil.rmtree(temp_out, ignore_errors=True)
                return

            m4a_path = os.path.join(root, file)
            stem = Path(file).stem
            mp3_filename = stem + ".mp3"
            mp3_path = os.path.join(temp_out, mp3_filename)
            lrc_path = m4a_path.replace(".m4a", ".lrc")

            if skip_existing and stem.lower() in existing_mp3 and os.path.isfile(os.path.join(OUTPUT_DIR, mp3_filename)):
                log(f"[跳过] {file} (已存在)")
                skipped += 1
                prog(30 + int((idx + 1) / total * 70), f"转换中 ({idx+1}/{total})")
                continue

            if os.path.getsize(m4a_path) == 0:
                log(f"[跳过] {file} (文件为空，gamdl 下载可能失败)")
                os.remove(m4a_path)
                failed += 1
                prog(30 + int((idx + 1) / total * 70), f"转换中 ({idx+1}/{total})")
                continue

            log(f"\n[转换] {file}")
            try:
                r = subprocess.run(
                    ["ffmpeg", "-y", "-i", m4a_path, "-codec:a", "libmp3lame", "-b:a", "320k", mp3_path],
                    capture_output=True, text=True, timeout=300,
                )
                if r.returncode != 0:
                    log(f"[失败] {file}: {r.stderr.strip()[:200]}")
                    failed += 1
                    continue
                with open(m4a_path, "w") as f:
                    pass
                if os.path.isfile(lrc_path):
                    os.remove(lrc_path)
                log(f"[完成] {file} -> {mp3_filename}")
                processed += 1
            except Exception as e:
                log(f"[异常] {file}: {e}")
                failed += 1

            prog(30 + int((idx + 1) / total * 70), f"转换中 ({idx+1}/{total})")

    zip_path = None
    if processed > 0:
        zip_path = os.path.join(BASE_DIR, f"AMTools_MP3_{sid[:8]}.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in os.listdir(temp_out):
                if f.lower().endswith(".mp3"):
                    zf.write(os.path.join(temp_out, f), f)
        task["zip_path"] = zip_path
        log(f"\n[打包] 已生成 zip 文件，可点击按钮下载")

    shutil.rmtree(temp_out, ignore_errors=True)

    prog(100, "完成")
    elapsed = time.time() - t0
    m, s = int(elapsed // 60), int(elapsed % 60)
    log(f"\n{'='*40}")
    log(f" 任务完成！成功转换: {processed} 首 | 跳过: {skipped} 首 | 失败: {failed} 首")
    log(f" 总耗时: {m}分{s}秒")
    log(f"{'='*40}")
    task["running"] = False
    task["result"] = {"ok": True, "processed": processed, "skipped": skipped, "failed": failed, "time": f"{m}分{s}秒", "has_download": zip_path is not None}


if __name__ == "__main__":
    print("正在启动 AMTools Web...")
    port = int(os.environ.get("PORT", 7860))
    print(f"请在浏览器中打开 http://localhost:{port}")
    app.run(host='0.0.0.0', port=port)
