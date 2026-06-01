import streamlit as st
import datetime
import json
import os
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ==========================================
# CONFIGURATION & CONSTANTS
# ==========================================
GOOGLE_DOC_ID = "1XIXRNMjvnHXU5HTWUP31GFIy1eXiqAcvhWV-3C7RvkA" 
SCOPES = ["https://www.googleapis.com/auth/documents"]
CREDENTIALS_FILE = "google_credentials.json"

# Setzt das Seitenlayout der Streamlit App auf "Weit"
st.set_page_config(page_title="Solo Status Tracker & Logger", layout="wide", page_icon="🚀")

# ==========================================
# PASSPORT PROTECTION (AUTHENTICATION)
# ==========================================
def check_password():
    """Gibt True zurück, wenn der Benutzer das korrekte Passwort eingegeben hat."""
    def password_entered():
        correct_password = st.secrets.get("password", "admin123")
        if st.session_state["password_input"] == correct_password:
            st.session_state["password_correct"] = True
            del st.session_state["password_input"]
        else:
            st.session_state["password_correct"] = False

    if st.session_state.get("password_correct", False):
        return True

    st.title("🔒 Solo Status Tracker — Login")
    st.text_input("Bitte gib das Passwort ein:", type="password", on_change=password_entered, key="password_input")
    if "password_correct" in st.session_state and not st.session_state["password_correct"]:
        st.error("❌ Falsches Passwort. Bitte versuche es erneut.")
    return False

if not check_password():
    st.stop()

# ==========================================
# GOOGLE SERVICES INTEGRATION
# ==========================================
def get_google_credentials():
    if "google_credentials" in st.secrets:
        creds_dict = dict(st.secrets["google_credentials"])
        return service_account.Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    elif os.path.exists(CREDENTIALS_FILE):
        return service_account.Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    return None

def get_google_docs_service():
    creds = get_google_credentials()
    if not creds:
        return None
    return build("docs", "v1", credentials=creds)

# ==========================================
# CLOUD DATENMANAGEMENT (VIA GOOGLE DOC)
# ==========================================
DATA_MARKER_START = "=== APP_DATA_START ==="
DATA_MARKER_END = "=== APP_DATA_END ==="

def load_remote_tasks():
    """Lädt die To-Do-Liste aus dem Ende des Google Docs."""
    service = get_google_docs_service()
    if not service:
        return []
    try:
        doc = service.documents().get(documentId=GOOGLE_DOC_ID).execute()
        text = ""
        for content in doc.get("body", {}).get("content", []):
            if "paragraph" in content:
                for element in content["paragraph"].get("elements", []):
                    text += element.get("textRun", {}).get("content", "")
        
        if DATA_MARKER_START in text and DATA_MARKER_END in text:
            start_idx = text.find(DATA_MARKER_START) + len(DATA_MARKER_START)
            end_idx = text.find(DATA_MARKER_END)
            json_data = text[start_idx:end_idx].strip()
            return json.loads(json_data)
    except Exception:
        pass
    return []

def save_remote_tasks(tasks):
    """Speichert die To-Do-Liste als JSON-String am Ende des Google Docs abs."""
    service = get_google_docs_service()
    if not service:
        return
    try:
        doc = service.documents().get(documentId=GOOGLE_DOC_ID).execute()
        text = ""
        full_content = doc.get("body", {}).get("content", [])
        for content in full_content:
            if "paragraph" in content:
                for element in content["paragraph"].get("elements", []):
                    text += element.get("textRun", {}).get("content", "")
        
        # Bestimme das Ende des Dokuments (letzter Index)
        end_of_doc_index = full_content[-1].get("endIndex") - 1
        
        json_string = json.dumps(tasks, ensure_ascii=False)
        new_data_block = f"\n{DATA_MARKER_START}{json_string}{DATA_MARKER_END}"
        
        requests = []
        
        # Falls alter Datenblock existiert, diesen zuerst löschen
        if DATA_MARKER_START in text:
            start_pos = text.find(DATA_MARKER_START)
            end_pos = text.find(DATA_MARKER_END) + len(DATA_MARKER_END)
            requests.append({
                "deleteContentRange": {
                    "range": {
                        "startIndex": start_pos + 1,
                        "endIndex": end_pos + 1
                    }
                }
            })
            # Nach dem Löschen fügen wir es am alten Startpunkt wieder ein
            requests.append({
                "insertText": {
                    "location": {"index": start_pos + 1},
                    "text": new_data_block
                }
            })
        else:
            # Wenn kein Block existiert, einfach ganz ans Ende anfügen
            requests.append({
                "insertText": {
                    "location": {"index": end_of_doc_index},
                    "text": new_data_block
                }
            })
            
        service.documents().batchUpdate(documentId=GOOGLE_DOC_ID, body={"requests": requests}).execute()
    except Exception as e:
        st.error(f"Fehler beim Speichern der Aufgaben in der Cloud: {e}")

