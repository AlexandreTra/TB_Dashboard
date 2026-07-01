"""
Helpers UI réutilisables :
  - st_plotly() : affiche un graphique Plotly + bouton de téléchargement PNG fond blanc
  - st_df()     : affiche un dataframe + bouton de téléchargement CSV
"""
from __future__ import annotations

import copy
import io
from datetime import datetime

import pandas as pd
import streamlit as st

# Layout fond blanc appliqué uniquement à l'export
_WHITE_LAYOUT = dict(
    template="plotly_white",
    paper_bgcolor="white",
    plot_bgcolor="#F7F8FA",
    font=dict(family="Inter, Segoe UI, sans-serif", color="#1A1A2E", size=13),
    legend=dict(bgcolor="white", bordercolor="#CCCCCC", borderwidth=1),
    xaxis=dict(gridcolor="#E5E7EB", linecolor="#9CA3AF"),
    yaxis=dict(gridcolor="#E5E7EB", linecolor="#9CA3AF"),
    hoverlabel=dict(bgcolor="white", font_size=12, bordercolor="#CCCCCC"),
)


def st_plotly(
    fig,
    key: str,
    filename: str | None = None,
    height: int | None = None,
) -> None:
    """
    Render a Plotly figure in dark theme + offer a white-background PNG download.

    Parameters
    ----------
    fig      : plotly Figure
    key      : unique Streamlit key (must be unique within the page)
    filename : base name for the downloaded file (defaults to key)
    height   : explicit height override for the PNG (pixels); None = use fig.layout.height
    """
    # ── Affichage normal (thème sombre) ──────────────────────────────────────
    st.plotly_chart(fig, use_container_width=True, key=key)

    # ── Bouton de téléchargement ──────────────────────────────────────────────
    _fn  = (filename or key).replace("/", "_").replace(" ", "_")
    _h   = height or (fig.layout.height if fig.layout.height else 500)
    _key_dl = f"_dl_{key}"

    fig_w = copy.deepcopy(fig)
    # Appliquer le layout blanc ; conserver le titre et les annotations
    fig_w.update_layout(**_WHITE_LAYOUT)
    if height:
        fig_w.update_layout(height=height)

    # Essai export PNG via kaleido
    try:
        import plotly.io as pio
        img = pio.to_image(fig_w, format="png", width=1_400, height=_h, scale=2)
        st.download_button(
            label="⬇️ PNG",
            data=img,
            file_name=f"{_fn}.png",
            mime="image/png",
            key=_key_dl,
            help="Télécharger en PNG (fond blanc, haute résolution)",
        )
    except Exception:
        # Repli : HTML interactif fond blanc (ne nécessite pas kaleido)
        html = fig_w.to_html(include_plotlyjs="cdn", full_html=True)
        st.download_button(
            label="⬇️ HTML",
            data=html.encode("utf-8"),
            file_name=f"{_fn}.html",
            mime="text/html",
            key=_key_dl,
            help="Télécharger en HTML interactif (fond blanc)",
        )


def st_df(
    df: pd.DataFrame,
    key: str,
    filename: str | None = None,
    label: str = "⬇️ CSV",
    **dataframe_kwargs,
) -> None:
    """
    Display a Streamlit dataframe + an explicit CSV download button.

    Parameters
    ----------
    df               : DataFrame to display
    key              : unique key (used for the download button)
    filename         : CSV filename base (defaults to key)
    label            : button label
    **dataframe_kwargs : forwarded to st.dataframe()
    """
    st.dataframe(df, use_container_width=True, **dataframe_kwargs)

    _fn   = (filename or key).replace("/", "_").replace(" ", "_")
    stamp = datetime.now().strftime("%Y%m%d")
    csv   = df.to_csv(index=False).encode("utf-8-sig")

    st.download_button(
        label=label,
        data=csv,
        file_name=f"{_fn}_{stamp}.csv",
        mime="text/csv",
        key=f"_dl_{key}",
        help="Télécharger le tableau en CSV",
    )
