import streamlit as st
import pandas as pd
import plotly.express as px
from Proyecto3 import CrawlerEmpleo
import re
import os
from urllib.parse import urlparse
from collections import Counter

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Analizador de Ofertas de Empleo",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- TEMA Y ESTILOS AVANZADOS ---
st.markdown("""
    <style>
        html, body, [class*="css"] {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            font-size: 24px;
        }
        .main { background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%); padding: 0; }
        .stMarkdown, .stMarkdown p, .stMarkdown li, .stMarkdown span {
            font-size: 22px !important; line-height: 1.7;
        }
        div[data-testid="stMetric"] {
            background: linear-gradient(135deg, rgba(0,123,255,0.2) 0%, rgba(0,123,255,0.1) 100%);
            padding: 20px; border-radius: 15px; border-left: 5px solid #007bff;
            box-shadow: 0 4px 15px rgba(0,123,255,0.1); transition: transform 0.3s, box-shadow 0.3s;
        }
        div[data-testid="stMetric"]:hover {
            transform: translateY(-5px); box-shadow: 0 8px 25px rgba(0,123,255,0.2);
        }
        div[data-testid="stMetricLabel"] { font-size: 24px !important; font-weight: 600; }
        div[data-testid="stMetricValue"] { font-size: 42px !important; font-weight: 700; }
        div[data-testid="stMetricDelta"]  { font-size: 18px !important; }
        .stButton>button, .stDownloadButton>button {
            border-radius: 10px; height: 52px; font-weight: 600; border: none; color: white;
            background: linear-gradient(135deg, #007bff 0%, #0056b3 100%);
            transition: all 0.3s ease; font-size: 22px !important;
        }
        .stButton>button:hover, .stDownloadButton>button:hover {
            box-shadow: 0 8px 25px rgba(0,123,255,0.5); transform: translateY(-2px);
        }
        [data-testid="stSidebar"] { background: linear-gradient(180deg, #2c3e50 0%, #34495e 100%); }
        [data-testid="stSidebar"] * { color: white; }
        .sidebar-title { color: white; font-size: 30px; font-weight: 700; margin-bottom: 20px; }
        .stTextInput input, .stNumberInput input,
        [data-testid="stTextInput"] input, [data-testid="stNumberInput"] input {
            font-size: 22px !important; padding: 14px !important; height: 52px !important;
        }
        .stSlider label, .stSlider span, [data-testid="stSlider"] * { font-size: 20px !important; }
        .stMultiSelect, [data-testid="stMultiSelect"] { font-size: 20px !important; }
        [data-testid="stMultiSelect"] span { font-size: 18px !important; }
        div[data-baseweb="select"] * { font-size: 20px !important; }
        h1 { color: #2c3e50; font-weight: 700; font-size: 58px !important; }
        h2 { color: #2c3e50; font-weight: 700; font-size: 44px !important; }
        h3 { color: #2c3e50; font-weight: 700; font-size: 34px !important; }
        label, [data-testid="stWidgetLabel"] p { font-size: 22px !important; font-weight: 500; }
        [data-testid="stDataFrame"], [data-testid="stDataFrame"] * { font-size: 18px !important; }
        [data-testid="stDataFrame"] [role="columnheader"] {
            font-size: 18px !important; font-weight: 700 !important;
        }
        hr { border: none; height: 2px;
             background: linear-gradient(90deg, transparent, #007bff, transparent); margin: 30px 0; }
        [data-testid="stTabs"] button[role="tab"] p,
        [data-testid="stTabs"] button[role="tab"] { font-size: 22px !important; font-weight: 600 !important; }
        div[data-testid="stAlert"], div[data-testid="stAlert"] p { font-size: 22px !important; }
        .stCodeBlock, .stCodeBlock pre, .stCodeBlock code { font-size: 18px !important; }
    </style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# FUNCIONES AUXILIARES
# ---------------------------------------------------------------------------

def validar_url(url: str) -> bool:
    """Devuelve True si la URL tiene esquema y netloc válidos."""
    try:
        return all(getattr(urlparse(url), attr) for attr in ["scheme", "netloc"])
    except Exception:
        return False


def normalizar_datos(df: pd.DataFrame) -> pd.DataFrame:
    """Garantiza que el DataFrame tenga la estructura esperada."""
    columnas_base = {
        "Titulo": "",
        "Precio": pd.NA,
        "Categoria": "Desconocida",
        "Descripcion": "",
        "URL": "",
    }
    for col, default in columnas_base.items():
        if col not in df.columns:
            df[col] = default
    df["Precio"] = pd.to_numeric(df["Precio"], errors="coerce")
    return df


# Stopwords: palabras que no aportan valor semántico a los títulos / descripciones
_STOPWORDS = {
    # Ruido de estructura web y redes sociales
    "page", "share", "inicio", "directorio", "gratis", "empleo", "ofertas",
    "candidatos", "empresas", "favoritos", "acceso", "facebook", "twitter",
    "linkedin", "instagram", "correo", "email", "sitio", "web", "enlaces",
    "compartir", "buscar", "resultados", "servicios", "salvador", "menu",
    "contacto", "aviso", "legal", "privacidad", "cookies", "derechos",
    # Palabras genéricas de ofertas de empleo
    "trabajo", "experiencia", "años", "requisitos", "conocimientos",
    "habilidades", "lugar", "puesto", "perfil", "empresa", "vacante", "oferta",
    "para", "como", "sobre", "este", "esta", "estos", "estas", "todo", "toda",
    "todos", "todas", "pero", "bien", "solo", "cuando", "donde", "quien",
    "desde", "hacia", "hasta", "tiene", "tienen", "hacer", "puede", "pueden",
    "requiere", "buscamos", "solicita", "importante", "forma", "parte",
    "curriculum", "enviar", "aplicar", "postularse", "salario", "sueldo",
}


def extraer_palabras_comunes(
    serie_texto: pd.Series,
    top_n: int = 15,
    nombre_columna: str = "Palabra",
) -> pd.DataFrame:
    """
    Extrae las palabras más frecuentes de una serie de textos,
    filtrando stopwords y ruido de navegación web.

    Retorna un DataFrame con columnas [nombre_columna, 'Frecuencia'],
    o un DataFrame vacío si no hay palabras suficientes.
    """
    texto = " ".join(serie_texto.dropna().astype(str)).lower()
    palabras_crudas = re.findall(r"\b[a-záéíóúñ]{4,}\b", texto)
    palabras_limpias = [p for p in palabras_crudas if p not in _STOPWORDS]

    if not palabras_limpias:
        return pd.DataFrame(columns=[nombre_columna, "Frecuencia"])

    return pd.DataFrame(
        Counter(palabras_limpias).most_common(top_n),
        columns=[nombre_columna, "Frecuencia"],
    )


# ---------------------------------------------------------------------------
# SIDEBAR — CONFIGURACIÓN
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown('<div class="sidebar-title">⚙️ Panel de Control</div>', unsafe_allow_html=True)
    st.markdown("---")

    st.markdown("<p style='font-size:24px;font-weight:600;'>🔗 URL Principal</p>", unsafe_allow_html=True)
    url_input = st.text_input(
        "", placeholder="https://ejemplo.com/empleos", label_visibility="collapsed"
    )

    col_max, col_delay = st.columns(2)
    with col_max:
        st.markdown("<p style='font-size:24px;font-weight:600;'>📄 Páginas</p>", unsafe_allow_html=True)
        max_paginas = st.slider("", 1, 300, 50, label_visibility="collapsed")
    with col_delay:
        st.markdown("<p style='font-size:24px;font-weight:600;'>⏱️ Timeout (s)</p>", unsafe_allow_html=True)
        timeout = st.number_input("", 5, 60, 15, label_visibility="collapsed")

    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        btn_start = st.button("🔍 Iniciar", type="primary", use_container_width=True)
    with col2:
        if st.button("🗑️ Limpiar", use_container_width=True) and os.path.exists("datos_extraidos.csv"):
            os.remove("datos_extraidos.csv")
            st.rerun()


# ---------------------------------------------------------------------------
# TÍTULO PRINCIPAL
# ---------------------------------------------------------------------------

st.markdown("""
    <div style="text-align:center; padding:40px 0;
                background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);
                border-radius:15px; color:white; margin-bottom:30px;
                box-shadow:0 10px 20px rgba(0,0,0,0.1);">
        <h1 style="margin:0; font-size:102px; text-shadow:2px 2px 4px rgba(0,0,0,0.3); color:white;">
            Analizador de Ofertas de Empleo
        </h1>
        <p style="margin:20px 0 0 0; font-size:40px; opacity:0.9; color:white;">
            Extracción inteligente y minería de datos
        </p>
    </div>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# LÓGICA DE EXTRACCIÓN
