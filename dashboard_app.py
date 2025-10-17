import streamlit as st
import pandas as pd
import glob
import os
import json
import urllib.request
from datetime import datetime, timezone
from streamlit_autorefresh import st_autorefresh

# --- CONFIG ---
SHARED_FOLDER = r"\\103.86.55.183\recording\SystemLogs"
SERVER_IP = "103.86.55.183"
REFRESH_SECONDS = 5

st.set_page_config(page_title="Network & Browser Dashboard", layout="wide")
st.title("Realtime Network & Browser Dashboard")

# --- UTILITIES ---
def get_external_ip():
    try:
        return urllib.request.urlopen('https://api.ipify.org').read().decode('utf-8')
    except Exception:
        return "Unknown"

def read_ndjson_files(path_pattern, max_files=12):
    """Read recent NDJSON files and return list of records."""
    files = sorted(glob.glob(path_pattern), key=os.path.getmtime, reverse=True)[:max_files]
    rows = []
    for f in files:
        try:
            with open(f, "r", encoding="utf-8") as fh:
                for line in fh:
                    try:
                        rows.append(json.loads(line.strip()))
                    except:
                        continue
        except:
            continue
    return rows

# --- LOAD PC FOLDERS ---
pc_folders = []
try:
    for entry in os.listdir(SHARED_FOLDER):
        full = os.path.join(SHARED_FOLDER, entry)
        if os.path.isdir(full):
            pc_folders.append(entry)
except Exception as e:
    st.error(f"❌ Could not access shared folder:\n```\n{e}\n```")
    st.stop()

# --- VIEW MODE ---
st.markdown("### PC Selection Mode")
view_mode = st.radio("Choose view:", ["📊 Combined View (All PCs)", "🖥️ Individual PC View"], horizontal=True)

if view_mode == "📊 Combined View (All PCs)":
    pc_choice = "All"
    st.success("Viewing combined data from all monitored PCs")
else:
    pc_choice = st.selectbox(
        "Select specific PC:",
        sorted(pc_folders, reverse=True),
        help=f"Available PCs: {', '.join(sorted(pc_folders))}"
    )

st.markdown("---")
show_count = st.slider("How many recent files to read per PC", 1, 20, 8)

if pc_choice == "All":
    browser_pattern = os.path.join(SHARED_FOLDER, "*", "browser_*.ndjson")
    network_pattern = os.path.join(SHARED_FOLDER, "*", "network_*.ndjson")
else:
    browser_pattern = os.path.join(SHARED_FOLDER, pc_choice, "browser_*.ndjson")
    network_pattern = os.path.join(SHARED_FOLDER, pc_choice, "network_*.ndjson")

# --- READ DATA ---
with st.spinner("Loading recent data..."):
    browser_docs = read_ndjson_files(browser_pattern, max_files=show_count)
    network_docs = read_ndjson_files(network_pattern, max_files=show_count)

df_browser = pd.DataFrame(browser_docs) if browser_docs else pd.DataFrame(columns=["timestamp", "url", "title"])
df_net = pd.DataFrame(network_docs) if network_docs else pd.DataFrame(columns=["timestamp", "status", "laddr", "raddr", "pid", "process"])

if "timestamp" in df_browser.columns:
    df_browser["timestamp"] = pd.to_datetime(df_browser["timestamp"], errors="coerce")
if "timestamp" in df_net.columns:
    df_net["timestamp"] = pd.to_datetime(df_net["timestamp"], errors="coerce")

# --- LAYOUT ---
col1, col2 = st.columns(2)

with col1:
    st.subheader("Recent Browser History")
    total_browser_files = (
        len(glob.glob(browser_pattern))
        if pc_choice != "All"
        else sum(len(glob.glob(os.path.join(SHARED_FOLDER, pc, "browser_*.ndjson"))) for pc in pc_folders)
    )
    st.write(f"Total browser files: {total_browser_files} | Showing latest {len(df_browser)} entries")
    st.dataframe(df_browser.head(500), width='stretch')