def log_to_google_doc(task_title, priority, started_at, process_note):
    """Schreibt das fertige Protokoll ganz oben ins Dokument."""
    service = get_google_docs_service()
    if not service:
        st.warning("⚠️ Keine Google-Zugangsdaten gefunden.")
        return False

    try:
        now = datetime.datetime.now()
        done_time_str = now.strftime("%d.%m.%Y um %H:%M:%S Uhr")
        
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

        log_entry = (
            f"\n==================================================\n"
            f"✅ ERLEDIGT: {task_title}\n"
            f"📅 Abgeschlossen am: {done_time_str}\n"
            f"⏱️ Bearbeitungszeit: {duration_str}\n"
            f"🔥 Priorität: {priority}\n"
            f"📝 Prozess-Notiz / Ergebnis:\n   {process_note if process_note else 'Keine Notiz hinterlegt.'}\n"
            f"==================================================\n"
        )

        requests = [{"insertText": {"location": {"index": 1}, "text": log_entry}}]
        service.documents().batchUpdate(documentId=GOOGLE_DOC_ID, body={"requests": requests}).execute()
        return True
    except Exception as e:
        st.error(f"Fehler bei der Übertragung an Google Docs: {e}")
        return False

# Initialisiere die Tasks direkt aus der Google Cloud
if "tasks" not in st.session_state:
    with st.spinner("Lade aktuelle To-Dos aus der Cloud..."):
        st.session_state.tasks = load_remote_tasks()

# ==========================================
# STREAMLIT UI & INTERACTION
# ==========================================
st.title("🚀 Solo Status Tracker")
st.caption("Ein maßgeschneidertes Tool mit Cloud-Speicherung direkt in Google Docs.")

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
    save_remote_tasks(st.session_state.tasks)
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
    for idx, task in enumerate(todo_tasks):
        with st.container(border=True):
            st.markdown(f"### {task['title']}")
            st.markdown(f"**Prio:** {task['priority']}")
            if st.button("▶️ Arbeit starten", key=f"start_todo_{task['id']}_{idx}", use_container_width=True):
                task["status"] = "in_progress"
                task["started_at"] = datetime.datetime.now().isoformat()
                save_remote_tasks(st.session_state.tasks)
                st.rerun()

