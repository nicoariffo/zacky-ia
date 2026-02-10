"""Streamlit application entry point."""

import streamlit as st

st.set_page_config(
    page_title="Zacky IA",
    page_icon="🤖",
    layout="wide",
)

st.title("🤖 Zacky IA")
st.subheader("Asistente IA para Soporte")

st.markdown("""
### Bienvenido

Esta aplicación te ayuda a gestionar tickets de soporte con asistencia de IA.

**Funcionalidades:**
- 📋 Ver tickets con sugerencias de respuesta
- 📊 Dashboard de métricas
- 🏷️ Gestión de intents

Usa el menú lateral para navegar entre las diferentes secciones.
""")

# Placeholder for stats
col1, col2, col3 = st.columns(3)

with col1:
    st.metric("Tickets Procesados", "0", help="Total de tickets procesados")

with col2:
    st.metric("Tasa de Aceptación", "0%", help="Porcentaje de sugerencias aceptadas")

with col3:
    st.metric("Intents Activos", "0", help="Número de intents configurados")
