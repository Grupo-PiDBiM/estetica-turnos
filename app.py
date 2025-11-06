# ==========================================================
# Estética | Turnos tipo Calendly (Local, sin Google/Secrets)
# Landing + Reserva paso a paso + Admin (Agenda, Servicios, Clientes, Historial)
# - Selección por grupos exclusivos (Piernas / Brazos / Rostro) + zonas sueltas (en un bloque)
# - Horarios en selectbox (mobile friendly) + bloquea horarios pasados del día actual
# - Editor masivo de turnos, catálogo editable, clientes editable
# - Finalizar turno y archivar historial por cliente + historial global
# - En "Turno pendiente" y "Cliente existente": Nombre (– email)
# - Estilos responsive para celular
# ==========================================================
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, time, date
from pathlib import Path
import uuid
import re

# =========================
# CONFIG GENERAL
# =========================
st.set_page_config(page_title="Turnos Estética", page_icon="💆‍♀️", layout="wide")

APP_TITLE = "💆‍♀️ Turnos Estética"
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

FILES = {
    "servicios": DATA_DIR / "servicios.csv",
    "clientes": DATA_DIR / "clientes.csv",
    "turnos": DATA_DIR / "turnos.csv",
    "historial": DATA_DIR / "historial.csv",
}

HISTORIAS_DIR = DATA_DIR / "historias"
HISTORIAS_DIR.mkdir(exist_ok=True)

# Parámetros
SLOT_STEP_MIN = 10
BUFFER_MIN_DEFAULT = 5

# Admin
ADMIN_USER = "admin"
ADMIN_PASS = "admin"

# Disponibilidad semanal (1=Lun ... 7=Dom)
DEFAULT_DISPONIBILIDAD_CODE = {
    1: [("09:00", "13:00"), ("14:00", "17:00")],
    2: [("09:00", "17:00")],
    3: [("09:00", "17:00")],
    4: [("09:00", "17:00")],
    5: [("09:00", "15:00")],
    # 6,7 sin turnos (sábado/domingo)
}

# =========================
# SEMILLAS
# =========================
DEFAULT_SERVICIOS = pd.DataFrame([
    # Tipo, Zona, Duracion_min, Precio
    # ---- LÁSER ----
    ["Láser", "Axilas",            15,  8000],
    ["Láser", "Medias piernas",    25, 16000],
    ["Láser", "Piernas completas", 40, 25000],
    ["Láser", "Brazos",            30, 18000],
    ["Láser", "Medio brazo",       20, 12000],
    ["Láser", "Cavado",            20, 12000],
    ["Láser", "Tiro de cola",      15, 10000],
    ["Láser", "Rostro completo",   25, 15000],
    ["Láser", "Cara",              15,  9000],
    # ---- DESCARTABLE ----
    ["Descartable", "Axilas",            20,  6000],
    ["Descartable", "Medias piernas",    30, 12000],
    ["Descartable", "Piernas completas", 45, 20000],
    ["Descartable", "Brazos",            35, 15000],
    ["Descartable", "Medio brazo",       25, 10000],
    ["Descartable", "Cavado",            25, 10000],
    ["Descartable", "Tiro de cola",      20,  8000],
    ["Descartable", "Rostro completo",   30, 12000],
    ["Descartable", "Cara",              20,  8000],
], columns=["Tipo", "Zona", "Duracion_min", "Precio"])

DEFAULT_CLIENTES = pd.DataFrame([], columns=["Cliente_ID", "Nombre", "WhatsApp", "Email", "Notas"])
DEFAULT_TURNOS = pd.DataFrame([], columns=[
    "Turno_ID","Cliente_ID","Fecha","Inicio","Fin","Tipo","Zonas",
    "Duracion_total","Estado","Notas","RecordatorioEnviado"
])
DEFAULT_HISTORIAL_GLOBAL = pd.DataFrame([], columns=["Cliente_ID","Nombre","Fecha","Evento","Detalles"])

# =========================
# IO DATOS
# =========================
def ensure_files():
    if not FILES["servicios"].exists():
        DEFAULT_SERVICIOS.to_csv(FILES["servicios"], index=False, encoding="utf-8")
    if not FILES["clientes"].exists():
        DEFAULT_CLIENTES.to_csv(FILES["clientes"], index=False, encoding="utf-8")
    if not FILES["turnos"].exists():
        DEFAULT_TURNOS.to_csv(FILES["turnos"], index=False, encoding="utf-8")
    if not FILES["historial"].exists():
        DEFAULT_HISTORIAL_GLOBAL.to_csv(FILES["historial"], index=False, encoding="utf-8")