# SPALTE 2: IN ARBEIT
with col_progress:
    st.header("⚡ In Arbeit")
    progress_tasks = [t for t in st.session_state.tasks if t["status"] == "in_progress"]
    if not progress_tasks:
        st.info("Aktuell ruht die Arbeit.")
    for idx, task in enumerate(progress_tasks):
        with st.container(border=True):
            st.markdown(f"### {task['title']}")
            st.markdown(f"**Prio:** {task['priority']}")
            if task["started_at"]:
                start = datetime.datetime.fromisoformat(task["started_at"])
                diff = datetime.datetime.now() - start
                mins = int(diff.total_seconds() // 60)
                st.caption(f"⏱️ Läuft seit: {mins} Minuten")
            if st.button("🏁 Abschließen & Loggen", key=f"trigger_done_{task['id']}_{idx}", use_container_width=True):
                st.session_state.active_done_task = task
                st.rerun()

# SPALTE 3: ABSCHLUSS-DIALOG
with col_done_dialog:
    st.header("📝 Prozess-Archiv")
    if "active_done_task" in st.session_state and st.session_state.active_done_task:
        task = st.session_state.active_done_task
        st.success(f"Füge Notizen hinzu für:\n**{task['title']}**")
        process_note = st.text_area("Was hast du gemacht?", placeholder="z.B. Fehler behoben...", key="process_note_input", height=150)
        
        col_back, col_confirm = st.columns(2)
        with col_back:
            if st.button("Abbrechen", use_container_width=True):
                st.session_state.active_done_task = None
                st.rerun()
        with col_confirm:
            if st.button("🚀 In Google Doc posten", type="primary", use_container_width=True):
                with st.spinner("Übertrage Daten an Google Docs..."):
                    success = log_to_google_doc(task_title=task["title"], priority=task["priority"], started_at=task["started_at"], process_note=process_note)
                    if success:
                        st.session_state.tasks.remove(task)
                        save_remote_tasks(st.session_state.tasks)
                        st.session_state.active_done_task = None
                        st.toast("Aufgabe erfolgreich archiviert!", icon="🎉")
                        st.rerun()
    else:
        st.info("Klicke bei einer aktiven Aufgabe auf 'Abschließen & Loggen'.")

with st.sidebar:
    st.header("⚙️ App-Optionen & Infos")
    total_open = len(st.session_state.tasks)
    st.metric(label="Offene Aufgaben (Cloud)", value=total_open)
    
    if st.button("🧹 Alle Cloud-Daten zurücksetzen"):
        st.session_state.tasks = []
        save_remote_tasks([])
        if "active_done_task" in st.session_state:
            st.session_state.active_done_task = None
        st.rerun()
        end_of_doc_index = full_content[-1].get("endIndex") - 1
        
        json_string = json.dumps(tasks, ensure_ascii=False)
        new_data_block = f"\n{DATA_MARKER_START}{json_string}{DATA_MARKER_END}"
        
        requests = []
        
        # Falls alter Datenblock existiert, diesen zuerst löschen
        if DATA_MARKER_START in text:
            start_pos = text.find(DATA_MARKER_START)
            end_pos = text.find(DATA_MARKER_END) + len(DATA_MARKER_END)
            requests.append({
                "deleteContentRange": {
                    "range": {
                        "startIndex": start_pos + 1,
                        "endIndex": end_pos + 1
                    }
                }
            })
            # Nach dem Löschen fügen wir es am alten Startpunkt wieder ein
            requests.append({
                "insertText": {
                    "location": {"index": start_pos + 1},
                    "text": new_data_block
                }
            })
        else:
            # Wenn kein Block existiert, einfach ganz ans Ende anfügen
            requests.append({
                "insertText": {
                    "location": {"index": end_of_doc_index},
                    "text": new_data_block
                }
            })
            
        service.documents().batchUpdate(documentId=GOOGLE_DOC_ID, body={"requests": requests}).execute()
    except Exception as e:
        st.error(f"Fehler beim Speichern der Aufgaben in der Cloud: {e}")

def log_to_google_doc(task_title, priority, started_at, process_note):
    """Schreibt das fertige Protokoll ganz oben ins Dokument."""
    service = get_google_docs_service()
    if not service:
        st.warning("⚠️ Keine Google-Zugangsdaten gefunden.")
        return False

    try:
        now = datetime.datetime.now()
        done_time_str = now.strftime("%d.%m.%Y um %H:%M:%S Uhr")
        
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

        log_entry = (
            f"\n==================================================\n"
            f"✅ ERLEDIGT: {task_title}\n"
            f"📅 Abgeschlossen am: {done_time_str}\n"
            f"⏱️ Bearbeitungszeit: {duration_str}\n"
            f"🔥 Priorität: {priority}\n"
            f"📝 Prozess-Notiz / Ergebnis:\n   {process_note if process_note else 'Keine Notiz hinterlegt.'}\n"
            f"==================================================\n"
        )

        requests = [{"insertText": {"location": {"index": 1}, "text": log_entry}}]
        service.documents().batchUpdate(documentId=GOOGLE_DOC_ID, body={"requests": requests}).execute()
        return True
    except Exception as e:
        st.error(f"Fehler bei der Übertragung an Google Docs: {e}")
        return False

# Initialisiere die Tasks direkt aus der Google Cloud
if "tasks" not in st.session_state:
    with st.spinner("Lade aktuelle To-Dos aus der Cloud..."):
        st.session_state.tasks = load_remote_tasks()

# ==========================================
# STREAMLIT UI & INTERACTION
# ==========================================
st.title("🚀 Solo Status Tracker")
st.caption("Ein maßgeschneidertes Tool mit Cloud-Speicherung direkt in Google Docs.")

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
    save_remote_tasks(st.session_state.tasks)
    st.success(f"Task '{new_task_title}' hinzugefügt!")
    st.rerun()

st.markdown("---")
col_todo, col_progress, col_done_dialog = st.columns(3)

# SPALTE 1: TO-DO (Befestigt mit eindeutigen Keys via enumerate)
with col_todo:
    st.header("📋 Bereit (To-Do)")
    todo_tasks = [t for t in st.session_state.tasks if t["status"] == "todo"]
    if not todo_tasks:
        st.info("Keine Aufgaben im Backlog.")
    for idx, task in enumerate(todo_tasks):
        with st.container(border=True):
            st.markdown(f"### {task['title']}")
            st.markdown(f"**Prio:** {task['priority']}")
            if st.button("▶️ Arbeit starten", key=f"start_todo_{task['id']}_{idx}", use_container_width=True):
                task["status"] = "in_progress"
                task["started_at"] = datetime.datetime.now().isoformat()
                save_remote_tasks(st.session_state.tasks)
                st.rerun()

# SPALTE 2: IN ARBEIT (Befestigt mit eindeutigen Keys via enumerate)
with col_progress:
    st.header("⚡ In Arbeit")
    progress_tasks = [t for t in st.session_state.tasks if t["status"] == "in_progress"]
    if not progress_tasks:
        st.info("Aktuell ruht die Arbeit.")
    for idx, task in enumerate(progress_tasks):
        with st.container(border=True):
            st.markdown(f"### {task['title']}")
            st.markdown(f"**Prio:** {task['priority']}")
            if task["started_at"]:
                start = datetime.datetime.fromisoformat(task["started_at"])
                diff = datetime.datetime.now() - start
                mins = int(diff.total_seconds() // 60)
                st.caption(f"⏱️ Läuft seit: {mins} Minuten")
            if st.button("🏁 Abschließen & Loggen", key=f"trigger_done_{task['id']}_{idx}", use_container_width=True):
                st.session_state.active_done_task = task
                st.rerun()

# SPALTE 3: ABSCHLUSS-DIALOG
with col_done_dialog:
    st.header("📝 Prozess-Archiv")
    if "active_done_task" in st.session_state and st.session_state.active_done_task:
        task = st.session_state.active_done_task
        st.success(f"Füge Notizen hinzu für:\n**{task['title']}**")
        process_note = st.text_area("Was hast du gemacht?", placeholder="z.B. Fehler behoben...", key="process_note_input", height=150)
        
        col_back, col_confirm = st.columns(2)
        with col_back:
            if st.button("Abbrechen", use_container_width=True):
                st.session_state.active_done_task = None
                st.rerun()
        with col_confirm:
            if st.button("🚀 In Google Doc posten", type="primary", use_container_width=True):
                with st.spinner("Übertrage Daten an Google Docs..."):
                    success = log_to_google_doc(task_title=task["title"], priority=task["priority"], started_at=task["started_at"], process_note=process_note)
                    if success:
                        st.session_state.tasks.remove(task)
                        save_remote_tasks(st.session_state.tasks)
                        st.session_state.active_done_task = None
                        st.toast("Aufgabe erfolgreich archiviert!", icon="🎉")
                        st.rerun()
    else:
        st.info("Klicke bei einer aktiven Aufgabe auf 'Abschließen & Loggen'.")

with st.sidebar:
    st.header("⚙️ App-Optionen & Infos")
    total_open = len(st.session_state.tasks)
    st.metric(label="Offene Aufgaben (Cloud)", value=total_open)
    
    if st.button("🧹 Alle Cloud-Daten zurücksetzen"):
        st.session_state.tasks = []
        save_remote_tasks([])
        if "active_done_task" in st.session_state:
            st.session_state.active_done_task = None
        st.rerun()
        end_of_doc_index = full_content[-1].get("endIndex") - 1
        
        json_string = json.dumps(tasks, ensure_ascii=False)
        new_data_block = f"\n{DATA_MARKER_START}{json_string}{DATA_MARKER_END}"
        
        requests = []
        
        # Falls alter Datenblock existiert, diesen zuerst löschen
        if DATA_MARKER_START in text:
            start_pos = text.find(DATA_MARKER_START)
            end_pos = text.find(DATA_MARKER_END) + len(DATA_MARKER_END)
            # Versatz im Google Doc ausgleichen (Index startet bei 1)
            requests.append({
                "deleteContentRange": {
                    "range": {
                        "startIndex": start_pos + 1,
                        "endIndex": end_pos + 1
                    }
                }
            })
            # Nach dem Löschen fügen wir es am alten Startpunkt wieder ein
            requests.append({
                "insertText": {
                    "location": {"index": start_pos + 1},
                    "text": new_data_block
                }
            })
        else:
            # Wenn kein Block existiert, einfach ganz ans Ende anfügen
            requests.append({
                "insertText": {
                    "location": {"index": end_of_doc_index},
                    "text": new_data_block
                }
            })
            
        service.documents().batchUpdate(documentId=GOOGLE_DOC_ID, body={"requests": requests}).execute()
    except Exception as e:
        st.error(f"Fehler beim Speichern der Aufgaben in der Cloud: {e}")

def log_to_google_doc(task_title, priority, started_at, process_note):
    """Schreibt das fertige Protokoll ganz oben ins Dokument."""
    service = get_google_docs_service()
    if not service:
        st.warning("⚠️ Keine Google-Zugangsdaten gefunden.")
        return False

    try:
        now = datetime.datetime.now()
        done_time_str = now.strftime("%d.%m.%Y um %H:%M:%S Uhr")
        
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

        log_entry = (
            f"\n==================================================\n"
            f"✅ ERLEDIGT: {task_title}\n"
            f"📅 Abgeschlossen am: {done_time_str}\n"
            f"⏱️ Bearbeitungszeit: {duration_str}\n"
            f"🔥 Priorität: {priority}\n"
            f"📝 Prozess-Notiz / Ergebnis:\n   {process_note if process_note else 'Keine Notiz hinterlegt.'}\n"
            f"==================================================\n"
        )

        requests = [{"insertText": {"location": {"index": 1}, "text": log_entry}}]
        service.documents().batchUpdate(documentId=GOOGLE_DOC_ID, body={"requests": requests}).execute()
        return True
    except Exception as e:
        st.error(f"Fehler bei der Übertragung an Google Docs: {e}")
        return False

# Initialisiere die Tasks direkt aus der Google Cloud
if "tasks" not in st.session_state:
    with st.spinner("Lade aktuelle To-Dos aus der Cloud..."):
        st.session_state.tasks = load_remote_tasks()

# ==========================================
# STREAMLIT UI & INTERACTION
# ==========================================
st.title("🚀 Solo Status Tracker")
st.caption("Ein maßgeschneidertes Tool mit Cloud-Speicherung direkt in Google Docs.")

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
    save_remote_tasks(st.session_state.tasks)
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
                save_remote_tasks(st.session_state.tasks)
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
        process_note = st.text_area("Was hast du gemacht?", placeholder="z.B. Fehler behoben...", key="process_note_input", height=150)
        
        col_back, col_confirm = st.columns(2)
        with col_back:
            if st.button("Abbrechen", use_container_width=True):
                st.session_state.active_done_task = None
                st.rerun()
        with col_confirm:
            if st.button("🚀 In Google Doc posten", type="primary", use_container_width=True):
                with st.spinner("Übertrage Daten an Google Docs..."):
                    success = log_to_google_doc(task_title=task["title"], priority=task["priority"], started_at=task["started_at"], process_note=process_note)
                    if success:
                        st.session_state.tasks.remove(task)
                        save_remote_tasks(st.session_state.tasks)
                        st.session_state.active_done_task = None
                        st.toast("Aufgabe erfolgreich archiviert!", icon="🎉")
                        st.rerun()
    else:
        st.info("Klicke bei einer aktiven Aufgabe auf 'Abschließen & Loggen'.")

with st.sidebar:
    st.header("⚙️ App-Optionen & Infos")
    total_open = len(st.session_state.tasks)
    st.metric(label="Offene Aufgaben (Cloud)", value=total_open)
    
    if st.button("🧹 Alle Cloud-Daten zurücksetzen"):
        st.session_state.tasks = []
        save_remote_tasks([])
        if "active_done_task" in st.session_state:
            st.session_state.active_done_task = None
        st.rerun()

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
        process_note = st.text_area("Was hast du gemacht?", placeholder="z.B. Fehler behoben...", key="process_note_input", height=150)
        
        col_back, col_confirm = st.columns(2)
        with col_back:
            if st.button("Abbrechen", use_container_width=True):
                st.session_state.active_done_task = None
                st.rerun()
        with col_confirm:
            if st.button("🚀 In Google Doc posten", type="primary", use_container_width=True):
                with st.spinner("Übertrage Daten an Google Docs..."):
                    success = log_to_google_doc(task_title=task["title"], priority=task["priority"], started_at=task["started_at"], process_note=process_note)
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