with col2:
    st.subheader("Recent Network Connections")
    total_network_files = (
        len(glob.glob(network_pattern))
        if pc_choice != "All"
        else sum(len(glob.glob(os.path.join(SHARED_FOLDER, pc, "network_*.ndjson"))) for pc in pc_folders)
    )
    st.write(f"Total network files: {total_network_files} | Showing latest {len(df_net)} entries")
    st.dataframe(df_net.head(500), width='stretch')

# --- PC INFO SECTION ---
st.subheader("PC Information")

if pc_folders:
    st.markdown("### PC Status Overview")
    num_cols = min(len(pc_folders), 4)
    cols = st.columns(num_cols)

    pc_info = []
    for pc in sorted(pc_folders):
        browser_count = len(glob.glob(os.path.join(SHARED_FOLDER, pc, "browser_*.ndjson")))
        network_count = len(glob.glob(os.path.join(SHARED_FOLDER, pc, "network_*.ndjson")))

        # Extract external IP from latest network file
        pc_ip = "Unknown"
        pc_network_files = glob.glob(os.path.join(SHARED_FOLDER, pc, "network_*.ndjson"))
        if pc_network_files:
            recent_file = max(pc_network_files, key=os.path.getmtime)
            try:
                with open(recent_file, "r", encoding="utf-8") as f:
                    for line_num, line in enumerate(f):
                        if line_num >= 5:
                            break
                        try:
                            data = json.loads(line.strip())
                            if "external_ip" in data and data["external_ip"] not in ("Unknown", ""):
                                pc_ip = data["external_ip"]
                                break
                        except:
                            continue
            except:
                pass

        if pc_ip == "Unknown":
            pc_ip = SERVER_IP

        pc_info.append({
            'name': pc,
            'ip': pc_ip,
            'browser_files': browser_count,
            'network_files': network_count
        })

    # Display PC cards
    for idx, pc_data in enumerate(pc_info):
        col_idx = idx % num_cols
        with cols[col_idx]:
            status_icon = "🟢" if pc_data['network_files'] > 0 else "🔴"
            st.markdown(f"#### {status_icon} {pc_data['name']}")
            st.caption(f"📡 IP: {pc_data['ip']}")
            st.caption(f"🌐 Browser Files: {pc_data['browser_files']}")
            st.caption(f"💾 Network Files: {pc_data['network_files']}")

            all_files = glob.glob(os.path.join(SHARED_FOLDER, pc_data['name'], "*.ndjson"))
            if all_files:
                latest_file = max(all_files, key=os.path.getmtime)
                last_activity = datetime.fromtimestamp(os.path.getmtime(latest_file), tz=timezone.utc)
                minutes_ago = (datetime.now(timezone.utc) - last_activity).total_seconds() / 60
                if minutes_ago < 60:
                    st.caption(f"🕐 Active {int(minutes_ago)} min ago")
                elif minutes_ago < 1440:
                    st.caption(f"🕐 Active {int(minutes_ago/60)} hours ago")
                else:
                    st.caption(f"🕐 Active {int(minutes_ago/1440)} days ago")

st.markdown("---")

# --- SUMMARY METRICS ---
if pc_choice == "All":
    st.subheader("📊 Combined Network Activity")
else:
    st.subheader(f"🖥️ PC Details: {pc_choice}")

colA, colB, colC, colD = st.columns(4)
colA.metric("Browser Entries", len(df_browser))
colB.metric("Network Rows", len(df_net))
colC.metric("Unique Remote IPs", df_net["raddr"].nunique() if not df_net.empty else 0)
colD.metric("Unique Processes", df_net["process"].nunique() if not df_net.empty else 0)

# --- AUTO REFRESH ---
st.caption(f"🔄 Auto-refresh every {REFRESH_SECONDS}s")
st_autorefresh(interval=REFRESH_SECONDS * 1000, key="data_refresh")
