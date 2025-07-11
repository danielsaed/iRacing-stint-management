import streamlit as st
import pandas as pd
from datetime import datetime, time
from pymongo import MongoClient

# --- CONFIGURACIÓN INICIAL Y GESTIÓN DE DATOS ---

# Paleta de colores seguros y visualmente distintos
SAFE_COLOR_PALETTE = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#9467bd", "#8c564b", 
    "#e377c2", "#7f7f7f", "#bcbd22", "#17becf", "#4A90E2"
]

def get_color_for_pilot(pilot_name, pilot_list):
    """Asigna un color consistente a un piloto de una lista."""
    if pilot_name == "Sin Asignar" or not pilot_name:
        return "#f0f2f6"
    try:
        index = pilot_list.index(pilot_name)
        return SAFE_COLOR_PALETTE[index % len(SAFE_COLOR_PALETTE)]
    except (ValueError, IndexError):
        return SAFE_COLOR_PALETTE[hash(pilot_name) % len(SAFE_COLOR_PALETTE)]

def get_default_team_structure(team_name="Equipo por Defecto", duration=24):
    """Crea la estructura de datos para un nuevo equipo con duración variable."""
    return {
        "race_config": {"start_hour": 14, "duration": duration},
        "pilots": pd.DataFrame({
            'Piloto': ['Piloto 1', 'Piloto 2', 'Piloto 3', 'Piloto 4'],
            'Quiere Empezar': [False, True, False, False],
            'Quiere Terminar': [False, False, True, False],
            'Horas Límite (Opcional)': [0, 0, 0, 0],
            **{str(h): [True] * 4 for h in range(duration)}
        }).to_dict('records'),
        "horario": pd.DataFrame({
            "Piloto al Volante": ["Sin Asignar"] * duration,
            "Comentarios": [""] * duration
        }).to_dict('records')
    }

# --- FUNCIONES DE CARGA Y GUARDADO PARA MONGODB ---
@st.cache_resource
def init_connection():
    return MongoClient(**st.secrets["mongo"])

def load_data(_client):
    db = _client.iracing_dashboard_db
    collection = db.teams_data
    stored_data = collection.find_one({"_id": "main_database"})
    if stored_data is None:
        default_data = {"Equipo por Defecto": get_default_team_structure()}
        collection.insert_one({"_id": "main_database", "data": default_data})
        return default_data
    return stored_data["data"]

def save_data(_client, data):
    db = _client.iracing_dashboard_db
    collection = db.teams_data
    collection.update_one({"_id": "main_database"}, {"$set": {"data": data}}, upsert=True)

# --- INICIALIZACIÓN DE LA APP ---
st.set_page_config(layout="wide", page_title="Stints iRacing")

# CONECTAR A MONGODB Y CARGAR DATOS
client = init_connection()
if 'db' not in st.session_state:
    st.session_state.db = load_data(client)

# --- CONTENIDO PRINCIPAL ---
st.markdown("<h1 style='text-align: center;'>🏁 iRacing Endurance Stints</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center;'>Selecciona un equipo o crea uno nuevo para planificar la carrera.</p>", unsafe_allow_html=True)
st.markdown("") # Espacio vertical

if 'newly_created_team' in st.session_state:
    st.session_state.selected_team = st.session_state.newly_created_team
    del st.session_state.newly_created_team

team_names = list(st.session_state.db.keys())
# Inicializa selected_team en None si no hay una selección válida
if 'selected_team' not in st.session_state or st.session_state.selected_team not in team_names:
    st.session_state.selected_team = None

