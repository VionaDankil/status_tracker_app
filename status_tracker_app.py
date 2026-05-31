import streamlit as st
import datetime
import json
import os
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ==========================================
# CONFIGURATION & CONSTANTS
# ==========================================
# In einer Produktionsumgebung (z.B. Streamlit Community Cloud) sollten diese Werte 
# über st.secrets geladen werden, um die Sicherheit der Zugangsdaten zu gewährleisten.
# lokal nutzen wir Platzhalter oder Umgebungsvariablen.

CREDENTIALS_FILE = "google_credentials.json"  # Pfad zu deiner Google Service-Account-JSON
GOOGLE_DOC_ID = "DEINE_GOOGLE_DOC_ID_HIER_EINFUEGEN" # Die ID aus der URL deines Google Docs
LOCAL_DATA_FILE = "todo_tasks.json"

SCOPES = ["https://www.googleapis.com/auth/documents"]

# Setzt das Seitenlayout der Streamlit App auf "Weit"
st.set_page_config(page_title="Solo Status Tracker & Logger", layout="wide", page_icon="🚀")

# ==========================================
# DATENMANAGEMENT (LOCAL STORAGE)
# ==========================================
def load_local_tasks():
    """Lädt die Aufgaben aus einer lokalen JSON-Datei."""
    if os.path.exists(LOCAL_DATA_FILE):
        try:
            with open(LOCAL_DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_local_tasks(tasks):
    """Speichert die Aufgaben in einer lokalen JSON-Datei."""
    with open(LOCAL_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(tasks, f, ensure_ascii=False, indent=4)

# Initialisiere den Session State von Streamlit
if "tasks" not in st.session_state:
    st.session_state.tasks = load_local_tasks()

# ==========================================
# GOOGLE DOCS INTEGRATION (LOGGER)
# ==========================================
def log_to_google_doc(task_title, priority, started_at, process_note):
    """Schreibt die erledigte Aufgabe mit Zeitstempel und Prozessdetails in Google Docs."""
    if not os.path.exists(CREDENTIALS_FILE):
        st.warning(f"⚠️ Hinweis: '{CREDENTIALS_FILE}' wurde nicht gefunden. Der Eintrag wird nur lokal gelöscht, nicht im Google Doc archiviert.")
        return False
    
    if GOOGLE_DOC_ID == "DEINE_GOOGLE_DOC_ID_HIER_EINFUEGEN":
        st.error("❌ Bitte trage deine echte Google Doc ID im Quellcode ein!")
        return False

    try:
        # Authentifizierung über den Service Account
        creds = service_account.Credentials.from_service_account_file(
            CREDENTIALS_FILE, scopes=SCOPES
        )
        service = build("docs", "v1", credentials=creds)

        # Zeitstempel berechnen
        now = datetime.datetime.now()
        done_time_str = now.strftime("%d.%m.%Y um %H:%M:%S Uhr")
        
        # Dauer berechnen, falls Startzeitpunkt vorhanden
        duration_str = "Nicht getrackt"
        if started_at:
            start_time = datetime.datetime.fromisoformat(started_at)
            duration = now - start_time
            # Formatierung der Dauer (Stunden und Minuten)
            hours, remainder = divmod(duration.total_seconds(), 3600)
            minutes, _ = divmod(remainder, 60)
            if hours > 0:
                duration_str = f"{int(hours)} Std. {int(minutes)} Min."
            else:
                duration_str = f"{int(minutes)} Min."

        # Formatierter Text für das Google Doc Logbuch
        log_entry = (
            f"\n==================================================\n"
            f"✅ ERLEDIGT: {task_title}\n"
            f"📅 Abgeschlossen am: {done_time_str}\n"
            f"⏱️ Bearbeitungszeit: {duration_str}\n"
            f"🔥 Priorität: {priority}\n"
            f"📝 Prozess-Notiz / Ergebnis:\n   {process_note if process_note else 'Keine Notiz hinterlegt.'}\n"
            f"==================================================\n"
        )

        # Text ganz oben im Dokument einfügen (nach dem ersten Zeichen)
        # Für ein reines fortlaufendes Logbuch ist das ideal, da das Neueste immer oben steht.
        requests = [
            {
                "insertText": {
                    "location": {
                        "index": 1
                    },
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

# Quick-Add Eingabefeld (Ganz oben für maximale Schnelligkeit)
st.subheader("📝 Neues To-Do hinzufügen")
with st.form("quick_add_form", clear_on_submit=True):
    col_input, col_prio, col_btn = st.columns([5, 2, 1])
    with col_input:
        new_task_title = st.text_input("Was ist zu tun?", placeholder="z.B. Datenbank-Backup automatisieren...")
    with col_prio:
        new_task_prio = st.selectbox("Priorität", ["🔴 Hoch", "🟡 Mittel", "🟢 Niedrig"], index=1)
    with col_btn:
        st.write("<br>", unsafe_allow_html=True) # Abstandshalter für vertikale Ausrichtung
        submit_button = st.form_submit_button("Hinzufügen")

if submit_button and new_task_title.strip():
    # Neues Task-Objekt erstellen
    new_task = {
        "id": str(datetime.datetime.now().timestamp()),
        "title": new_task_title.strip(),
        "priority": new_task_prio,
        "status": "todo", # standardmäßig im Backlog
        "created_at": datetime.datetime.now().isoformat(),
        "started_at": None
    }
    st.session_state.tasks.append(new_task)
    save_local_tasks(st.session_state.tasks)
    st.success(f"Task '{new_task_title}' hinzugefügt!")
    st.rerun()

# Trennlinie
st.markdown("---")

# Spalten-Layout für das Solo-Kanban-Board
col_todo, col_progress, col_done_dialog = st.columns(3)

# ------------------------------------------
# SPALTE 1: BEREIT (TO-DO)
# ------------------------------------------
with col_todo:
    st.header("📋 Bereit (To-Do)")
    todo_tasks = [t for t in st.session_state.tasks if t["status"] == "todo"]
    
    if not todo_tasks:
        st.info("Keine Aufgaben im Backlog. Zeit für neue Ideen!")
        
    for task in todo_tasks:
        with st.container(border=True):
            st.markdown(f"### {task['title']}")
            st.markdown(f"**Prio:** {task['priority']}")
            
            # Button um die Arbeit zu beginnen (startet den Timer)
            if st.button("▶️ Arbeit starten", key=f"start_{task['id']}", use_container_width=True):
                task["status"] = "in_progress"
                task["started_at"] = datetime.datetime.now().isoformat()
                save_local_tasks(st.session_state.tasks)
                st.rerun()

# ------------------------------------------
# SPALTE 2: IN ARBEIT (IN PROGRESS)
# ------------------------------------------
with col_progress:
    st.header("⚡ In Arbeit")
    progress_tasks = [t for t in st.session_state.tasks if t["status"] == "in_progress"]
    
    if not progress_tasks:
        st.info("Aktuell ruht die Arbeit. Wähle ein To-Do aus!")
        
    for task in progress_tasks:
        with st.container(border=True):
            st.markdown(f"### {task['title']}")
            st.markdown(f"**Prio:** {task['priority']}")
            
            # Zeit seit Start berechnen für die Anzeige im UI
            if task["started_at"]:
                start = datetime.datetime.fromisoformat(task["started_at"])
                diff = datetime.datetime.now() - start
                mins = int(diff.total_seconds() // 60)
                st.caption(f"⏱️ Läuft seit: {mins} Minuten")
            
            # Aktiviert den Abschluss-Prozess für genau diese Aufgabe
            if st.button("🏁 Abschließen & Loggen", key=f"trigger_done_{task['id']}", use_container_width=True):
                st.session_state.active_done_task = task
                st.rerun()

# ------------------------------------------
# SPALTE 3: ABSCHLUSS-DIALOG & PROZESSNOTIZ
# ------------------------------------------
with col_done_dialog:
    st.header("📝 Prozess-Archiv")
    
    if "active_done_task" in st.session_state and st.session_state.active_done_task:
        task = st.session_state.active_done_task
        
        st.success(f"Füge Notizen hinzu für:\n**{task['title']}**")
        
        # Textfeld für den "ganzen Prozess" / Fehler / Lösungen
        process_note = st.text_area(
            "Was hast du gemacht? (Ablauf, gelöste Probleme, wichtige Erkenntnisse):",
            placeholder="z.B. Fehler im Skript behoben, Berechtigungen in der Cloud angepasst. Doku aktualisiert.",
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
                    # 1. An Google Docs senden
                    success = log_to_google_doc(
                        task_title=task["title"],
                        priority=task["priority"],
                        started_at=task["started_at"],
                        process_note=process_note
                    )
                    
                    if success or not os.path.exists(CREDENTIALS_FILE):
                        # 2. Wenn erfolgreich (oder lokal getestet ohne Datei), aus der App entfernen
                        st.session_state.tasks.remove(task)
                        save_local_tasks(st.session_state.tasks)
                        st.session_state.active_done_task = None
                        st.toast("Aufgabe erfolgreich archiviert!", icon="🎉")
                        st.rerun()
    else:
        st.info("Klicke bei einer aktiven Aufgabe auf 'Abschließen & Loggen', um das Prozessprotokoll zu starten.")

# Sidebar mit Statistiken und Hilfen
with st.sidebar:
    st.header("⚙️ App-Optionen & Infos")
    
    # Lokaler Zähler
    total_open = len(st.session_state.tasks)
    st.metric(label="Offene Aufgaben lokal", value=total_open)
    
    st.markdown("""
    ### Kurzanleitung:
    1. Trage oben eine Aufgabe ein.
    2. Klicke auf **▶️ Arbeit starten**, um den Timer im Hintergrund zu aktivieren.
    3. Sobald du fertig bist, klicke auf **🏁 Abschließen & Loggen**.
    4. Beschreibe kurz deinen Prozess und drücke den Sende-Button. 
    
    *Das Ergebnis wird direkt chronologisch ganz oben in dein Google Doc eingefügt.*
    """)
    
    if st.button("🧹 Alle lokalen Daten zurücksetzen"):
        st.session_state.tasks = []
        save_local_tasks([])
        if "active_done_task" in st.session_state:
            st.session_state.active_done_task = None
        st.rerun()