# ---------------------------------------------------------------------------

if btn_start:
    if not url_input or not validar_url(url_input):
        st.error("⚠️ URL inválida (debe incluir http:// o https://).")
    else:
        with st.status("⏳ Analizando sitio web...", expanded=True) as status:
            log_area = st.empty()
            logs: list[str] = []

            def update_logs(msg: str) -> None:
                logs.append(f"• {msg}")
                log_area.code("\n".join(logs[-8:]), language="plaintext")

            try:
                df_datos = CrawlerEmpleo(url_input).recorrer(
                    max_paginas=max_paginas, callback=update_logs
                )
                if df_datos.empty:
                    status.update(label="⚠️ Proceso terminado sin hallazgos", state="complete")
                else:
                    df_datos.to_csv("datos_extraidos.csv", index=False, encoding="utf-8")
                    status.update(label="✓ Extracción completada", state="complete")
                    st.rerun()
            except Exception as e:
                status.update(label="❌ Error crítico", state="error")
                st.error(str(e))


# ---------------------------------------------------------------------------
# CARGA Y PREPROCESAMIENTO DE DATOS
# ---------------------------------------------------------------------------

try:
    df = normalizar_datos(pd.read_csv("datos_extraidos.csv"))
except (FileNotFoundError, pd.errors.EmptyDataError):
    df = pd.DataFrame()


