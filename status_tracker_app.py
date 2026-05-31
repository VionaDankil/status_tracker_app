import streamlit as st
import datetime
import json
import os
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ==========================================
# CONFIGURATION & CONSTANTS
# ==========================================
# ID aus der URL deines Google Docs extrahieren (nur der lange Code zwischen /d/ und /edit)
GOOGLE_DOC_ID = "1XIXRNMjvnHXU5HTWUP31GFIy1eXiqAcvhWV-3C7RvkA" 
LOCAL_DATA_FILE = "todo_tasks.json"
CREDENTIALS_FILE = "google_credentials.json"

SCOPES = ["https://www.googleapis.com/auth/documents"]

# Setzt das Seitenlayout der Streamlit App auf "Weit"
st.set_page_config(page_title="Solo Status Tracker & Logger", layout="wide", page_icon="🚀")

# ==========================================
# DATENMANAGEMENT (LOCAL STORAGE)
# ==========================================
def load_local_tasks():
    """Lädt die Aufgaben aus einer lokalen JSON-Datei (oder dem Session State in der Cloud)."""
    if os.path.exists(LOCAL_DATA_FILE):
        try:
            with open(LOCAL_DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_local_tasks(tasks):
    """Speichert die Aufgaben lokal ab."""
    try:
        with open(LOCAL_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(tasks, f, ensure_ascii=False, indent=4)
    except Exception:
        # In der Streamlit Cloud ist das Schreiben auf Festplatte manchmal eingeschränkt.
        # Der Session State hält die Daten temporär im RAM.
        pass

# Initialisiere den Session State von Streamlit
if "tasks" not in st.session_state:
    st.session_state.tasks = load_local_tasks()

# ==========================================
# GOOGLE DOCS INTEGRATION (LOGGER)
# ==========================================
def get_google_credentials():
    """Lädt Credentials entweder aus den Streamlit Secrets (Cloud) oder lokal aus der JSON."""
    # 1. Versuch: Aus den Streamlit Secrets laden (Produktion / Cloud)
    if "google_credentials" in st.secrets:
        creds_dict = dict(st.secrets["google_credentials"])
        return service_account.Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    
    # 2. Versuch: Lokal aus der Datei laden (Entwicklung)
    elif os.path.exists(CREDENTIALS_FILE):
        return service_account.Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    
    else:
        return None

def log_to_google_doc(task_title, priority, started_at, process_note):
    """Schreibt die erledigte Aufgabe in Google Docs."""
    creds = get_google_credentials()
    
    if not creds:
        st.warning("⚠️ Keine Google-Zugangsdaten gefunden (weder lokal noch in den Streamlit Secrets).")
        return False

    try:
        service = build("docs", "v1", credentials=creds)

        # Zeitstempel berechnen
        now = datetime.datetime.now()
        done_time_str = now.strftime("%d.%m.%Y um %H:%M:%S Uhr")
        
        # Dauer berechnen, falls Startzeitpunkt vorhanden
        duration_str = "Nicht getrackt"
        if started_at:
            start_time = datetime.datetime.fromisoformat(started_at)
            duration = now - start_time
            hours, remainder = divmod(duration.total_seconds(), 3600)
            minutes, _ = divmod(remainder, 60)
            if hours > 0:
                duration_str = f"{int(hours)} Std. {int(minutes)} Min."
            else:
                duration_str = f"{int(minutes)} Min."

        # Formatierter Text
        log_entry = (
            f"\n==================================================\n"
            f"✅ ERLEDIGT: {task_title}\n"
            f"📅 Abgeschlossen am: {done_time_str}\n"
            f"⏱️ Bearbeitungszeit: {duration_str}\n"
            f"🔥 Priorität: {priority}\n"
            f"📝 Prozess-Notiz / Ergebnis:\n   {process_note if process_note else 'Keine Notiz hinterlegt.'}\n"
            f"==================================================\n"
        )

        requests = [
            {
                "insertText": {
                    "location": {"index": 1},
                    "text": log_entry
                }
            }
        ]

        service.documents().batchUpdate(
            documentId=GOOGLE_DOC_ID, body={"requests": requests}
        ).execute()
        return True
        
    except Exception as e:
        st.error(f"Fehler bei der Übertragung an Google Docs: {e}")
        return False

# ==========================================
# STREAMLIT UI & INTERACTION
# ==========================================

st.title("🚀 Solo Status Tracker")
st.caption("Ein maßgeschneidertes Tool mit automatischem Google-Docs-Prozessprotokoll.")

# Quick-Add Eingabefeld
st.subheader("📝 Neues To-Do hinzufügen")
with st.form("quick_add_form", clear_on_submit=True):
    col_input, col_prio, col_btn = st.columns([5, 2, 1])
    with col_input:
        new_task_title = st.text_input("Was ist zu tun?", placeholder="z.B. Datenbank-Backup automatisieren...")
    with col_prio:
        new_task_prio = st.selectbox("Priorität", ["🔴 Hoch", "🟡 Mittel", "🟢 Niedrig"], index=1)
    with col_btn:
        st.write("<br>", unsafe_allow_html=True)
        submit_button = st.form_submit_button("Hinzufügen")

if submit_button and new_task_title.strip():
    new_task = {
        "id": str(datetime.datetime.now().timestamp()),
        "title": new_task_title.strip(),
        "priority": new_task_prio,
        "status": "todo",
        "created_at": datetime.datetime.now().isoformat(),
        "started_at": None
    }
    st.session_state.tasks.append(new_task)
    save_local_tasks(st.session_state.tasks)
    st.success(f"Task '{new_task_title}' hinzugefügt!")
    st.rerun()

st.markdown("---")

col_todo, col_progress, col_done_dialog = st.columns(3)

# SPALTE 1: TO-DO
with col_todo:
    st.header("📋 Bereit (To-Do)")
    todo_tasks = [t for t in st.session_state.tasks if t["status"] == "todo"]
    
    if not todo_tasks:
        st.info("Keine Aufgaben im Backlog.")
        
    for task in todo_tasks:
        with st.container(border=True):
            st.markdown(f"### {task['title']}")
            st.markdown(f"**Prio:** {task['priority']}")
            
            if st.button("▶️ Arbeit starten", key=f"start_{task['id']}", use_container_width=True):
                task["status"] = "in_progress"
                task["started_at"] = datetime.datetime.now().isoformat()
                save_local_tasks(st.session_state.tasks)
                st.rerun()

# SPALTE 2: IN ARBEIT
with col_progress:
    st.header("⚡ In Arbeit")
    progress_tasks = [t for t in st.session_state.tasks if t["status"] == "in_progress"]
    
    if not progress_tasks:
        st.info("Aktuell ruht die Arbeit.")
        
    for task in progress_tasks:
        with st.container(border=True):
            st.markdown(f"### {task['title']}")
            st.markdown(f"**Prio:** {task['priority']}")
            
            if task["started_at"]:
                start = datetime.datetime.fromisoformat(task["started_at"])
                diff = datetime.datetime.now() - start
                mins = int(diff.total_seconds() // 60)
                st.caption(f"⏱️ Läuft seit: {mins} Minuten")
            
            if st.button("🏁 Abschließen & Loggen", key=f"trigger_done_{task['id']}", use_container_width=True):
                st.session_state.active_done_task = task
                st.rerun()

# SPALTE 3: ABSCHLUSS-DIALOG
with col_done_dialog:
    st.header("📝 Prozess-Archiv")
    
    if "active_done_task" in st.session_state and st.session_state.active_done_task:
        task = st.session_state.active_done_task
        st.success(f"Füge Notizen hinzu für:\n**{task['title']}**")
        
        process_note = st.text_area(
            "Was hast du gemacht?",
            placeholder="z.B. Fehler behoben...",
            key="process_note_input",
            height=150
        )
        
        col_back, col_confirm = st.columns(2)
        with col_back:
            if st.button("Abbrechen", use_container_width=True):
                st.session_state.active_done_task = None
                st.rerun()
                
        with col_confirm:
            if st.button("🚀 In Google Doc posten", type="primary", use_container_width=True):
                with st.spinner("Übertrage Daten an Google Docs..."):
                    success = log_to_google_doc(
                        task_title=task["title"],
                        priority=task["priority"],
                        started_at=task["started_at"],
                        process_note=process_note
                    )
                    
                    if success:
                        st.session_state.tasks.remove(task)
                        save_local_tasks(st.session_state.tasks)
                        st.session_state.active_done_task = None
                        st.toast("Aufgabe erfolgreich archiviert!", icon="🎉")
                        st.rerun()
    else:
        st.info("Klicke bei einer aktiven Aufgabe auf 'Abschließen & Loggen'.")

with st.sidebar:
    st.header("⚙️ App-Optionen & Infos")
    total_open = len(st.session_state.tasks)
    st.metric(label="Offene Aufgaben lokal", value=total_open)
    
    if st.button("🧹 Alle lokalen Daten zurücksetzen"):
        st.session_state.tasks = []
        save_local_tasks([])
        if "active_done_task" in st.session_state:
            st.session_state.active_done_task = None
        st.rerun()