# --- SECCIÓN SUPERIOR CENTRADA PARA GESTIÓN DE EQUIPOS ---
_, mid_col_top, _ = st.columns([1, 2, 1])
with mid_col_top:
    # El selectbox ahora puede no tener nada seleccionado
    st.selectbox(
        "Selecciona un Equipo/Evento", 
        options=team_names, 
        key='selected_team',
        index=team_names.index(st.session_state.selected_team) if st.session_state.selected_team and st.session_state.selected_team in team_names else None,
        placeholder="Elige un equipo para empezar"
    )

    with st.expander("Gestionar Equipos"):
        col1, col2 = st.columns(2)
        with col1:
            new_team_name = st.text_input("Nombre del Nuevo Equipo")
            new_team_duration = st.selectbox(
                "Duración de la carrera (Horas)",
                options=[24, 12, 10, 8, 6, 4, 3],
                key="new_team_duration"
            )
            if st.button("➕ Crear Equipo"):
                if new_team_name and new_team_name not in st.session_state.db:
                    st.session_state.db[new_team_name] = get_default_team_structure(
                        team_name=new_team_name,
                        duration=new_team_duration
                    )
                    save_data(client, st.session_state.db)
                    # Actualizamos el estado de la sesión para reflejar el nuevo equipo
                    st.session_state.db = load_data(client)
                    st.session_state.newly_created_team = new_team_name
                    st.rerun()
                else:
                    st.error("El nombre del equipo no puede estar vacío o ya existe.")
        with col2:
            team_to_delete = st.selectbox("Selecciona equipo a eliminar", options=team_names, index=None, placeholder="Seleccionar...")
            if st.button("❌ Eliminar Equipo Seleccionado", type="primary"):
                if team_to_delete and len(st.session_state.db) > 1:
                    del st.session_state.db[team_to_delete]
                    save_data(client, st.session_state.db)
                    # Actualizamos el estado de la sesión para reflejar la eliminación
                    st.session_state.db = load_data(client)
                    st.session_state.selected_team = None # Deseleccionamos el equipo eliminado
                    st.rerun()
                else:
                    st.error("No puedes eliminar el último equipo.")

#st.markdown("---")

# --- CARGA EL RESTO DE LA APP SOLO SI HAY UN EQUIPO SELECCIONADO ---
if not st.session_state.selected_team:
    st.info("Por favor, selecciona o crea un equipo para continuar.")
    st.stop()

# A partir de aquí, todo el código asume que st.session_state.selected_team tiene un valor
team_data = st.session_state.db[st.session_state.selected_team]
config_df = pd.DataFrame(team_data['pilots'])
horario_df = pd.DataFrame(team_data['horario'])
if "Comentarios" not in horario_df.columns:
    horario_df["Comentarios"] = ""

# --- CONFIGURACIÓN DE CARRERA (HORA Y DURACIÓN) ---
race_config = team_data.setdefault('race_config', {'start_hour': 14, 'duration': 24})
start_hour = race_config.get('start_hour', 14)
race_duration = race_config.get('duration', 24)
pilot_list = config_df['Piloto'].dropna().unique().tolist()

# --- SECCIÓN DE CONFIGURACIÓN CENTRADA ---
_, mid_col, _ = st.columns([1, 2, 1])
with mid_col:
    st.subheader(f"Configuración para: **{st.session_state.selected_team}**")
    
    c1, c2 = st.columns(2)
    new_start_time = c1.time_input(
        "Hora de inicio", value=time(start_hour, 0), step=3600, 
        key=f"time_input_{st.session_state.selected_team}"
    )
    # La duración ahora es solo informativa y no se puede cambiar
    c2.selectbox(
        "Duración (Horas)", options=[race_duration], index=0,
        key=f"duration_input_{st.session_state.selected_team}",
        disabled=True,
        help="La duración se establece al crear el equipo y no se puede modificar."
    )

# --- LÓGICA DE ACTUALIZACIÓN DE CONFIGURACIÓN DE CARRERA ---
config_changed = False
if new_start_time.hour != start_hour:
    team_data['race_config']['start_hour'] = new_start_time.hour
    config_changed = True

if config_changed:
    save_data(client, st.session_state.db)
    st.rerun()