# ---------------------------------------------------------------------------
# DASHBOARD VISUAL INTERACTIVO
# ---------------------------------------------------------------------------

if not df.empty:
    tab1, tab2, tab3, tab4 = st.tabs(
        ["📊 Resumen", "📈 Análisis de Texto", "🔍 Explorador Interactivo", "💾 Exportar"]
    )

    # Datos limpios reutilizados en varias pestañas
    df_precios = df.dropna(subset=["Precio"])
    hay_precios = not df_precios.empty

    # -----------------------------------------------------------------------
    # TAB 1 — RESUMEN Y MÉTRICAS
    # -----------------------------------------------------------------------
    with tab1:
        st.markdown("### 📈 Visión General del Mercado")

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("📊 Ofertas Totales", f"{len(df):,}", f"{df['Categoria'].nunique()} categorías")
        m2.metric("💰 Promedio",  f"${df_precios['Precio'].mean():,.0f}" if hay_precios else "N/A")
        m3.metric("📈 Máximo",    f"${df_precios['Precio'].max():,.0f}"  if hay_precios else "N/A")
        m4.metric("📉 Mínimo",    f"${df_precios['Precio'].min():,.0f}"  if hay_precios else "N/A")

        st.markdown("---")
        c1, c2 = st.columns(2)

        with c1:
            st.markdown(
                "<p style='font-size:26px;font-weight:600;color:#2c3e50;'>🏢 Distribución por Categoría</p>",
                unsafe_allow_html=True,
            )
            cat_counts = df["Categoria"].value_counts().head(10).reset_index()
            cat_counts.columns = ["Categoría", "Cantidad"]
            fig1 = px.bar(
                cat_counts, x="Cantidad", y="Categoría",
                orientation="h", color="Cantidad", text="Cantidad",
            )
            fig1.update_layout(
                yaxis={"categoryorder": "total ascending"},
                showlegend=False,
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(size=18),
            )
            st.plotly_chart(fig1, use_container_width=True)

        with c2:
            st.markdown(
                "<p style='font-size:26px;font-weight:600;color:#2c3e50;'>💰 Distribución Salarial</p>",
                unsafe_allow_html=True,
            )
            if hay_precios:
                fig2 = px.histogram(df_precios, x="Precio", nbins=20, color_discrete_sequence=["#28a745"])
                fig2.update_layout(
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                    font=dict(size=18),
                )
                st.plotly_chart(fig2, use_container_width=True)
            else:
                st.info("📭 Sin datos salariales suficientes.")

    # -----------------------------------------------------------------------
    # TAB 2 — ANÁLISIS DE TEXTO
    # -----------------------------------------------------------------------
    with tab2:
        st.markdown("### 🔠 ¿Qué están buscando las empresas?")
        col1, col2 = st.columns(2)

        with col1:
            st.markdown(
                "<p style='font-size:26px;font-weight:600;color:#2c3e50;'>📌 Palabras más usadas en Títulos</p>",
                unsafe_allow_html=True,
            )
            df_palabras_titulos = extraer_palabras_comunes(df["Titulo"], nombre_columna="Palabra")
            if not df_palabras_titulos.empty:
                fig_t = px.bar(
                    df_palabras_titulos, x="Frecuencia", y="Palabra",
                    orientation="h", color_discrete_sequence=["#6f42c1"],
                )
                fig_t.update_layout(yaxis={"categoryorder": "total ascending"}, font=dict(size=18))
                st.plotly_chart(fig_t, use_container_width=True)
            else:
                st.info("📭 Sin datos de títulos suficientes.")

        with col2:
            st.markdown(
                "<p style='font-size:26px;font-weight:600;color:#2c3e50;'>📝 Palabras más usadas en Descripciones</p>",
                unsafe_allow_html=True,
            )
            df_palabras_desc = extraer_palabras_comunes(df["Descripcion"], nombre_columna="Palabra")
            if not df_palabras_desc.empty:
                fig_d = px.bar(
                    df_palabras_desc, x="Frecuencia", y="Palabra",
                    orientation="h", color_discrete_sequence=["#fd7e14"],
                )
                fig_d.update_layout(yaxis={"categoryorder": "total ascending"}, font=dict(size=18))
                st.plotly_chart(fig_d, use_container_width=True)
            else:
                st.info("📭 Sin datos de descripciones suficientes.")

    # -----------------------------------------------------------------------
    # TAB 3 — EXPLORADOR INTERACTIVO
    # -----------------------------------------------------------------------
    with tab3:
        st.markdown("### Buscador y Filtros")

        f1, f2, f3 = st.columns(3)

        with f1:
            st.markdown(
                "<p style='font-size:24px;font-weight:600;'>🔎 Buscar palabra clave</p>",
                unsafe_allow_html=True,
            )
            busqueda = st.text_input("", label_visibility="collapsed", key="busqueda_input")

        with f2:
            st.markdown(
                "<p style='font-size:24px;font-weight:600;'>📂 Categoría</p>",
                unsafe_allow_html=True,
            )
            categoria_filter = st.multiselect(
                "", options=df["Categoria"].dropna().unique(), label_visibility="collapsed"
            )

        with f3:
            min_p = int(df_precios["Precio"].min()) if hay_precios else 0
            max_p = int(df_precios["Precio"].max()) if hay_precios else 0

            if not hay_precios:
                st.markdown(
                    "<p style='font-size:22px;'>📭 Ofertas sin sueldo definido</p>",
                    unsafe_allow_html=True,
                )
                price_range = (0, 0)
            elif min_p == max_p:
                st.markdown(
                    f"<p style='font-size:22px;'>💡 Salario único: ${min_p}</p>",
                    unsafe_allow_html=True,
                )
                price_range = (min_p, max_p)
            else:
                st.markdown(
                    "<p style='font-size:24px;font-weight:600;'>💰 Rango Salarial</p>",
                    unsafe_allow_html=True,
                )
                price_range = st.slider(
                    "", min_value=min_p, max_value=max_p,
                    value=(min_p, max_p), label_visibility="collapsed",
                )

        # Filtros encadenados
        df_filtrado = df.copy()
        if busqueda:
            mask = df_filtrado.astype(str).apply(
                lambda col: col.str.contains(busqueda, case=False, na=False)
            ).any(axis=1)
            df_filtrado = df_filtrado[mask]
        if categoria_filter:
            df_filtrado = df_filtrado[df_filtrado["Categoria"].isin(categoria_filter)]
        if hay_precios:
            df_filtrado = df_filtrado[
                df_filtrado["Precio"].between(price_range[0], price_range[1])
                | df_filtrado["Precio"].isna()
            ]

        st.markdown(
            f"<p style='font-size:24px;font-weight:600;'>📋 Mostrando {len(df_filtrado)} resultados</p>",
            unsafe_allow_html=True,
        )
        st.dataframe(df_filtrado, use_container_width=True, height=400, hide_index=True)

    # -----------------------------------------------------------------------
    # TAB 4 — EXPORTAR
    # -----------------------------------------------------------------------
    with tab4:
        st.markdown("### 💾 Descarga de Datos")
        e1, e2, e3 = st.columns(3)

        with e1:
            st.download_button(
                "📥 CSV",
                df.to_csv(index=False).encode("utf-8"),
                "analisis.csv",
                "text/csv",
                use_container_width=True,
            )
        with e2:
            st.download_button(
                "📥 JSON",
                df.to_json(orient="records", indent=2).encode("utf-8"),
                "analisis.json",
                "application/json",
                use_container_width=True,
            )
        with e3:
            try:
                import openpyxl  # noqa: F401

                excel_buffer = pd.ExcelWriter("temp.xlsx", engine="openpyxl")
                df.to_excel(excel_buffer, index=False)
                excel_buffer.close()
                with open("temp.xlsx", "rb") as f:
                    st.download_button(
                        "📥 Excel",
                        f.read(),
                        "analisis.xlsx",
                        "application/vnd.ms-excel",
                        use_container_width=True,
                    )
            except ImportError:
                st.button("📥 Excel no disponible", disabled=True, use_container_width=True)

else:
    # ESTADO VACÍO
    st.markdown(
        "<h2 style='text-align:center;color:#667eea;padding:40px;font-size:56px;'>"
        "👋 Ingresa una URL para comenzar</h2>",
        unsafe_allow_html=True,
    )