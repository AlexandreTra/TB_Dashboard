"""
TB Quant Dashboard — Point d'entrée unique.
Double-cliquez sur lancer.py pour ouvrir le dashboard dans le navigateur.
"""
import os
import sys
import subprocess

# ── Auto-lancement Streamlit ──────────────────────────────────────────────────
if "STREAMLIT_RUN" not in os.environ:
    os.environ["STREAMLIT_RUN"] = "1"
    here = os.path.dirname(os.path.abspath(__file__))
    subprocess.run([sys.executable, "-m", "streamlit", "run",
                    os.path.join(here, "Accueil.py")])
    sys.exit()

import streamlit as st

# ══════════════════════════════════════════════════════════════════════════════
# Navigation centrale — st.navigation() avec sections
# ══════════════════════════════════════════════════════════════════════════════
pg = st.navigation(
    {
        "": [
            st.Page("pages/accueil.py", title="Accueil", icon="🏠", default=True),
        ],
        "📈 Résultats": [
            st.Page("pages/vue_globale.py",     title="Vue Globale",     icon="📊"),
            st.Page("pages/analyse_croisee.py", title="Analyse Croisée", icon="🔀"),
            st.Page("pages/benchmarks.py",      title="Benchmarks",      icon="🏁"),
        ],
        "🌍 Contexte de Marché": [
            st.Page("pages/regime_marche.py",   title="Régime de Marché",icon="🌊"),
            st.Page("pages/profil_actifs.py",   title="Profil des Actifs",icon="🧬"),
        ],
        "🔍 Analyse Avancée": [
            st.Page("pages/sensibilite.py",     title="Sensibilité",      icon="🎚️"),
            st.Page("pages/journaux.py",        title="Journaux de Trades",icon="📋"),
            st.Page("pages/hypotheses.py",      title="Hypothèses",       icon="🧪"),
        ],
        "📝 Outils": [
            st.Page("pages/export.py",          title="Narrative & Export",icon="📄"),
            st.Page("pages/mt5_lancer.py",      title="Lancer MT5",      icon="⚙️"),
        ],
    }
)
pg.run()
