# ==========================================================
# Estética | Turnos tipo Calendly (Local, sin Google/Secrets)
# Landing + Reserva paso a paso + Admin (Agenda, Servicios, Clientes)
# - Mejora: selección por grupos exclusivos (Piernas, Brazos, Rostro) + zonas sueltas
# ==========================================================
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, time, date
import uuid
from pathlib import Path

# =========================
# CONFIG GENERAL
# =========================
st.set_page_config(page_title="Turnos Estética", page_icon="💆‍♀️", layout="wide")

APP_TITLE = "💆‍♀️ Turnos Estética"
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

FILES = {
    "servicios": DATA_DIR / "servicios.csv",
    "clientes": DATA_DIR / "clientes.csv",
    "turnos": DATA_DIR / "turnos.csv",
}

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

def load_df(name: str) -> pd.DataFrame:
    ensure_files()
    df = pd.read_csv(FILES[name], dtype=str).fillna("")

    if name == "servicios":
        for col in ["Tipo", "Zona"]:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()
        df = df[(df["Tipo"] != "") & (df["Zona"] != "")]
        for c in ["Duracion_min", "Precio"]:
            if c in df.columns:
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
    return ", ".join(items)

def calc_duracion(servicios_df: pd.DataFrame, tipo: str, zonas: list[str]) -> int:
    sel = servicios_df[(servicios_df["Tipo"] == tipo) & (servicios_df["Zona"].isin(zonas))]
    if sel.empty:
        return 0
    return int(sel["Duracion_min"].sum())

def calc_precio(servicios_df: pd.DataFrame, tipo: str, zonas: list[str]) -> int:
    sel = servicios_df[(servicios_df["Tipo"] == tipo) & (servicios_df["Zona"].isin(zonas))]
    if sel.empty:
        return 0
    return int(sel["Precio"].sum())

def generar_slots(date_obj: date, dur_min: int, turnos_df: pd.DataFrame, slot_step_min: int = SLOT_STEP_MIN):
    if dur_min <= 0:
        return []
    weekday = date_obj.isoweekday()
    tramos = DEFAULT_DISPONIBILIDAD_CODE.get(weekday, [])
    if not tramos:
        return []

    day_turnos = pd.DataFrame()
    if not turnos_df.empty:
        day_turnos = turnos_df[(turnos_df["Fecha"] == date_obj) &
                               (~turnos_df["Estado"].isin(["Cancelado", "No-show"]))].copy()

    result = []
    step = timedelta(minutes=slot_step_min)
    dur = timedelta(minutes=dur_min)
    buff = timedelta(minutes=BUFFER_MIN_DEFAULT)

    for (ini, fin) in tramos:
        ti = to_time(ini)
        tf = to_time(fin)
        if not ti or not tf:
            continue
        start_dt = datetime.combine(date_obj, ti)
        end_window = datetime.combine(date_obj, tf)
        current = start_dt
        while current + dur <= end_window:
            c_start = current
            c_end = current + dur
            ok = True
            if not day_turnos.empty:
                for _, t in day_turnos.iterrows():
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

def go_home():
    st.session_state["vista"] = "home"
    st.rerun()

# =========================
# ESTADO INICIAL
# =========================
if "vista" not in st.session_state:
    st.session_state["vista"] = "home"