# --- EXPANSORES CON LAS TABLAS ---
with st.expander("1. Configuración de Disponibilidad de Pilotos", expanded=True):
    st.write("🎨 **Leyenda de Colores:**")
    cols = st.columns(len(pilot_list) if pilot_list else 1)
    for i, pilot in enumerate(pilot_list):
        color = get_color_for_pilot(pilot, pilot_list)
        cols[i].markdown(f"<div style='background-color:{color}; color:white; padding: 5px; border-radius: 5px; text-align: center;'>{pilot}</div>", unsafe_allow_html=True)
    st.markdown("")
    
    st.info("Nota: Todas las horas se muestran en la zona horaria de CDMX (GMT-6).")

    display_config_df = config_df.copy()
    dynamic_hour_labels = [f"{(start_hour + h) % 24:02d}:00" for h in range(race_duration)]
    column_map = {str(h): dynamic_hour_labels[h] for h in range(race_duration)}
    display_config_df.rename(columns=column_map, inplace=True)
    
    edited_pilots_df = st.data_editor(
        display_config_df, num_rows="dynamic", use_container_width=True,
        column_config={
            "Piloto": st.column_config.TextColumn(width="medium"),
            **{label: st.column_config.CheckboxColumn(width="small") for label in dynamic_hour_labels},
            "Quiere Empezar": st.column_config.CheckboxColumn("Quiere Empezar"),
            "Quiere Terminar": st.column_config.CheckboxColumn("Quiere Terminar"),
            "Horas Límite (Opcional)": st.column_config.NumberColumn("Maximo Horas/Carrera", width="small")
        }
    )
    if st.button("💾 Guardar Configuración de Pilotos"):
        latest_db_data = load_data(client)
        reverse_column_map = {v: k for k, v in column_map.items()}
        df_to_save = edited_pilots_df.copy()
        df_to_save.rename(columns=reverse_column_map, inplace=True)
        
        latest_horario = latest_db_data[st.session_state.selected_team]['horario']
        for i in range(race_duration):
            piloto_asignado = latest_horario[i]['Piloto al Volante']
            if piloto_asignado != "Sin Asignar":
                piloto_config_row = df_to_save[df_to_save['Piloto'] == piloto_asignado]
                if not piloto_config_row.empty:
                    disponible = True
                    if i == 0: disponible = piloto_config_row['Quiere Empezar'].iloc[0]
                    elif i == race_duration - 1: disponible = piloto_config_row['Quiere Terminar'].iloc[0]
                    else: disponible = piloto_config_row[str(i)].iloc[0]
                    
                    if not disponible:
                        latest_horario[i]['Piloto al Volante'] = "Sin Asignar"

        latest_db_data[st.session_state.selected_team]['pilots'] = df_to_save.to_dict('records')
        latest_db_data[st.session_state.selected_team]['horario'] = latest_horario
        save_data(client, latest_db_data)
        st.session_state.db = latest_db_data # Actualiza el estado de la sesión con los nuevos datos
        st.success("Configuración guardada y horario sincronizado.")
        st.rerun()

st.markdown("---")

col_assign, col_summary = st.columns(2, gap="large")

