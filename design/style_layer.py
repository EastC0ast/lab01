# Оформление отчёта. Расчётные ячейки ниже оставлены без изменений.
import functools as _design_functools
import textwrap as _design_textwrap
import matplotlib as _design_mpl
import matplotlib.pyplot as _design_plt
import seaborn as _design_sns
import pandas as _design_pd
from IPython.display import display as _design_display, HTML as _design_HTML
from matplotlib.collections import PathCollection as _DesignScatter, PolyCollection as _DesignFill

_DESIGN_CSS = '\n:root{--lab-ink:#243447;--lab-blue:#245B78;--lab-muted:#667789;--lab-line:#D9E2EA;--lab-paper:#fff;--lab-tint:#F4F7FA}\n.lab-title{border-top:4px solid #245B78;border-bottom:1px solid #D9E2EA;padding:28px 0 22px;margin:12px 0 20px;color:#243447}\n.lab-title .kicker{font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:#667789}\n.lab-title h1{font-size:32px!important;line-height:1.2!important;font-weight:650!important;border:0!important;margin:15px 0 8px!important;color:#243447!important}\n.lab-title .subtitle{font-size:19px;line-height:1.45;margin:0 0 20px;color:#42576A}\n.lab-title .authors{font-size:14px;line-height:1.8;color:#556575}\n.lab-nav{border-top:1px solid #D9E2EA;border-bottom:1px solid #D9E2EA;padding:10px 0;margin:18px 0 24px;font-size:13px;display:flex;flex-wrap:wrap;gap:10px 24px}\n.lab-nav a,.lab-links a{color:#245B78;text-decoration:none!important}\n.lab-nav a:hover,.lab-links a:hover{text-decoration:underline!important}\n.lab-links{font-size:13px;line-height:1.8;color:#667789;margin:8px 0 16px}\n.lab-caption{font-size:13px;line-height:1.6;color:#5C6E7E;margin:10px 0 22px}\n.lab-anchor{scroll-margin-top:80px}\n.jp-RenderedHTMLCommon h1,.jp-RenderedHTMLCommon h2,.jp-RenderedHTMLCommon h3,.jp-RenderedHTMLCommon h4{color:#243447;line-height:1.4}\n.jp-RenderedHTMLCommon h2{border-top:1px solid #D9E2EA;padding-top:22px;margin-top:30px}\n.jp-RenderedHTMLCommon p,.jp-RenderedMarkdown p{line-height:1.75}\n.jp-RenderedHTMLCommon table:not(.dataframe){border-collapse:collapse;max-width:100%;width:100%;font-size:13px;margin:16px 0}\n.jp-RenderedHTMLCommon table th{background:#F0F5F8;color:#243447;text-align:left;border-bottom:2px solid #BCCBD7;padding:10px 12px}\n.jp-RenderedHTMLCommon table td{border-bottom:1px solid #E1E7ED;padding:9px 12px;vertical-align:top}\n.lab-table-wrap{overflow-x:auto;padding:6px 0 16px}\n.lab-table{border-collapse:collapse!important;width:100%!important;font-size:13px!important;color:#243447!important}\n.lab-table th{background:#F0F5F8!important;border:0!important;border-bottom:2px solid #BCCBD7!important;padding:10px 12px!important;text-align:right!important;white-space:normal!important}\n.lab-table td{border:0!important;border-bottom:1px solid #E1E7ED!important;padding:9px 12px!important;text-align:right!important;font-variant-numeric:tabular-nums!important}\n.lab-table tbody th{background:#fff!important;text-align:left!important;white-space:normal!important;border-bottom:1px solid #E1E7ED!important;font-weight:500!important}\n.lab-table tbody tr:nth-child(even) td,.lab-table tbody tr:nth-child(even) th{background:#F8FAFC!important}\n.lab-table thead th:first-child{text-align:left!important}\n.jp-RenderedImage img{max-width:100%;height:auto}\n.jp-OutputArea-output pre{font-size:13px;line-height:1.65}\n@media(max-width:640px){.lab-title h1{font-size:26px!important}.lab-title .subtitle{font-size:17px}.lab-nav{gap:7px 15px}}\n'
_design_display(_design_HTML("<style>" + _DESIGN_CSS + "</style>"))
_design_palette = ["#245B78", "#B87532", "#697A8C", "#477D73"]
_design_mpl.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 10.5,
    "axes.titlesize": 13, "axes.titleweight": "semibold",
    "axes.labelsize": 10.5, "axes.labelcolor": "#243447",
    "text.color": "#243447", "xtick.color": "#5C6E7E", "ytick.color": "#5C6E7E",
    "axes.edgecolor": "#C7D3DD", "axes.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.prop_cycle": _design_mpl.cycler(color=_design_palette),
    "grid.color": "#DEE6ED", "grid.linewidth": 0.6,
    "figure.facecolor": "white", "axes.facecolor": "white",
    "savefig.facecolor": "white", "figure.dpi": 120, "savefig.dpi": 140,
    "legend.frameon": False, "legend.fontsize": 9.5,
    "axes.formatter.useoffset": False, "axes.formatter.limits": (-4, 7),
})
try:
    get_ipython().run_line_magic("config", "InlineBackend.figure_format = 'png'")