def load_df(name: str) -> pd.DataFrame:
    ensure_files()
    df = pd.read_csv(FILES[name], dtype=str).fillna("")
    if name == "servicios":
        for col in ["Tipo", "Zona"]:
            df[col] = df[col].astype(str).str.strip()
        df = df[(df["Tipo"] != "") & (df["Zona"] != "")]
        for c in ["Duracion_min", "Precio"]:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)
        df = df.drop_duplicates(subset=["Tipo", "Zona"], keep="first").reset_index(drop=True)
    elif name == "clientes":
        if "Cliente_ID" in df.columns and "WhatsApp" in df.columns:
            df["Cliente_ID"] = df["Cliente_ID"].astype(str).str.strip()
            df["WhatsApp"] = df["WhatsApp"].astype(str).str.strip()
            df.loc[df["Cliente_ID"] == "", "Cliente_ID"] = df["WhatsApp"]
            df.loc[df["WhatsApp"] == "", "WhatsApp"] = df["Cliente_ID"]
    elif name == "turnos":
        if "Fecha" in df.columns:
            df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce").dt.date
    return df

def save_df(name: str, df: pd.DataFrame):
    df.to_csv(FILES[name], index=False, encoding="utf-8")

# =========================
# UTILS
# =========================
def to_time(hhmm: str):
    s = str(hhmm).strip()
    if not s or ":" not in s:
        return None
    try:
        hh, mm = s.split(":")[:2]
        return time(int(hh), int(mm))
    except:
        return None

def overlaps(start1, end1, start2, end2):
    return (start1 < end2) and (start2 < end1)

def humanize_list(items):
    return ", ".join(items or [])

def calc_duracion(servicios_df: pd.DataFrame, tipo: str, zonas: list[str]) -> int:
    sel = servicios_df[(servicios_df["Tipo"] == tipo) & (servicios_df["Zona"].isin(zonas))]
    return int(sel["Duracion_min"].sum()) if not sel.empty else 0

def calc_precio(servicios_df: pd.DataFrame, tipo: str, zonas: list[str]) -> int:
    sel = servicios_df[(servicios_df["Tipo"] == tipo) & (servicios_df["Zona"].isin(zonas))]
    return int(sel["Precio"].sum()) if not sel.empty else 0

def generar_slots(date_obj: date, dur_min: int, turnos_df: pd.DataFrame, slot_step_min: int = SLOT_STEP_MIN):
    if dur_min <= 0:
        return []
    weekday = date_obj.isoweekday()
    tramos = DEFAULT_DISPONIBILIDAD_CODE.get(weekday, [])
    if not tramos:
        return []

    activos = pd.DataFrame()
    if not turnos_df.empty:
        activos = turnos_df[(turnos_df["Fecha"] == date_obj) & (~turnos_df["Estado"].isin(["Cancelado", "No-show"]))].copy()

    result = []
    step = timedelta(minutes=slot_step_min)
    dur = timedelta(minutes=dur_min)
    buff = timedelta(minutes=BUFFER_MIN_DEFAULT)

    for (ini, fin) in tramos:
        ti, tf = to_time(ini), to_time(fin)
        if not ti or not tf:
            continue
        start_dt = datetime.combine(date_obj, ti)
        end_window = datetime.combine(date_obj, tf)
        current = start_dt
        while current + dur <= end_window:
            c_start, c_end = current, current + dur
            ok = True
            if not activos.empty:
                for _, t in activos.iterrows():
                    try:
                        t_start = datetime.combine(date_obj, datetime.strptime(t["Inicio"], "%H:%M").time())
                        t_end = datetime.combine(date_obj, datetime.strptime(t["Fin"], "%H:%M").time())
                    except Exception:
                        continue
                    if overlaps(c_start - buff, c_end + buff, t_start, t_end):
                        ok = False
                        break
            if ok:
                result.append(c_start)
            current += step
    return sorted(list(dict.fromkeys(result)))

def filter_future_slots(date_obj: date, slots: list[datetime]) -> list[datetime]:
    """Si la fecha es hoy, filtra slots que ya pasaron respecto al ahora del servidor."""
    if not slots:
        return []
    now = datetime.now()
    if date_obj == now.date():
        return [s for s in slots if s > now]
    return slots

def slugify(text: str) -> str:
    text = str(text or "").strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:60] if text else "cliente"

def get_cliente_display_row(row) -> str:
    """Devuelve 'Nombre – email' si hay email; si no, 'Nombre'; si no hay, el Cliente_ID."""
    nombre = str(row.get("Nombre", "") or "").strip()
    email = str(row.get("Email", "") or "").strip()
    cid = str(row.get("Cliente_ID", "") or "").strip()
    if nombre and email:
        return f"{nombre} – {email}"
    if nombre:
        return nombre
    return cid or "Sin nombre"

