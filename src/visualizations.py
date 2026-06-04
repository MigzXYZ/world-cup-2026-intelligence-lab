"""Reusable Plotly chart builders."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def probability_bar(labels: list[str], values: list[float], title: str = "Probability"):
    df = pd.DataFrame({"Outcome": labels, "Probability": values})
    fig = px.bar(df, x="Outcome", y="Probability", text=df["Probability"].map(lambda x: f"{x*100:.1f}%"), title=title)
    fig.update_layout(yaxis_tickformat=".0%", yaxis_range=[0, max(1.0, max(values) * 1.15)], height=430)
    return fig


def horizontal_bar(df: pd.DataFrame, x: str, y: str, title: str, color: str | None = None):
    fig = px.bar(df, x=x, y=y, orientation="h", color=color, text=x, title=title)
    fig.update_layout(yaxis={"categoryorder": "total ascending"}, height=460)
    return fig


def probability_heatmap(df: pd.DataFrame, x: str, y: str, z: str, title: str):
    fig = px.density_heatmap(df, x=x, y=y, z=z, histfunc="avg", text_auto=".1%", title=title)
    fig.update_layout(height=500)
    return fig


def gauge(value: float, title: str):
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=float(value),
        title={"text": title},
        gauge={"axis": {"range": [0, 100]}},
    ))
    fig.update_layout(height=300)
    return fig
