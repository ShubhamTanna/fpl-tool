"""Shared look: colours, the Plotly template, styled tables, club chips and the pitch view."""
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

from fpl.colours import club_colours

BG, PANEL, GRID = "#0B0F14", "#151B23", "#222B36"
TEXT, MUTED = "#E6EDF3", "#9AA7B4"
ACCENT, GOOD, BAD, WARN = "#22D3EE", "#2ECC71", "#FF4D4F", "#F5A524"
MONO = "JetBrains Mono, ui-monospace, Menlo, monospace"
SANS = "Roboto, system-ui, sans-serif"
POS_COLOUR = {"GKP": "#F5A524", "DEF": "#4C9AFF", "MID": "#2ECC71", "FWD": "#FF6B6B"}
# xP parts as charted: the three small parts are grouped as "Other"
PART_GROUPS = {"Appearance": ["xp_app"], "Goals": ["xp_goals"], "Assists": ["xp_assists"],
               "Clean sheet": ["xp_cs"], "Def. contribution": ["xp_dc"], "Bonus": ["xp_bonus"],
               "Other": ["xp_conceded", "xp_saves", "xp_cards"]}
PART_COLOUR = {"Appearance": "#5B6B7D", "Goals": "#22D3EE", "Assists": "#A78BFA", "Clean sheet": "#2ECC71",
               "Def. contribution": "#F5A524", "Bonus": "#F472B6", "Other": "#FF4D4F"}

pio.templates["fpl"] = go.layout.Template(layout=dict(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(family=SANS, color=TEXT, size=13),
    colorway=[ACCENT, "#A78BFA", GOOD, WARN, "#F472B6", BAD, "#4C9AFF", MUTED],
    xaxis=dict(automargin=True, gridcolor=GRID, zerolinecolor="#3A4654", linecolor=GRID, tickfont=dict(family=MONO, size=12),
               title=dict(font=dict(color=MUTED, size=12))),
    yaxis=dict(automargin=True, gridcolor=GRID, zerolinecolor="#3A4654", linecolor=GRID, tickfont=dict(family=MONO, size=12),
               title=dict(font=dict(color=MUTED, size=12))),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=1, xanchor="right", font=dict(size=12), bgcolor="rgba(0,0,0,0)"),
    margin=dict(l=10, r=10, t=56, b=10), hoverlabel=dict(bgcolor=PANEL, bordercolor=GRID, font=dict(family=MONO, color=TEXT)),
    title=dict(font=dict(size=14, color=TEXT), x=0, xanchor="left", y=0.98, yanchor="top"), bargap=0.25))
pio.templates.default = "fpl"


def chart(fig: go.Figure, caption: str, height: int = 360, key: str | None = None, select: bool = False):
    """Draw a figure in the shared style with its one-line 'what to look for' caption."""
    fig.update_layout(height=height)
    if select:
        fig.update_layout(clickmode="event+select", dragmode=False)   # a plain click selects the point
    out = st.plotly_chart(fig, theme=None, key=key, config={"displayModeBar": False},
                          **({"on_select": "rerun", "selection_mode": "points"} if select else {}))
    st.caption(caption)
    return out


# ---------------------------------------------------------------- clubs
def line(team: str) -> str:
    """Chart colour for a club (visible on the dark background)."""
    c = club_colours()
    return c.line[team] if team in c.index else MUTED


def fill(team: str) -> tuple[str, str, str]:
    """(fill, outline, text colour) for a club's chip or pitch card."""
    c = club_colours()
    if team not in c.index:
        return PANEL, MUTED, TEXT
    r = c.loc[team]
    return r.fill, r.outline or r.fill, r.ink


def parts_frame(d: pd.DataFrame) -> pd.DataFrame:
    """Collapse the nine xp_ columns into the seven charted groups."""
    return pd.DataFrame({g: d[cols].sum(axis=1) for g, cols in PART_GROUPS.items()}, index=d.index)


def stacked_parts(parts: pd.DataFrame, labels: list[str], horizontal: bool = True, title: str = "") -> go.Figure:
    """Stacked bars of xP by part. `parts` has one row per bar and the PART_GROUPS columns."""
    fig = go.Figure()
    for g in PART_GROUPS:
        v = parts[g].round(2).tolist()
        kw = dict(x=v, y=labels, orientation="h") if horizontal else dict(x=labels, y=v)
        fig.add_bar(name=g, marker_color=PART_COLOUR[g], hovertemplate=f"{g}: %{{{'x' if horizontal else 'y'}:.2f}}<extra></extra>", **kw)
    fig.update_layout(barmode="relative", title=title)
    if horizontal:
        fig.update_yaxes(autorange="reversed", tickfont=dict(family=SANS))
        fig.update_xaxes(title_text="xP")
    else:
        fig.update_yaxes(title_text="xP")
        fig.update_xaxes(tickfont=dict(family=SANS))
    return fig


# ---------------------------------------------------------------- tables
DIVERGING = ("change", "minus", "- mine", "running", "swing", "error", "rise", "gain", "diff")
NO_FORMAT = {"GW", "Id", "From GW", "To GW"}
HEAT_DEFAULT = ["Appearance", "Goals", "Assists", "Clean sheet", "Conceded", "Saves", "Def. contribution", "Bonus",
                "Cards", "Top 1k %", "Owned %", "xP per m", "Chance of starting", "xMins", "Pts", "Pts per match"]


def _rgba(hex_colour: str, alpha: float) -> str:
    h = hex_colour.lstrip("#")
    return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{alpha:.2f})"