def write_historia_cliente(cliente_id: str, nombre: str, turno_row: pd.Series):
    """
    Crea/actualiza carpeta del cliente y guarda:
    - un TXT por turno con resumen
    - un CSV 'historial.csv' por cliente
    - agrega entrada al historial global
    """
    carpeta = HISTORIAS_DIR / f"{cliente_id}_{slugify(nombre)}"
    carpeta.mkdir(parents=True, exist_ok=True)

    # TXT por turno
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    turnoid = turno_row["Turno_ID"]
    txt_path = carpeta / f"{ts}_{turnoid}.txt"
    resumen = []
    resumen.append(f"Fecha archivo: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    resumen.append(f"Turno_ID: {turnoid}")
    resumen.append(f"Cliente_ID: {cliente_id}")
    resumen.append(f"Nombre: {nombre}")
    resumen.append(f"Turno Fecha: {turno_row.get('Fecha','')}")
    resumen.append(f"Horario: {turno_row.get('Inicio','')} - {turno_row.get('Fin','')}")
    resumen.append(f"Tipo: {turno_row.get('Tipo','')}")
    resumen.append(f"Zonas: {turno_row.get('Zonas','')}")
    resumen.append(f"Duración (min): {turno_row.get('Duracion_total','')}")
    resumen.append(f"Estado: {turno_row.get('Estado','')}")
    resumen.append(f"Notas: {turno_row.get('Notas','')}")
    txt_path.write_text("\n".join(resumen), encoding="utf-8")

    # CSV por cliente
    cli_hist_path = carpeta / "historial.csv"
    cols_cli = ["Fecha","Evento","Turno_ID","Tipo","Zonas","Duracion_min","Notas"]
    nuevo_cli = pd.DataFrame([{
        "Fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "Evento": "Turno finalizado",
        "Turno_ID": turnoid,
        "Tipo": turno_row.get("Tipo",""),
        "Zonas": turno_row.get("Zonas",""),
        "Duracion_min": turno_row.get("Duracion_total",""),
        "Notas": turno_row.get("Notas",""),
    }])
    if cli_hist_path.exists():
        df_cli = pd.read_csv(cli_hist_path, dtype=str).fillna("")
        df_cli = pd.concat([df_cli, nuevo_cli], ignore_index=True)
    else:
        df_cli = nuevo_cli[cols_cli] if set(cols_cli).issubset(nuevo_cli.columns) else nuevo_cli
    df_cli.to_csv(cli_hist_path, index=False, encoding="utf-8")

    # Historial global
    global_hist = load_df("historial")
    nuevo_global = pd.DataFrame([{
        "Cliente_ID": cliente_id,
        "Nombre": nombre,
        "Fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "Evento": "Turno finalizado",
        "Detalles": f"{turno_row.get('Tipo','')} | {turno_row.get('Zonas','')} | {turno_row.get('Fecha','')} {turno_row.get('Inicio','')}-{turno_row.get('Fin','')}"
    }])
    global_hist = pd.concat([global_hist, nuevo_global], ignore_index=True)
    save_df("historial", global_hist)

def find_cliente_hist_path(cliente_id: str):
    """
    Busca la carpeta data/historias/<cliente_id>_* y devuelve (hist_csv_path, carpeta_path).
    Si no existe, retorna (None, None).
    """
    for p in (HISTORIAS_DIR).glob(f"{cliente_id}_*"):
        hist_csv = p / "historial.csv"
        if hist_csv.exists():
            return hist_csv, p
    return None, None

def go_home():
    st.session_state["vista"] = "home"
    st.rerun()

# =========================
# ESTADO INICIAL
# =========================
if "vista" not in st.session_state:
    st.session_state["vista"] = "home"

_defaults_booking_state = {
    "step": "pick_service",  # pick_service -> pick_date -> pick_time -> client_details -> confirm
    "service_tipo": None,
    "service_zonas": None,
    "duracion": 0,
    "precio_total": 0,
    "fecha": None,
    "slot_dt": None,
    "nombre": "",
    "whatsapp": "",
    "email": "",
    "notas": "",
}
if "booking" not in st.session_state:
    st.session_state["booking"] = _defaults_booking_state.copy()

# =========================
# ESTILOS (CSS simple)
# =========================
st.markdown("""
<style>
:root {
  --card-bg: #ffffff;
  --card-br: 14px;
  --card-bd: 1px solid #ececec;
  --soft-shadow: 0 2px 10px rgba(0,0,0,0.06);
}
.card { background:var(--card-bg); border:var(--card-bd); border-radius:var(--card-br); padding:16px; box-shadow:var(--soft-shadow); }
.step-title { font-weight:700; font-size:20px; margin:6px 0 14px; }
.touch-btn button, .touch-full button { padding:10px 14px !important; border-radius:10px !important; }
.badge { display:inline-block; padding:2px 8px; border-radius:10px; background:#EEF2FF; color:#344; font-size:12px; margin-right:6px;}
.small { font-size:13px; color:#666; }
hr { border:none; border-top:1px solid #eee; margin:8px 0 16px; }
.confirm-box { background:#F6FFED; border:1px solid #B7EB8F; border-radius:12px; padding:16px; }

/* Mobile tweaks */
@media (max-width: 768px) {
  .step-title { font-size:18px; }
  .card { padding:12px; }
  .touch-full button { width: 100% !important; }
}
</style>
""", unsafe_allow_html=True)

# =========================
# HEADER
# =========================
st.title(APP_TITLE)

# =========================
# HOME (Landing)
# =========================
if st.session_state["vista"] == "home":
    left, right = st.columns([3, 1])
    with left:
        st.markdown("## Bienvenida 👋")
        st.write("Elegí una opción para continuar.")
        if st.button("🗓️ Reservar turno", type="primary", use_container_width=True):
            st.session_state["vista"] = "reserva"
            st.session_state["booking"] = _defaults_booking_state.copy()
            st.rerun()
    with right:
        st.markdown("#### Acceso")
        if st.button("🔑 Panel del administrador", use_container_width=True):
            st.session_state["vista"] = "login_admin"
            st.rerun()
    st.stop()

# =========================
# LOGIN ADMIN
# =========================
if st.session_state["vista"] == "login_admin":
    st.markdown("### 🔐 Ingresar al panel")
    colA, colB = st.columns(2)
    user = colA.text_input("Usuario")
    pwd = colB.text_input("Contraseña", type="password")
    c1, c2 = st.columns([1, 3])
    if c1.button("Ingresar", type="primary"):
        if user == ADMIN_USER and pwd == ADMIN_PASS:
            st.session_state["vista"] = "admin"
            st.rerun()
        else:
            st.error("Usuario o contraseña incorrectos.")
    if c2.button("⬅ Volver al inicio"):
        go_home()
    st.stop()

# =========================
# RESERVA — TIPO CALENDLY (grupos exclusivos + sueltas)
# =========================
if st.session_state["vista"] == "reserva":
    servicios_df = load_df("servicios")
    turnos_df = load_df("turnos")
    clientes_df = load_df("clientes")

    if st.button("⬅ Volver al inicio"):
        go_home()

    st.markdown("### Reservá tu turno en 3 pasos")
    booking = st.session_state["booking"]

    # STEP 1 — Elegir Servicio (grupos exclusivos + sueltas)
    if booking["step"] == "pick_service":
        st.markdown('<div class="step-title">1) Elegí tu servicio</div>', unsafe_allow_html=True)

        if servicios_df.empty:
            st.warning("No hay servicios cargados. Volvé más tarde.")
            st.stop()

        tipos_raw = [t for t in servicios_df["Tipo"].unique().tolist() if str(t).strip() != ""]
        prefer = ["Descartable", "Láser"]
        tipos = [t for t in prefer if t in tipos_raw] + [t for t in tipos_raw if t not in prefer]

        tipo_sel = st.selectbox("Tipo", tipos, index=0, key="tipo_sel")
        zonas_tipo = servicios_df[(servicios_df["Tipo"] == tipo_sel) & (servicios_df["Zona"].str.strip() != "")]["Zona"].unique().tolist()

        GROUP_RULES = {
            "Piernas": ["Medias piernas", "Piernas completas"],
            "Brazos":  ["Brazos", "Medio brazo"],
            "Rostro":  ["Rostro completo", "Cara"],
        }

        with st.container():
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown("##### Zonas")
            seleccion_grupos = []
            for grupo, miembros in GROUP_RULES.items():
                presentes = [m for m in miembros if m in zonas_tipo]
                if len(presentes) >= 2:
                    choice = st.radio(
                        f"{grupo}",
                        ["Ninguna"] + presentes, index=0, horizontal=True, key=f"radio_{tipo_sel}_{grupo}"
                    )
                    if choice != "Ninguna":
                        seleccion_grupos.append(choice)

            usados_en_grupos = {m for ml in GROUP_RULES.values() for m in ml}
            zonas_sueltas = [z for z in zonas_tipo if z not in usados_en_grupos]
            zonas_extra = st.multiselect("Otras zonas (podés elegir varias)", zonas_sueltas, key=f"otras_{tipo_sel}") if zonas_sueltas else []
            st.markdown('</div>', unsafe_allow_html=True)

        zonas_final = list(dict.fromkeys(seleccion_grupos + zonas_extra))
        dur_preview = calc_duracion(servicios_df, tipo_sel, zonas_final) if zonas_final else 0
        precio_preview = calc_precio(servicios_df, tipo_sel, zonas_final) if zonas_final else 0

        c1, c2, c3 = st.columns([1,1,2])
        c1.metric("Duración total", f"{dur_preview} min")
        c2.metric("Precio estimado", f"AR$ {precio_preview:,}")
        c3.caption("La duración y el precio se calculan sumando todas las zonas elegidas.")

        if st.button("Continuar ➡️", type="primary", use_container_width=True):
            if not zonas_final:
                st.warning("Elegí al menos una zona.")
            else:
                booking["service_tipo"] = tipo_sel
                booking["service_zonas"] = zonas_final
                booking["duracion"] = dur_preview
                booking["precio_total"] = precio_preview
                booking["step"] = "pick_date"
                st.session_state["booking"] = booking
                st.rerun()

    # STEP 2 — Elegir Fecha
    if booking["step"] == "pick_date":
        st.markdown('<div class="step-title">2) Elegí la fecha</div>', unsafe_allow_html=True)
        st.caption(f"Servicio: **{booking['service_tipo']}** — Zonas: **{humanize_list(booking['service_zonas'] or [])}** — ⏱ {booking['duracion']} min — AR$ {booking['precio_total']:,}")

        c1, c2 = st.columns([1, 3])
        with c1:
            fecha = st.date_input("Fecha", min_value=date.today(), value=booking["fecha"] or date.today())
            if st.button("⬅ Cambiar zonas"):
                st.session_state["booking"] = _defaults_booking_state.copy()
                st.session_state["booking"]["step"] = "pick_service"
                st.rerun()
        with c2:
            st.info("Luego vas a elegir el horario disponible.")

        if st.button("Siguiente ➡️", type="primary"):
            if not fecha:
                st.warning("Elegí una fecha.")
            else:
                booking["fecha"] = fecha
                booking["step"] = "pick_time"
                st.session_state["booking"] = booking
                st.rerun()

    # STEP 3 — Elegir Horario (selectbox + filtra pasados)
    if booking["step"] == "pick_time":
        st.markdown('<div class="step-title">3) Elegí el horario</div>', unsafe_allow_html=True)
        st.caption(f"{booking['fecha']} — {booking['service_tipo']} / {humanize_list(booking['service_zonas'] or [])} — ⏱ {booking['duracion']} min — AR$ {booking['precio_total']:,}")

        if not booking["fecha"]:
            st.warning("Elegí una fecha.")
        else:
            turnos_df = load_df("turnos")  # refresco
            slots_all = generar_slots(booking["fecha"], booking["duracion"], turnos_df, SLOT_STEP_MIN)
            slots = filter_future_slots(booking["fecha"], slots_all)
            if not slots:
                st.error("No hay horarios disponibles para esa fecha.")
            else:
                # Selectbox (mobile friendly)
                opciones = [s.strftime("%H:%M") for s in slots]
                current_label = booking["slot_dt"].strftime("%H:%M") if booking["slot_dt"] else None
                label_idx = opciones.index(current_label) if current_label in opciones else 0
                sel_label = st.selectbox("Horario disponible", opciones, index=label_idx, key="select_hora")
                # Guardar selección
                sel_dt = [s for s in slots if s.strftime("%H:%M") == sel_label][0]
                if (not booking["slot_dt"]) or (booking["slot_dt"] != sel_dt):
                    booking["slot_dt"] = sel_dt
                    st.session_state["booking"] = booking

        c1, c2 = st.columns(2)
        if c1.button("⬅ Volver a fecha"):
            booking["step"] = "pick_date"
            st.session_state["booking"] = booking
            st.rerun()
        disabled_next = booking["slot_dt"] is None
        if c2.button("Siguiente ➡️", type="primary", disabled=disabled_next):
            booking["step"] = "client_details"
            st.session_state["booking"] = booking
            st.rerun()

    # STEP 4 — Datos del cliente
    if booking["step"] == "client_details":
        st.markdown('<div class="step-title">4) Tus datos</div>', unsafe_allow_html=True)
        st.caption(f"{booking['fecha']} — {booking['slot_dt'].strftime('%H:%M') if booking['slot_dt'] else ''} — {booking['service_tipo']} / {humanize_list(booking['service_zonas'] or [])}")
        turnos_df = load_df("turnos")
        clientes_df = load_df("clientes")

        with st.form("client_form"):
            c1, c2 = st.columns(2)
            nombre = c1.text_input("Nombre y apellido", value=booking["nombre"])
            whatsapp = c2.text_input("WhatsApp (+549...)", value=booking["whatsapp"])
            email = st.text_input("Email (opcional)", value=booking["email"])
            notas = st.text_area("Notas (opcional)", value=booking["notas"])
            submitted = st.form_submit_button("Confirmar turno ✅")
        if submitted:
            if not nombre.strip() or not whatsapp.strip() or not booking["slot_dt"]:
                st.warning("Completá nombre, WhatsApp y elegí un horario.")
            else:
                # Alta/actualización cliente (usa WhatsApp como ID)
                if clientes_df.empty or not (clientes_df["Cliente_ID"].astype(str) == whatsapp.strip()).any():
                    clientes_df = pd.concat([clientes_df, pd.DataFrame([{
                        "Cliente_ID": whatsapp.strip(),
                        "Nombre": nombre.strip(),
                        "WhatsApp": whatsapp.strip(),
                        "Email": email.strip(),
                        "Notas": ""
                    }])], ignore_index=True)
                else:
                    ix = clientes_df.index[clientes_df["Cliente_ID"] == whatsapp.strip()].tolist()[0]
                    if nombre.strip():
                        clientes_df.at[ix, "Nombre"] = nombre.strip()
                    if email.strip():
                        clientes_df.at[ix, "Email"] = email.strip()
                save_df("clientes", clientes_df)

                # Guardar turno
                inicio_str = booking["slot_dt"].strftime("%H:%M")
                fin_str = (booking["slot_dt"] + timedelta(minutes=booking["duracion"])).strftime("%H:%M")
                turno_id = str(uuid.uuid4())[:8]
                zonas_str = humanize_list(booking["service_zonas"] or [])
                new_row = pd.DataFrame([{
                    "Turno_ID": turno_id,
                    "Cliente_ID": whatsapp.strip(),
                    "Fecha": booking["fecha"].strftime("%Y-%m-%d"),
                    "Inicio": inicio_str,
                    "Fin": fin_str,
                    "Tipo": booking["service_tipo"],
                    "Zonas": zonas_str,
                    "Duracion_total": str(booking["duracion"]),
                    "Estado": "Confirmado",
                    "Notas": notas.strip(),
                    "RecordatorioEnviado": ""
                }])
                turnos_df = pd.concat([turnos_df, new_row], ignore_index=True)
                save_df("turnos", turnos_df)

                booking["nombre"] = nombre.strip()
                booking["whatsapp"] = whatsapp.strip()
                booking["email"] = email.strip()
                booking["notas"] = notas.strip()
                booking["step"] = "confirm"
                st.session_state["booking"] = booking
                st.rerun()

        if st.button("⬅ Volver a horario"):
            booking["step"] = "pick_time"
            st.session_state["booking"] = booking
            st.rerun()

    # STEP 5 — Confirmación
    if booking["step"] == "confirm":
        st.success("¡Listo! Tu turno fue confirmado ✅")
        st.markdown("""
        <div class="confirm-box">
        <h4>¡Gracias por reservar!</h4>
        <p>Estos son los detalles de tu turno:</p>
        </div>
        """, unsafe_allow_html=True)
        det1, det2 = st.columns(2)
        with det1:
            st.write(f"**Servicio:** {booking['service_tipo']}")
            st.write(f"**Zonas:** {humanize_list(booking['service_zonas'] or [])}")
            st.write(f"**Duración:** {booking['duracion']} min")
            st.write(f"**Precio estimado:** AR$ {booking['precio_total']:,}")
        with det2:
            st.write(f"**Fecha:** {booking['fecha']}")
            st.write(f"**Horario:** {booking['slot_dt'].strftime('%H:%M') if booking['slot_dt'] else ''}")
            st.write(f"**Nombre:** {booking['nombre']}")
            st.write(f"**WhatsApp:** {booking['whatsapp']}")
            if booking["email"]:
                st.write(f"**Email:** {booking['email']}")
        st.info("Te vamos a recordar tu turno el día anterior 💬")

        colx, coly = st.columns(2)
        if colx.button("📅 Reservar otro turno"):
            st.session_state["booking"] = _defaults_booking_state.copy()
            st.rerun()
        if coly.button("🏠 Volver al inicio"):
            go_home()

# =========================
# PANEL ADMIN
# =========================
if st.session_state["vista"] == "admin":
    top1, top2 = st.columns([1, 3])
    if top1.button("⬅ Volver al inicio"):
        go_home()
    st.success("Ingreso correcto ✅")

    tab_turnos, tab_servicios, tab_clientes, tab_historial = st.tabs(
        ["📆 Turnos", "🧾 Servicios", "👤 Clientes", "📓 Historial"]
    )

    # -------- 📆 TURNOS
    with tab_turnos:
        turnos_df = load_df("turnos")
        clientes_df = load_df("clientes")

        st.markdown("#### Base de turnos (con filtros)")
        c1, c2, c3 = st.columns([1,1,2])
        desde = c1.date_input("Desde", value=date.today())
        hasta = c2.date_input("Hasta", value=date.today() + timedelta(days=14))
        filtro_estado = c3.multiselect("Estado", options=["Confirmado","Reprogramado","Cancelado","No-show","Realizado"], default=["Confirmado","Reprogramado"])

        df_agenda = turnos_df.copy()
        if not df_agenda.empty:
            df_agenda["Fecha"] = pd.to_datetime(df_agenda["Fecha"]).dt.date
            df_agenda = df_agenda[(df_agenda["Fecha"] >= desde) & (df_agenda["Fecha"] <= hasta)]
            if filtro_estado:
                df_agenda = df_agenda[df_agenda["Estado"].isin(filtro_estado)]
        if df_agenda.empty:
            st.info("Sin turnos en el rango / estado seleccionado.")
        else:
            if not clientes_df.empty:
                nombre_map = clientes_df.set_index("Cliente_ID")["Nombre"].to_dict()
                df_agenda["Cliente"] = df_agenda["Cliente_ID"].map(nombre_map).fillna(df_agenda["Cliente_ID"])
            cols = ["Fecha","Inicio","Fin","Cliente","Tipo","Zonas","Estado","Notas","Turno_ID"]
            show = [c for c in cols if c in df_agenda.columns]
            st.dataframe(df_agenda[show].sort_values(by=["Fecha","Inicio"]), use_container_width=True)

        st.divider()

        # -------- 🛠️ EDITAR TURNOS (masivo)
        st.markdown("### 🛠️ Editar turnos (toda la base)")
        base_turnos = load_df("turnos")
        if base_turnos.empty:
            st.info("No hay turnos activos.")
        else:
            estado_options = ["Confirmado","Reprogramado","Cancelado","No-show","Realizado"]
            base_edit = base_turnos.copy()
            base_edit["Fecha"] = base_edit["Fecha"].astype(str)
            edit_turnos = st.data_editor(
                base_edit[["Turno_ID","Cliente_ID","Fecha","Inicio","Fin","Tipo","Zonas","Duracion_total","Estado","Notas"]],
                num_rows="dynamic",
                use_container_width=True,
                key="edit_turnos_all",
                column_config={
                    "Estado": st.column_config.SelectboxColumn(options=estado_options),
                    "Fecha": st.column_config.TextColumn(help="YYYY-MM-DD"),
                    "Inicio": st.column_config.TextColumn(help="HH:MM"),
                    "Fin": st.column_config.TextColumn(help="HH:MM"),
                    "Notas": st.column_config.TextColumn(width="large"),
                }
            )
            if st.button("💾 Guardar cambios de turnos"):
                out = edit_turnos.copy()
                out["Fecha"] = pd.to_datetime(out["Fecha"], errors="coerce").dt.date.astype(str)
                save_df("turnos", out)
                st.success("Cambios guardados.")
                st.rerun()

        st.divider()

        # ---- ✅ Finalizar turno y archivar en carpeta del cliente
        st.markdown("### ✅ Finalizar turno y archivar")

        pendientes = turnos_df[~turnos_df["Estado"].isin(["Realizado", "Cancelado"])]
        if pendientes.empty:
            st.info("No hay turnos pendientes para finalizar.")
        else:
            # Etiqueta que incluye NOMBRE (– email), fecha y detalle
            def fmt_turno(tid: str) -> str:
                row = pendientes[pendientes["Turno_ID"] == tid].iloc[0]
                etiqueta_cliente = str(row["Cliente_ID"])
                if not clientes_df.empty and (clientes_df["Cliente_ID"] == row["Cliente_ID"]).any():
                    cli_row = clientes_df[clientes_df["Cliente_ID"] == row["Cliente_ID"]].iloc[0]
                    etiqueta_cliente = get_cliente_display_row(cli_row)
                return f"{etiqueta_cliente} | {row['Fecha']} {row['Inicio']} | {row['Tipo']} - {row['Zonas']}"

            sel_turno_id = st.selectbox(
                "Turno pendiente",
                pendientes["Turno_ID"].tolist(),
                format_func=fmt_turno
            )

            colA, colB = st.columns([2, 2])
            is_new = colB.checkbox("Cliente nuevo")

            if is_new:
                n1, n2 = st.columns(2)
                nuevo_nombre = n1.text_input("Nombre y apellido *")
                nuevo_whats  = n2.text_input("WhatsApp (+549...) *")
                nuevo_email  = st.text_input("Email")
            else:
                if clientes_df.empty:
                    st.warning("No hay clientes cargados. Marcá 'Cliente nuevo'.")
                    nuevo_nombre = nuevo_whats = nuevo_email = ""
                else:
                    cliente_ids = clientes_df["Cliente_ID"].astype(str).tolist()
                    def fmt_cliente(cid: str) -> str:
                        row = clientes_df[clientes_df["Cliente_ID"] == cid].iloc[0]
                        return get_cliente_display_row(row)
                    sel_cliente_id = st.selectbox("Cliente existente", cliente_ids, format_func=fmt_cliente)
                    row_sel = clientes_df[clientes_df["Cliente_ID"] == sel_cliente_id].iloc[0]
                    nuevo_nombre = str(row_sel.get("Nombre", "") or "")
                    nuevo_whats  = str(row_sel.get("Cliente_ID", "") or "")
                    nuevo_email  = str(row_sel.get("Email", "") or "")

            notas_adic = st.text_area("Notas adicionales para el archivo (opcional)")

            if st.button("Finalizar y archivar", type="primary"):
                if is_new and (not nuevo_nombre.strip() or not nuevo_whats.strip()):
                    st.error("Completá nombre y WhatsApp para crear cliente nuevo.")
                else:
                    # 1) Alta cliente si corresponde
                    clientes = load_df("clientes")
                    if is_new:
                        if (clientes["Cliente_ID"] == nuevo_whats.strip()).any():
                            st.warning("Ese Cliente_ID (WhatsApp) ya existe, se usará el existente.")
                        else:
                            clientes = pd.concat([clientes, pd.DataFrame([{
                                "Cliente_ID": nuevo_whats.strip(),
                                "Nombre": nuevo_nombre.strip(),
                                "WhatsApp": nuevo_whats.strip(),
                                "Email": nuevo_email.strip(),
                                "Notas": ""
                            }])], ignore_index=True)
                            save_df("clientes", clientes)

                    # 2) Marcar turno como Realizado
                    turnos = load_df("turnos")
                    ix = turnos.index[turnos["Turno_ID"] == sel_turno_id].tolist()
                    if not ix:
                        st.error("No se encontró el turno.")
                    else:
                        irow = ix[0]
                        turnos.at[irow, "Cliente_ID"] = nuevo_whats.strip() or turnos.at[irow, "Cliente_ID"]
                        turnos.at[irow, "Estado"] = "Realizado"
                        if notas_adic.strip():
                            prev = str(turnos.at[irow, "Notas"] or "")
                            turnos.at[irow, "Notas"] = (prev + " | " if prev else "") + notas_adic.strip()
                        save_df("turnos", turnos)

                        # 3) Escribir historia
                        row_turno = turnos.loc[irow]
                        nombre_para_guardar = (nuevo_nombre.strip() or
                                               (clientes[clientes["Cliente_ID"] == row_turno["Cliente_ID"]].iloc[0]["Nombre"]
                                                if not clientes.empty and (clientes["Cliente_ID"] == row_turno["Cliente_ID"]).any()
                                                else ""))

                        write_historia_cliente(
                            cliente_id=str(row_turno["Cliente_ID"]),
                            nombre=nombre_para_guardar,
                            turno_row=row_turno
                        )

                        st.success("Turno finalizado y archivado en carpeta del cliente ✅")
                        st.info(f"Carpeta: data/historias/{row_turno['Cliente_ID']}_{slugify(nombre_para_guardar)}")
                        st.rerun()

    # -------- 🧾 SERVICIOS
    with tab_servicios:
        servicios_df = load_df("servicios")
        st.markdown("#### Duraciones y costos")
        st.caption("Podés editar los valores directamente y guardar.")
        edit_serv_tab = st.data_editor(
            servicios_df[["Tipo","Zona","Duracion_min","Precio"]],
            num_rows="dynamic",
            use_container_width=True,
            key="edit_servicios_tab"
        )
        if st.button("💾 Guardar (servicios)", key="save_serv_tab"):
            for c in ["Duracion_min", "Precio"]:
                edit_serv_tab[c] = pd.to_numeric(edit_serv_tab[c], errors="coerce").fillna(0).astype(int)
            save_df("servicios", edit_serv_tab)
            st.success("Servicios guardados.")

    # -------- 👤 CLIENTES
    with tab_clientes:
        clientes_df = load_df("clientes")
        st.markdown("#### Base de clientes")
        st.caption("Campos: Cliente_ID (WhatsApp), Nombre, WhatsApp, Email, Notas")
        edit_cli = st.data_editor(
            clientes_df,
            num_rows="dynamic",
            use_container_width=True,
            key="edit_clientes"
        )
        if st.button("💾 Guardar clientes"):
            save_df("clientes", edit_cli)
            st.success("Clientes guardados.")

    # -------- 📓 HISTORIAL (selector por cliente + global)
    with tab_historial:
        st.markdown("#### Historial por cliente")

        clientes_df = load_df("clientes")
        if clientes_df.empty:
            st.info("Aún no hay clientes cargados.")
        else:
            def fmt_cliente(cid: str) -> str:
                row = clientes_df[clientes_df["Cliente_ID"] == cid].iloc[0]
                return get_cliente_display_row(row)

            cliente_ids = clientes_df["Cliente_ID"].astype(str).tolist()
            sel_cliente_id = st.selectbox("Elegí un cliente", cliente_ids, format_func=fmt_cliente)

            # Ficha del cliente
            row_cli = clientes_df[clientes_df["Cliente_ID"] == sel_cliente_id].iloc[0]
            c1, c2, c3 = st.columns(3)
            c1.metric("Nombre", str(row_cli.get("Nombre", "") or "-"))
            c2.metric("WhatsApp", str(row_cli.get("WhatsApp", "") or "-"))
            c3.metric("Email", str(row_cli.get("Email", "") or "-"))

            st.divider()

            # Intentar cargar historial del folder del cliente
            hist_csv_path, carpeta_path = find_cliente_hist_path(sel_cliente_id)

            if hist_csv_path is not None:
                st.markdown("##### Historial del cliente (carpeta dedicada)")
                df_cli_hist = pd.read_csv(hist_csv_path, dtype=str).fillna("")
                if "Fecha" in df_cli_hist.columns:
                    _tmp = pd.to_datetime(df_cli_hist["Fecha"], errors="coerce")
                    df_cli_hist = df_cli_hist.assign(_ord=_tmp).sort_values("_ord", ascending=False).drop(columns=["_ord"])
                st.dataframe(df_cli_hist, use_container_width=True)
                st.download_button(
                    "⬇️ Descargar historial CSV",
                    data=df_cli_hist.to_csv(index=False).encode("utf-8"),
                    file_name=f"historial_{sel_cliente_id}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
                st.caption(f"Carpeta: {carpeta_path.as_posix()}")
            else:
                st.markdown("##### Historial del cliente (desde historial global)")
                hist_global = load_df("historial")
                df_filt = hist_global[hist_global["Cliente_ID"] == sel_cliente_id].copy()
                if df_filt.empty:
                    st.info("Este cliente aún no tiene historial cargado.")
                else:
                    if "Fecha" in df_filt.columns:
                        _tmp = pd.to_datetime(df_filt["Fecha"], errors="coerce")
                        df_filt = df_filt.assign(_ord=_tmp).sort_values("_ord", descending=False).drop(columns=["_ord"])
                        df_filt = df_filt.sort_values("_ord", ascending=False).drop(columns=["_ord"])
                    st.dataframe(df_filt, use_container_width=True)
                    st.download_button(
                        "⬇️ Descargar historial (global filtrado) CSV",
                        data=df_filt.to_csv(index=False).encode("utf-8"),
                        file_name=f"historial_global_{sel_cliente_id}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )

        st.divider()
        st.markdown("#### Historial global (solo lectura)")
        hist = load_df("historial")
        st.dataframe(hist.sort_values(by="Fecha", ascending=False), use_container_width=True)

# =============================
# Footer
# =============================
st.markdown("---")
st.caption("Hecho por PiDBiM")