except (NameError, AttributeError):
    pass

# Явный цвет устраняет несовместимость histplot с некоторыми версиями Matplotlib.
# Данные, интервалы bins, KDE и параметры статистики не меняются.
_design_histplot_original = getattr(_design_sns.histplot, "_design_original", _design_sns.histplot)
@_design_functools.wraps(_design_histplot_original)
def _design_histplot(*args, **kwargs):
    if kwargs.get("hue") is None:
        kwargs.setdefault("color", _design_palette[0])
    return _design_histplot_original(*args, **kwargs)
_design_histplot._design_original = _design_histplot_original
_design_sns.histplot = _design_histplot

# Единый вид таблиц; исходные числовые значения DataFrame сохраняются.
_design_table_original = getattr(_design_pd.DataFrame._repr_html_, "_design_original", _design_pd.DataFrame._repr_html_)
def _design_table_repr(self):
    result = _design_table_original(self)
    if result is None:
        return None
    result = result.replace('class="dataframe"', 'class="dataframe lab-table"')
    return '<style>' + _DESIGN_CSS + '</style><div class="lab-table-wrap">' + result + '</div>'
_design_table_repr._design_original = _design_table_original
_design_pd.DataFrame._repr_html_ = _design_table_repr

# Меняются только визуальные свойства, а не данные или границы шкал.
_design_show_original = getattr(_design_plt.show, "_design_original", _design_plt.show)
_design_figure_number = 0

def _design_style_figure(figure):
    figure.set_size_inches(9.2, 4.8, forward=True)
    for axis in figure.axes:
        if axis.get_label() == "<colorbar>":
            axis.tick_params(labelsize=9)
            continue
        _is_heatmap = any(isinstance(v, _design_mpl.collections.QuadMesh) for v in axis.collections)
        _limits = (axis.get_xlim(), axis.get_ylim())
        _title = axis.get_title()
        axis.set_title("\n".join(_design_textwrap.wrap(_title, width=76)), loc="left", pad=18)
        axis.set_title("", loc="center")
        axis.set_axisbelow(True)
        if _is_heatmap:
            _heat_cmap = _design_mpl.colors.LinearSegmentedColormap.from_list(
                "lab-correlation", ["#245B78", "#F6F8FA", "#B87532"])
            for collection in axis.collections:
                if isinstance(collection, _design_mpl.collections.QuadMesh):
                    collection.set_cmap(_heat_cmap)
        if not _is_heatmap:
            axis.grid(False)
            axis.yaxis.grid(True, color="#DEE6ED", linewidth=0.6, alpha=0.9)
            for side in ["top", "right"]:
                axis.spines[side].set_visible(False)
            for side in ["bottom", "left"]:
                axis.spines[side].set_color("#C7D3DD")
            _line_index = 0
            for line in axis.lines:
                _label = line.get_label()
                _colour = _design_palette[_line_index % len(_design_palette)]
                if any(isinstance(c, _DesignScatter) for c in axis.collections):
                    _colour = _design_palette[1]
                if _label == "Среднее":
                    _colour = _design_palette[1]
                if _label == "Среднее выборки":
                    _colour = _design_palette[0]
                if _label == "lognormal":
                    _colour = _design_palette[1]
                    line.set_linestyle("--")
                line.set_color(_colour)
                line.set_linewidth(1.8)
                _line_index += 1
            for patch in axis.patches:
                if isinstance(patch, _design_mpl.patches.Rectangle):
                    _comparison = any(l.get_label() == "skew-normal" for l in axis.lines)
                    patch.set_facecolor("#C8D5DE" if _comparison else _design_palette[0])
                    patch.set_edgecolor("white")
                    patch.set_linewidth(0.6)
                    patch.set_alpha(0.80)
            for collection in axis.collections:
                if isinstance(collection, _DesignScatter):
                    collection.set_facecolor(_design_palette[0])
                    collection.set_edgecolor("none")
                elif isinstance(collection, _DesignFill):
                    collection.set_facecolor(_design_palette[1])
            if axis.get_legend() is not None:
                axis.legend(frameon=False, fontsize=9.5, loc="best")
        axis.tick_params(labelsize=9.5, length=3.0)
        axis.set_xlim(_limits[0]); axis.set_ylim(_limits[1])
    figure.tight_layout(pad=1.8)

@_design_functools.wraps(_design_show_original)
def _design_show(*args, **kwargs):
    global _design_figure_number
    _figures = [_design_plt.figure(i) for i in _design_plt.get_fignums()]
    for figure in _figures:
        _design_style_figure(figure)
        _design_figure_number += 1
        figure.text(0.99, 0.008, f"Рисунок {_design_figure_number:02d}", ha="right", va="bottom", fontsize=8, color="#7A8996")
    return _design_show_original(*args, **kwargs)
_design_show._design_original = _design_show_original
_design_plt.show = _design_show