def _is_bar(col: str) -> bool:
    return col != "xP per m" and (col == "xP" or col.startswith("xP ") or col.endswith(" xP"))


def style(df: pd.DataFrame, decimals: int = 2, heat: list[str] | None = None):
    """(Styler, column_config) for st.dataframe: club chips, position tags, colour scales on the
    key numbers, in-cell bars for xP, right-aligned numbers with consistent decimals."""
    df = df.reset_index(drop=True)
    num = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c])]
    floats = [c for c in num if pd.api.types.is_float_dtype(df[c]) and c not in NO_FORMAT]
    bars = [c for c in num if _is_bar(c) and df[c].min() >= 0]
    div = [c for c in num if any(k in c.lower() for k in DIVERGING)]
    seq = [c for c in num if c in set(HEAT_DEFAULT + (heat or [])) and c not in div and c not in bars]
    s = df.style.format({c: ("{:.1f}" if c == "Price" else f"{{:.{decimals}f}}") for c in floats}, na_rep="")

    def seq_css(col: pd.Series):
        lo, hi = col.min(), col.max()
        if not hi > lo:
            return [""] * len(col)
        return ["" if pd.isna(v) else f"background-color: {_rgba(ACCENT, 0.42 * (v - lo) / (hi - lo))}" for v in col]

    def div_css(col: pd.Series):
        m = col.abs().max()
        if not m > 0:
            return [""] * len(col)
        return ["" if pd.isna(v) or v == 0 else f"background-color: {_rgba(GOOD if v > 0 else BAD, 0.45 * abs(v) / m)}"
                for v in col]

    if seq:
        s = s.apply(seq_css, subset=seq)
    if div:
        s = s.apply(div_css, subset=div)
    clubs = club_colours()
    for col in [c for c in df.columns if c.lower().endswith("club")]:
        s = s.map(lambda t: (f"background-color: {clubs.line[t]}; color: {clubs.chip_ink[t]}; font-weight: 700"
                             if t in clubs.index else ""), subset=[col])
    if "Pos" in df.columns:
        s = s.map(lambda p: f"color: {POS_COLOUR.get(p, TEXT)}; font-weight: 700", subset=["Pos"])
    cfg = {c: st.column_config.ProgressColumn(c, format=f"%.{decimals}f", min_value=0,
                                              max_value=float(df[c].max()) or 1.0, color=ACCENT) for c in bars}
    for col in df.columns:
        if col == "Pos" or col.lower().endswith("club"):
            cfg[col] = st.column_config.TextColumn(col, width="small")
    return s, cfg


# ---------------------------------------------------------------- pitch
ROW_Y = {"GKP": 9, "DEF": 33, "MID": 57, "FWD": 81}
PITCH, PITCH_LINE = "#0F2A20", "#2C6B4F"


def pitch(cards: pd.DataFrame, title: str = "") -> go.Figure:
    """A pitch with the XI in formation and the bench in a row below.

    `cards`: one row per squad player with columns name, team, pos, opp, xp, slot ("XI" or
    "B1".."B4"), role ("C", "V" or ""), boosted (bool), flag (injury text or "").
    """
    fig = go.Figure()
    shapes = [dict(type="rect", x0=0, y0=0, x1=100, y1=100, fillcolor=PITCH, line=dict(color=PITCH_LINE, width=2)),
              dict(type="line", x0=0, y0=50, x1=100, y1=50, line=dict(color=PITCH_LINE, width=2)),
              dict(type="circle", x0=40, y0=42, x1=60, y1=58, line=dict(color=PITCH_LINE, width=2)),
              dict(type="rect", x0=25, y0=0, x1=75, y1=15, line=dict(color=PITCH_LINE, width=2)),
              dict(type="rect", x0=25, y0=85, x1=75, y1=100, line=dict(color=PITCH_LINE, width=2)),
              dict(type="rect", x0=0, y0=-24, x1=100, y1=-4, fillcolor=PANEL, line=dict(color=GRID, width=1))]
    spots = []
    xi = cards[cards.slot == "XI"]
    for pos, y in ROW_Y.items():
        row = xi[xi.pos == pos]
        spots += [(r, (k + 1) * 100 / (len(row) + 1), y) for k, (_, r) in enumerate(row.iterrows())]
    bench = cards[cards.slot != "XI"].sort_values("slot")
    spots += [(r, (k + 1) * 100 / (len(bench) + 1), -14) for k, (_, r) in enumerate(bench.iterrows())]
    for r, x, y in spots:
        bg, edge, ink = fill(r.team)
        marks = "".join([f" ({r.role})" if r.role else "", " [boost]" if r.boosted else ""])
        lines = [f"<b>{r['name']}{marks}</b>", f"{r.team} v {r.opp}", f"<b>{r.xp:.1f}</b>"
                 + (f"  {r.flag}" if r.flag else "")]
        fig.add_annotation(x=x, y=y, text="<br>".join(lines), showarrow=False, bgcolor=bg, font=dict(color=ink, size=11, family=SANS),
                           bordercolor=WARN if r.flag else (ACCENT if r.role == "C" else edge),
                           borderwidth=3 if (r.flag or r.role == "C") else 1.5, borderpad=4, width=104, opacity=1)
    fig.add_annotation(x=1, y=-6, text="BENCH", showarrow=False, xanchor="left", font=dict(color=MUTED, size=10, family=MONO))
    fig.update_layout(shapes=shapes, title=title, margin=dict(l=0, r=0, t=30 if title else 5, b=0),
                      xaxis=dict(range=[-1, 101], visible=False, fixedrange=True),
                      yaxis=dict(range=[-26, 102], visible=False, fixedrange=True))
    return fig