with col_assign:
    st.header("2. Asignación de Stints")
    horas_reales = [f"{(start_hour + h) % 24:02d}:00 - {(start_hour + h + 1) % 24:02d}:00" for h in range(race_duration)]
    
    nuevas_asignaciones = []
    nuevos_comentarios = []
    for i in range(race_duration):
        piloto_actual = horario_df.loc[i, "Piloto al Volante"]
        comentario_actual = horario_df.loc[i, "Comentarios"]
        
        pilotos_disponibles = []
        if i == 0: pilotos_disponibles = edited_pilots_df[edited_pilots_df['Quiere Empezar'] == True]['Piloto'].tolist()
        elif i == race_duration - 1: pilotos_disponibles = edited_pilots_df[edited_pilots_df['Quiere Terminar'] == True]['Piloto'].tolist()
        else:
            hora_label = dynamic_hour_labels[i]
            if hora_label in edited_pilots_df.columns:
                pilotos_disponibles = edited_pilots_df[edited_pilots_df[hora_label] == True]['Piloto'].tolist()
        
        lista_pilotos_filtrada = ["Sin Asignar"] + pilotos_disponibles
        try: default_index = lista_pilotos_filtrada.index(piloto_actual)
        except ValueError: default_index = 0

        row_cols = st.columns([2, 2, 2, 2])
        row_cols[0].write(f"**{horas_reales[i]}**")
        
        seleccion = row_cols[2].selectbox(f"sel_{i}", options=lista_pilotos_filtrada, index=default_index, label_visibility="collapsed", key=f"piloto_hora_{i}_{st.session_state.selected_team}")
        nuevas_asignaciones.append(seleccion)
        comentario = row_cols[3].text_input(f"com_{i}", value=comentario_actual, label_visibility="collapsed", placeholder="Comentarios...", key=f"comentario_hora_{i}_{st.session_state.selected_team}")
        nuevos_comentarios.append(comentario)

        color = get_color_for_pilot(seleccion, pilot_list)
        text_color = 'white' if color != '#f0f2f6' else 'black'
        row_cols[1].markdown(f"<div style='background-color:{color}; color:{text_color}; padding: 8px; border-radius: 5px; text-align: center; margin-top: -8px;'>{seleccion}</div>", unsafe_allow_html=True)

    if st.button("💾 Guardar Horario Asignado", use_container_width=True):
        latest_db_data = load_data(client)
        # Obtenemos una copia del horario para modificarla
        horario_a_guardar = latest_db_data[st.session_state.selected_team]['horario']
        for i in range(race_duration):
            # Comparamos con el horario mostrado en la UI (horario_df)
            if nuevas_asignaciones[i] != horario_df.loc[i, "Piloto al Volante"]:
                horario_a_guardar[i]['Piloto al Volante'] = nuevas_asignaciones[i]
            if nuevos_comentarios[i] != horario_df.loc[i, "Comentarios"]:
                horario_a_guardar[i]['Comentarios'] = nuevos_comentarios[i]
        
        latest_db_data[st.session_state.selected_team]['horario'] = horario_a_guardar
        save_data(client, latest_db_data)
        st.session_state.db = latest_db_data # Actualiza el estado de la sesión con los nuevos datos
        st.success("Horario guardado y fusionado correctamente.")
        st.rerun()

with col_summary:
    st.header("3. Resumen del Horario")
    resumen_df = pd.Series(nuevas_asignaciones).value_counts().drop("Sin Asignar", errors='ignore').reset_index()
    resumen_df.columns = ['Piloto', 'Número de Stints']
    
    st.subheader("📊 Resumen de Stints")
    def style_pilot_col(col):
        return col.apply(lambda pilot: f"background-color: {get_color_for_pilot(pilot, pilot_list)}; color: {'white' if get_color_for_pilot(pilot, pilot_list) != '#f0f2f6' else 'black'}")

    if not resumen_df.empty:
        st.dataframe(resumen_df.style.apply(style_pilot_col, subset=['Piloto']), use_container_width=True, hide_index=True)
    else:
        st.dataframe(resumen_df, use_container_width=True, hide_index=True)

    st.subheader("⚠️ Alertas de Límite")
    alertas_mostradas = False
    for _, row in resumen_df.iterrows():
        piloto_nombre = row['Piloto']
        stints_asignados = row['Número de Stints']
        limite_piloto_df = edited_pilots_df[edited_pilots_df['Piloto'] == piloto_nombre]
        if not limite_piloto_df.empty:
            limite = limite_piloto_df['Horas Límite (Opcional)'].iloc[0]
            if limite > 0 and stints_asignados > limite:
                st.warning(f"**{piloto_nombre}** supera su límite de {int(limite)} stints ({stints_asignados} asignados).")
                alertas_mostradas = True
    
    if not alertas_mostradas:
        st.success("Todos los pilotos están dentro de sus límites.")

    st.subheader("📥 Descargar")
    df_to_download = pd.DataFrame({
        "Hora del Stint": horas_reales, 
        "Piloto al Volante": nuevas_asignaciones,
        "Comentarios": nuevos_comentarios
    })
    csv_data = df_to_download.to_csv(index=False).encode('utf-8')
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    st.download_button(
        label="Descargar Horario en CSV",
        data=csv_data,
        file_name=f"horario_{st.session_state.selected_team}_{timestamp}.csv",
        mime="text/csv",
        use_container_width=True
    )