_defaults_booking_state = {
    "step": "pick_service",
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
.step-title { font-weight:700; font-size:20px; margin:4px 0 12px; }
.confirm-box { background:#F6FFED; border:1px solid #B7EB8F; border-radius:12px; padding:16px; }
.muted { color:#666; font-size:13px; }
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
# RESERVA — TIPO CALENDLY
# =========================
if st.session_state["vista"] == "reserva":
    servicios_df = load_df("servicios")
    turnos_df = load_df("turnos")
    clientes_df = load_df("clientes")

    if st.button("⬅ Volver al inicio"):
        go_home()

    st.markdown("### Reservá tu turno en 3 pasos")
    booking = st.session_state["booking"]

    # === STEP 1 — Elegir Servicio (grupos exclusivos + zonas sueltas)
    if booking["step"] == "pick_service":
        st.markdown('<div class="step-title">1) Elegí tu servicio</div>', unsafe_allow_html=True)

        if servicios_df.empty:
            st.warning("No hay servicios cargados. Volvé más tarde.")
            st.stop()

        # Tipos y orden preferido
        tipos_raw = [t for t in servicios_df["Tipo"].unique().tolist() if str(t).strip() != ""]
        prefer = ["Descartable", "Láser"]
        tipos = [t for t in prefer if t in tipos_raw] + [t for t in tipos_raw if t not in prefer]

        tipo_sel = st.selectbox("Tipo", tipos, index=0, key="tipo_sel")

        # Zonas disponibles para el tipo seleccionado
        zonas_tipo = servicios_df[(servicios_df["Tipo"] == tipo_sel) & (servicios_df["Zona"].str.strip() != "")]["Zona"].unique().tolist()

        # Definir grupos exclusivos (solo se muestran si existen sus opciones en el catálogo)
        GROUP_RULES = {
            "Piernas": ["Medias piernas", "Piernas completas"],
            "Brazos":  ["Brazos", "Medio brazo"],
            "Rostro":  ["Rostro completo", "Cara"],
        }

        # Radios por grupo exclusivo
        seleccion_grupos = []
        for grupo, miembros in GROUP_RULES.items():
            presentes = [m for m in miembros if m in zonas_tipo]
            if len(presentes) >= 2:  # solo tiene sentido si hay al menos 2 variantes
                st.markdown(f"##### {grupo} (exclusivo)")
                choice = st.radio(
                    f"Elegí una sola opción de {grupo.lower()} (o ninguna)",
                    ["Ninguna"] + presentes, index=0, horizontal=True, key=f"radio_{tipo_sel}_{grupo}"
                )
                if choice != "Ninguna":
                    seleccion_grupos.append(choice)

        # Zonas sueltas = todas menos las de los grupos
        usados_en_grupos = {m for ml in GROUP_RULES.values() for m in ml}
        zonas_sueltas = [z for z in zonas_tipo if z not in usados_en_grupos]
        if zonas_sueltas:
            st.markdown("##### Otras zonas")
            zonas_extra = st.multiselect("Podés elegir múltiples zonas", zonas_sueltas, key=f"otras_{tipo_sel}")
        else:
            zonas_extra = []

        # Construir selección final
        zonas_final = list(dict.fromkeys(seleccion_grupos + zonas_extra))

        # Feedback de duración y precio
        dur_preview = calc_duracion(servicios_df, tipo_sel, zonas_final) if zonas_final else 0
        precio_preview = calc_precio(servicios_df, tipo_sel, zonas_final) if zonas_final else 0

        c1, c2, c3 = st.columns([1,1,2])
        c1.metric("Duración total", f"{dur_preview} min")
        c2.metric("Precio estimado", f"AR$ {precio_preview:,}")
        c3.caption("La duración y el precio se calculan sumando todas las zonas elegidas.")

        if st.button("Continuar con estas zonas ➡️", type="primary", use_container_width=True):
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

    # === STEP 2 — Elegir Fecha
    if booking["step"] == "pick_date":
        st.markdown('<div class="step-title">2) Elegí la fecha</div>', unsafe_allow_html=True)
        st.caption(f"Servicio: **{booking['service_tipo']}** — Zonas: **{humanize_list(booking['service_zonas'] or [])}** — ⏱ {booking['duracion']} min — AR$ {booking['precio_total']:,}")

        c1, c2 = st.columns([1, 3])
        with c1:
            fecha = st.date_input("Fecha", min_value=date.today(), value=booking["fecha"] or date.today())
            if st.button("⬅ Cambiar selección de zonas"):
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

    # === STEP 3 — Elegir Horario
    if booking["step"] == "pick_time":
        st.markdown('<div class="step-title">3) Elegí el horario</div>', unsafe_allow_html=True)
        st.caption(f"{booking['fecha']} — {booking['service_tipo']} / {humanize_list(booking['service_zonas'] or [])} — ⏱ {booking['duracion']} min — AR$ {booking['precio_total']:,}")

        if not booking["fecha"]:
            st.warning("Elegí una fecha.")
        else:
            turnos_df = load_df("turnos")  # refresco
            slots = generar_slots(booking["fecha"], booking["duracion"], turnos_df, SLOT_STEP_MIN)
            if not slots:
                st.error("No hay horarios disponibles para esa fecha.")
            else:
                st.markdown("#### Horarios disponibles")
                ncols = 4
                rows = (len(slots) + ncols - 1) // ncols
                selected = booking["slot_dt"]

                for r in range(rows):
                    cols = st.columns(ncols)
                    for c in range(ncols):
                        i = r * ncols + c
                        if i >= len(slots):
                            continue
                        s = slots[i]
                        label = s.strftime("%H:%M")
                        with cols[c]:
                            if st.button(label, key=f"slot_{booking['fecha']}_{label}"):
                                selected = s
                                booking["slot_dt"] = s
                                st.session_state["booking"] = booking
                                st.rerun()

                if selected:
                    st.success(f"Seleccionaste: **{selected.strftime('%H:%M')}**")

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

    # === STEP 4 — Datos del cliente
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

    # === STEP 5 — Confirmación
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

    tab_turnos, tab_servicios, tab_clientes = st.tabs(["📆 Ver y gestionar turnos", "🧾 Duraciones y costos", "👤 Clientes"])

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

        st.markdown("### 🧾 Duraciones y costos (servicios)")
        servicios_df = load_df("servicios")
        st.caption("Podés editar los valores directamente y guardar.")
        edit_serv = st.data_editor(
            servicios_df[["Tipo","Zona","Duracion_min","Precio"]],
            num_rows="dynamic",
            use_container_width=True,
            key="edit_servicios_inline"
        )
        if st.button("💾 Guardar servicios"):
            for c in ["Duracion_min", "Precio"]:
                edit_serv[c] = pd.to_numeric(edit_serv[c], errors="coerce").fillna(0).astype(int)
            save_df("servicios", edit_serv)
            st.success("Servicios guardados.")

        st.divider()

        st.markdown("### 🛠️ Editar turnos (toda la base en una sola tabla)")
        st.caption("Cambiá Estado, reprogramá Fecha/Inicio/Fin o ajustá Notas.")
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
                    "Fecha": st.column_config.TextColumn(help="Formato YYYY-MM-DD"),
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

    with tab_servicios:
        servicios_df = load_df("servicios")
        st.markdown("#### Duraciones y costos")
        st.caption("Vista y edición simple del catálogo.")
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

# =============================
# Footer
# =============================
st.markdown("---")
st.caption("Hecho por PiDBiM")
