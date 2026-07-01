"""
Composants graphiques Plotly réutilisables — thème sombre unifié.
Toutes les fonctions retournent un objet go.Figure prêt pour st.plotly_chart().
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from core.constants import PALETTE, PLOTLY_DARK, REGIME_COLOR, THEME, TYPE_COLOR


# ─────────────────────────────────────────────────────────────────────────────
# Helpers internes
# ─────────────────────────────────────────────────────────────────────────────

def _apply_dark(fig: go.Figure, title: str = "", **kwargs) -> go.Figure:
    """Applique le thème sombre et le titre à une figure."""
    layout = {**PLOTLY_DARK, **kwargs}
    if title:
        layout["title"] = title
    fig.update_layout(**layout)
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# Vue Globale
# ─────────────────────────────────────────────────────────────────────────────

def fig_ghpr_scatter(df: pd.DataFrame) -> go.Figure:
    """
    Scatter GHPR vs Equity DD% — un point par pass, coloré par type de stratégie.
    La ligne rouge horizontale à GHPR=1.0 délimite la rentabilité en capitalisation.
    """
    fig = go.Figure()
    if "Equity DD %" not in df.columns:
        return _apply_dark(fig, "GHPR vs Drawdown (colonne 'Equity DD %' absente)")

    for stype, grp in df.groupby("Type"):
        fig.add_trace(go.Scatter(
            x=grp["Equity DD %"],
            y=grp["GHPR"],
            mode="markers",
            name=stype,
            marker=dict(
                color=TYPE_COLOR.get(stype, "#aaa"),
                size=6, opacity=0.7,
                line=dict(color="white", width=0.4),
            ),
            text=grp["Stratégie"],
            hovertemplate=(
                "<b>%{text}</b><br>"
                "DD: %{x:.1f}%<br>"
                "GHPR: %{y:.5f}<extra></extra>"
            ),
        ))

    fig.add_hline(
        y=1.0, line_dash="dash", line_color=THEME["danger"],
        annotation_text="Seuil rentabilité (GHPR=1)",
        annotation_position="bottom right",
        annotation_font=dict(color=THEME["danger"]),
    )
    return _apply_dark(
        fig,
        title="Rendement Composé (GHPR) vs Risque (DD %)",
        xaxis_title="Equity Drawdown (%)",
        yaxis_title="GHPR (Geometric HPR)",
    )


def fig_ghpr_boxplot(df: pd.DataFrame) -> go.Figure:
    """Boxplot GHPR par type de stratégie avec affichage de la moyenne (sd)."""
    fig = go.Figure()
    all_vals = []
    for stype, grp in df.groupby("Type"):
        vals = grp["GHPR"].dropna()
        all_vals.extend(vals.tolist())
        fig.add_trace(go.Box(
            y=vals,
            name=stype,
            marker_color=TYPE_COLOR.get(stype, "#aaa"),
            boxmean="sd",
            hovertemplate="%{y:.5f}<extra>" + stype + "</extra>",
        ))
    fig.add_hline(y=1.0, line_dash="dash", line_color=THEME["danger"],
                  annotation_text="GHPR=1")
    # Plage Y dynamique : zoome sur la distribution réelle au lieu d'afficher tout depuis 0
    if all_vals:
        arr    = np.array(all_vals)
        p05    = float(np.percentile(arr, 2))
        p95    = float(np.percentile(arr, 98))
        margin = max((p95 - p05) * 0.3, 0.0005)
        y_bot  = min(p05 - margin, 0.998)
        y_top  = max(p95 + margin, 1.002)
        extra  = dict(yaxis_range=[y_bot, y_top], yaxis_zeroline=False)
    else:
        extra = {}
    return _apply_dark(fig, title="Distribution GHPR par Type de Stratégie",
                       yaxis_title="GHPR", **extra)


def fig_wfe_bar(df_kpi: pd.DataFrame) -> go.Figure:
    """
    Bar chart WFE (%) par stratégie.
    Vert ≥ 80% | Orange 50-80% | Rouge < 50%
    """
    df_s = df_kpi.dropna(subset=["WFE (%)"]).sort_values("WFE (%)", ascending=False)
    if df_s.empty:
        return go.Figure()

    colors = [
        THEME["success"] if v >= 80
        else (THEME["warning"] if v >= 50 else THEME["danger"])
        for v in df_s["WFE (%)"]
    ]
    # Noms de stratégies tronqués pour la lisibilité de l'axe X
    labels = [s[:22] + "…" if len(s) > 22 else s for s in df_s["Stratégie"]]
    fig = go.Figure(go.Bar(
        x=labels,
        y=df_s["WFE (%)"],
        marker_color=colors,
        text=[f"{v:.1f}%" for v in df_s["WFE (%)"]],
        textposition="outside",
        customdata=df_s["Stratégie"],
        hovertemplate="<b>%{customdata}</b><br>WFE: %{y:.1f}%<extra></extra>",
    ))
    fig.add_hline(y=100, line_dash="dot", line_color="#444",
                  annotation_text="WFE=100%", annotation_position="right")
    fig.add_hline(y=50, line_dash="dash", line_color=THEME["warning"],
                  annotation_text="Danger (50%)", annotation_position="right",
                  annotation_font=dict(color=THEME["warning"]))
    # Plage Y dynamique : toujours montrer les seuils 50 et 100, zoomer sur les données
    wfe_max = df_s["WFE (%)"].max()
    wfe_min = df_s["WFE (%)"].min()
    y_top   = max(wfe_max * 1.15, 110)
    y_bot   = max(0, min(wfe_min * 0.85, 40))   # toujours inclure la zone danger
    return _apply_dark(fig, title="Walk-Forward Efficiency par Stratégie",
                       yaxis_title="WFE (%)",
                       yaxis_range=[y_bot, y_top],
                       xaxis_tickangle=-40)


def fig_significance_scatter(df_kpi: pd.DataFrame) -> go.Figure:
    """
    Scatter WFE% vs GHPR, coloré par significativité statistique.
    Visualise les stratégies qui sont à la fois robustes ET statistiquement valides.
    """
    df_s = df_kpi.dropna(subset=["WFE (%)", "GHPR Moyen"])
    if df_s.empty:
        return go.Figure()

    fig = px.scatter(
        df_s,
        x="WFE (%)", y="GHPR Moyen",
        color="Significatif",
        symbol="Type",
        size="Nb Passes",
        text="Symbole",
        color_discrete_map={"✅": THEME["success"], "❌": THEME["danger"]},
        hover_data=["Stratégie", "Survie GHPR>1 (%)", "p-value"],
        template="plotly_dark",
    )
    fig.add_hline(y=1.0, line_dash="dash", line_color=THEME["danger"],
                  annotation_text="GHPR=1 (rentabilité composée)")
    fig.add_vline(x=50, line_dash="dash", line_color=THEME["warning"],
                  annotation_text="WFE critique (50%)")
    fig.update_traces(textposition="top center", marker=dict(line=dict(width=0.5, color="white")))
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(14,17,23,0.6)")
    return _apply_dark(fig, title="Carte de Robustesse : WFE% vs GHPR (taille = nb passes)")


# ─────────────────────────────────────────────────────────────────────────────
# Analyse Croisée
# ─────────────────────────────────────────────────────────────────────────────

def fig_heatmap_cross(pivot: pd.DataFrame, metric: str, title: str) -> go.Figure:
    """
    Heatmap Type de stratégie × Symbole pour une métrique donnée.
    Utilise une échelle RdYlGn (rouge=mauvais, vert=bon).
    """
    if pivot.empty:
        return go.Figure()
    fig = px.imshow(
        pivot,
        text_auto=".2f",
        color_continuous_scale="RdYlGn",
        title=title,
        labels=dict(color=metric),
        template="plotly_dark",
    )
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)")
    return fig


def fig_type_bar(df_kpi: pd.DataFrame, metric: str, title: str) -> go.Figure:
    """Bar chart de la métrique agrégée par type de stratégie."""
    if metric not in df_kpi.columns:
        return go.Figure()
    agg = (
        df_kpi.groupby("Type")[metric]
        .mean().reset_index()
        .sort_values(metric, ascending=False)
    )
    fig = px.bar(
        agg, x="Type", y=metric,
        color="Type", color_discrete_map=TYPE_COLOR,
        text=agg[metric].round(3),
        template="plotly_dark",
    )
    fig.update_traces(textposition="outside", marker_line_width=0)
    fig.update_layout(showlegend=False, paper_bgcolor="rgba(0,0,0,0)")
    # Plage Y dynamique pour rendre les différences inter-types visibles
    vals = agg[metric].dropna()
    if not vals.empty:
        v_min, v_max = vals.min(), vals.max()
        margin = max((v_max - v_min) * 0.5, abs(v_max) * 0.05, 0.001)
        y_bot  = v_min - margin
        y_top  = v_max + margin
        return _apply_dark(fig, title=title, yaxis_title=metric,
                           yaxis_range=[y_bot, y_top])
    return _apply_dark(fig, title=title, yaxis_title=metric)


def fig_radar_symbols(df_kpi: pd.DataFrame, symbols: list[str], metrics: list[str]) -> go.Figure:
    """
    Radar chart (spider) pour comparer plusieurs symboles sur plusieurs métriques.
    """
    fig = go.Figure()
    for i, sym in enumerate(symbols):
        row = df_kpi[df_kpi["Symbole"] == sym][metrics].mean()
        if row.empty:
            continue
        vals = row.values.tolist()
        vals += [vals[0]]  # ferme le polygone
        fig.add_trace(go.Scatterpolar(
            r=vals,
            theta=metrics + [metrics[0]],
            fill="toself",
            name=sym,
            line_color=PALETTE[i % len(PALETTE)],
            opacity=0.7,
        ))
    return _apply_dark(fig, title="Profil comparatif des Symboles",
                       polar=dict(radialaxis=dict(visible=True)))


def fig_perf_map(df_kpi: pd.DataFrame) -> go.Figure:
    """
    Carte de performance : WFE% vs GHPR, taille = nb passes, couleur = type.
    Quadrants pour identifier rapidement les meilleures stratégies.
    """
    df_s = df_kpi.dropna(subset=["WFE (%)", "GHPR Moyen"])
    if df_s.empty:
        return go.Figure()
    fig = px.scatter(
        df_s,
        x="WFE (%)", y="GHPR Moyen",
        color="Type", symbol="Groupe" if "Groupe" in df_s.columns else None,
        size="Nb Passes",
        text="Symbole",
        color_discrete_map=TYPE_COLOR,
        hover_data=["Stratégie", "Survie GHPR>1 (%)", "Significatif"],
        template="plotly_dark",
    )
    fig.add_hline(y=1.0, line_dash="dash", line_color=THEME["danger"],
                  annotation_text="GHPR=1")
    fig.add_vline(x=50, line_dash="dash", line_color=THEME["warning"],
                  annotation_text="WFE=50%")
    fig.update_traces(textposition="top center",
                      marker=dict(line=dict(width=0.5, color="white")))
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(14,17,23,0.6)")
    return _apply_dark(fig, title="Carte Globale de Performance")


# ─────────────────────────────────────────────────────────────────────────────
# Régime de Marché
# ─────────────────────────────────────────────────────────────────────────────

def fig_adx_timeline(df_market: pd.DataFrame, symbol: str) -> go.Figure:
    """
    Timeline de l'ADX mensuel avec zones de régime colorées en fond.
    """
    if df_market.empty or "ADX" not in df_market.columns:
        return go.Figure()

    df = df_market.reset_index()
    date_col = "index" if "index" in df.columns else df.columns[0]
    dates = df[date_col]

    fig = go.Figure()

    # Zones colorées par régime
    regime_col = "#1E2130"
    prev_regime, start_i = None, 0
    for i, (_, row) in enumerate(df.iterrows()):
        regime = row.get("Regime", "Range")
        if regime != prev_regime or i == len(df) - 1:
            if prev_regime is not None:
                end_i = i if regime != prev_regime else i + 1
                fig.add_vrect(
                    x0=dates.iloc[start_i], x1=dates.iloc[min(end_i, len(dates)-1)],
                    fillcolor=REGIME_COLOR.get(prev_regime, "#333"),
                    opacity=0.12, layer="below", line_width=0,
                    annotation_text=prev_regime if (end_i - start_i) > 2 else "",
                    annotation_position="top left",
                    annotation_font=dict(color=REGIME_COLOR.get(prev_regime, "#aaa"), size=9),
                )
            prev_regime, start_i = regime, i

    # Ligne ADX
    fig.add_trace(go.Scatter(
        x=dates, y=df["ADX"],
        mode="lines+markers", name="ADX",
        line=dict(color=THEME["accent"], width=2.5),
        marker=dict(size=4),
        hovertemplate="Date: %{x|%b %Y}<br>ADX: %{y:.1f}<extra></extra>",
    ))
    fig.add_hline(y=25, line_dash="dash", line_color=THEME["warning"],
                  annotation_text="Tendance (25)", annotation_position="right",
                  annotation_font=dict(color=THEME["warning"]))
    fig.add_hline(y=40, line_dash="dash", line_color=THEME["success"],
                  annotation_text="Forte tendance (40)", annotation_position="right",
                  annotation_font=dict(color=THEME["success"]))

    return _apply_dark(fig,
        title=f"Régime de Marché — {symbol} | ADX Mensuel",
        xaxis_title="Date", yaxis_title="ADX",
    )


def fig_hurst_bar(results: dict[str, float]) -> go.Figure:
    """
    Bar chart de l'exposant de Hurst par symbole.
    Vert > 0.55 (Tendanciel) | Jaune ≈ 0.50 (Aléatoire) | Rouge < 0.45 (Mean-revertant)
    """
    if not results:
        return go.Figure()
    symbols = list(results.keys())
    hursts  = list(results.values())
    colors  = [
        THEME["success"] if h > 0.55
        else (THEME["danger"] if h < 0.45 else THEME["warning"])
        for h in hursts
    ]
    fig = go.Figure(go.Bar(
        x=symbols, y=hursts,
        marker_color=colors,
        text=[f"{h:.3f}" for h in hursts],
        textposition="outside",
        hovertemplate="<b>%{x}</b><br>H = %{y:.3f}<extra></extra>",
    ))
    fig.add_hline(y=0.55, line_dash="dash", line_color=THEME["success"],
                  annotation_text="Tendanciel (H>0.55)", annotation_position="right",
                  annotation_font=dict(color=THEME["success"]))
    fig.add_hline(y=0.45, line_dash="dash", line_color=THEME["danger"],
                  annotation_text="Mean-revertant (H<0.45)", annotation_position="right",
                  annotation_font=dict(color=THEME["danger"]))
    fig.add_hline(y=0.50, line_dash="dot", line_color="#555")
    return _apply_dark(fig,
        title="Exposant de Hurst par Actif (Nature intrinsèque du marché)",
        yaxis_title="Exposant de Hurst (H)",
        yaxis_range=[0.2, 0.85],
    )


def fig_regime_performance(df_strat: pd.DataFrame, df_market: pd.DataFrame, symbol: str) -> go.Figure:
    """
    Bar chart groupé : GHPR moyen par type de stratégie × régime de marché dominant.
    Le régime dominant est calculé pour chaque période de test (Date_Start / Date_End) déclarée.
    """
    if df_strat.empty or df_market.empty or "Regime" not in df_market.columns:
        return go.Figure()

    # Normaliser l'index du df marché en colonne de dates
    df_mkt = df_market.reset_index()
    date_col = "index" if "index" in df_mkt.columns else df_mkt.columns[0]
    df_mkt[date_col] = pd.to_datetime(df_mkt[date_col], errors="coerce")

    rows = []
    for _, row in df_strat.iterrows():
        try:
            start = pd.to_datetime(row.get("Date_Start", "2010-01-01"))
            end   = pd.to_datetime(row.get("Date_End",   "2026-01-01"))
            mask  = (df_mkt[date_col] >= start) & (df_mkt[date_col] <= end)
            modes = df_mkt.loc[mask, "Regime"].mode()
            dominant = modes.iloc[0] if not modes.empty else "N/A"
        except Exception:
            dominant = "N/A"
        rows.append({
            "Type":   row.get("Type", "?"),
            "GHPR":   row.get("GHPR", 1.0),
            "Regime": dominant,
        })

    if not rows:
        return go.Figure()

    df_r   = pd.DataFrame(rows)
    df_agg = (
        df_r[df_r["Regime"] != "N/A"]
        .groupby(["Type", "Regime"])["GHPR"]
        .mean()
        .reset_index()
        .rename(columns={"GHPR": "Valeur"})
    )
    if df_agg.empty:
        return go.Figure()

    fig = px.bar(
        df_agg,
        x="Type", y="Valeur", color="Regime",
        barmode="group",
        color_discrete_map=REGIME_COLOR,
        text=df_agg["Valeur"].round(4),
        template="plotly_dark",
    )
    fig.add_hline(y=1.0, line_dash="dash", line_color=THEME["danger"],
                  annotation_text="GHPR=1")
    fig.update_traces(textposition="outside", marker_line_width=0)
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(14,17,23,0.6)")
    return _apply_dark(fig,
        title=f"{symbol} — GHPR Moyen par Type × Régime Dominant de la Période",
        yaxis_title="GHPR Moyen",
    )


def fig_adx_vs_ghpr(df: pd.DataFrame, symbol: str) -> go.Figure:
    """
    Scatter : ADX mensuel vs GHPR des passes forward, coloré par régime.
    Montre si l'ADX au moment du test influence la performance de la stratégie.
    """
    if df.empty or "ADX_periode" not in df.columns or "GHPR" not in df.columns:
        return go.Figure()
    fig = px.scatter(
        df.dropna(subset=["ADX_periode", "GHPR"]),
        x="ADX_periode", y="GHPR",
        color="Regime_periode" if "Regime_periode" in df.columns else None,
        color_discrete_map=REGIME_COLOR,
        trendline="ols",
        template="plotly_dark",
        hover_data=["Stratégie", "Type"] if "Stratégie" in df.columns else [],
    )
    fig.add_hline(y=1.0, line_dash="dash", line_color=THEME["danger"])
    fig.add_vline(x=25, line_dash="dash", line_color=THEME["warning"])
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)")
    return _apply_dark(fig,
        title=f"{symbol} — ADX de la période vs GHPR des passes",
        xaxis_title="ADX Moyen de la Période",
        yaxis_title="GHPR",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Sensibilité Paramétrique
# ─────────────────────────────────────────────────────────────────────────────

def fig_param_sensitivity(df_agg: pd.DataFrame, param_name: str, metric: str) -> go.Figure:
    """
    Bar chart de sensibilité paramétrique : métrique moyenne par tranche de valeur.

    Une courbe plate indique un paramètre robuste.
    Un pic isolé suggère un sur-ajustement (overfitting).
    """
    if df_agg.empty:
        return go.Figure()
    colors = [
        THEME["success"] if v >= (1.0 if metric == "GHPR" else 0)
        else THEME["danger"]
        for v in df_agg["Moyenne"]
    ]
    fig = go.Figure(go.Bar(
        x=df_agg["Tranche_str"],
        y=df_agg["Moyenne"],
        error_y=dict(
            type="data",
            array=df_agg["Ecart-type"].fillna(0),
            visible=True,
            color="#555",
            thickness=1.5,
        ),
        marker_color=colors,
        text=[f"n={int(n)}" for n in df_agg["N"]],
        textposition="outside",
        hovertemplate="Tranche: %{x}<br>Moy: %{y:.4f}<extra></extra>",
    ))
    ref = 1.0 if metric == "GHPR" else 0
    fig.add_hline(y=ref, line_dash="dash", line_color="#555")
    return _apply_dark(fig,
        title=f"Sensibilité de {metric} → {param_name}",
        xaxis_title=param_name,
        yaxis_title=f"{metric} moyen",
        xaxis_tickangle=-40,
    )


def fig_parallel_coords(df: pd.DataFrame, param_cols: list[str], metric: str = "GHPR") -> go.Figure:
    """
    Coordonnées parallèles : chaque ligne est une passe d'optimisation.
    Couleur = valeur du GHPR (rouge=mauvais, vert=bon).
    Permet de voir visuellement quelles combinaisons de paramètres donnent les meilleurs résultats.
    """
    cols = [c for c in param_cols if c in df.columns] + [metric]
    df_p = df[cols].dropna()
    if df_p.empty or len(df_p) < 5:
        return go.Figure()

    dimensions = [
        dict(label=col, values=df_p[col], range=[df_p[col].min(), df_p[col].max()])
        for col in cols
    ]
    fig = go.Figure(go.Parcoords(
        line=dict(
            color=df_p[metric],
            colorscale="Tealrose",
            cmin=df_p[metric].quantile(0.05),
            cmax=df_p[metric].quantile(0.95),
            showscale=True,
            colorbar=dict(title=metric),
        ),
        dimensions=dimensions,
    ))
    return _apply_dark(fig, title=f"Radiographie des Paramètres (coloré par {metric})")


def fig_param_importance(df_imp: pd.DataFrame) -> go.Figure:
    """
    Bar chart horizontal : importance des paramètres (corrélation de Spearman absolue).
    """
    if df_imp.empty:
        return go.Figure()
    df_s = df_imp.copy()
    df_s["Abs"] = df_s["Corrélation (Spearman)"].abs()
    df_s = df_s.sort_values("Abs")
    colors = [
        THEME["success"] if v > 0 else THEME["danger"]
        for v in df_s["Corrélation (Spearman)"]
    ]
    fig = go.Figure(go.Bar(
        x=df_s["Corrélation (Spearman)"],
        y=df_s["Paramètre"],
        orientation="h",
        marker_color=colors,
        text=[f"{v:.3f}" for v in df_s["Corrélation (Spearman)"]],
        textposition="outside",
        hovertemplate="<b>%{y}</b><br>ρ = %{x:.3f}<extra></extra>",
    ))
    fig.add_vline(x=0, line_color="#555")
    return _apply_dark(fig,
        title="Importance des Paramètres (Corrélation de Spearman avec GHPR)",
        xaxis_title="Corrélation de Spearman (ρ)",
        yaxis_title="Paramètre",
    )
