from contextlib import contextmanager
from copy import deepcopy
from functools import reduce
from IPython.core.getipython import get_ipython
import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import PIL
import plotnine
from plotnine import aes, ggplot, geom_bar, geom_density, geom_histogram, geom_line, geom_point, theme
from plotnine.stats.binning import freedman_diaconis_bins

import potoo.mpl_backend_xee  # Used by ~/.matplotlib/matplotlibrc
from potoo.util import or_else, puts, singleton


ipy = get_ipython()  # None if not in ipython


def get_figsize_named(size_name):
    # Determined empirically, and fine-tuned for atom splits with status-bar + tab-bar
    mpl_aspect = 2/3  # Tuned using plotnine, but works the same for mpl/sns
    R_aspect = 7/12  # Not sure why this is different than mpl, but it is
    figsizes_mpl = dict(
        # Some common sizes that are useful; add more as necessary
        inline     = dict(width=10, aspect_ratio=mpl_aspect * 1/2),
        half       = dict(width=10, aspect_ratio=mpl_aspect * 2),
        full       = dict(width=20, aspect_ratio=mpl_aspect * 1),
        half_dense = dict(width=20, aspect_ratio=mpl_aspect * 2),
        full_dense = dict(width=40, aspect_ratio=mpl_aspect * 1),
    )
    figsizes = dict(
        mpl=figsizes_mpl,
        R={
            k: dict(width=v['width'], height=v['width'] * v['aspect_ratio'] / mpl_aspect * R_aspect)
            for k, v in figsizes_mpl.items()
        },
    )
    if size_name not in figsizes['mpl']:
        raise ValueError(f'Unknown figsize name[{size_name}]')
    return {k: figsizes[k][size_name] for k in figsizes.keys()}


def plot_set_defaults():
    figsize()
    plot_set_default_mpl_rcParams()
    plot_set_jupyter_defaults()
    # plot_set_R_defaults()  # TODO Re-enable after reinstalling my patch of rpy2


def figure_format(figure_format: str = None):
    """
    Set figure_format: one of 'svg', 'retina', 'png'
    """
    if figure_format:
        assert figure_format in ['svg', 'retina', 'png'], f'Unknown figure_format[{figure_format}]'
        ipy.run_line_magic('config', f"InlineBackend.figure_format = {figure_format!r}")
    return or_else(None, lambda: ipy.run_line_magic('config', 'InlineBackend.figure_format'))


# Only sets mpl figsize
def figsize(*args, **kwargs):
    """
    Set theme_figsize(...) as global plotnine.options + mpl.rcParams:
    - https://plotnine.readthedocs.io/en/stable/generated/plotnine.themes.theme.html
    - http://matplotlib.org/users/customizing.html
    """
    # Passthru to theme_figsize
    t = theme_figsize(*args, **kwargs)
    [width, height] = figure_size = t.themeables['figure_size'].properties['value']
    aspect_ratio = t.themeables['aspect_ratio'].properties['value']
    dpi = t.themeables['dpi'].properties['value']
    # Set mpl figsize
    mpl.rcParams.update(t.rcParams)
    # Set plotnine figsize
    plotnine.options.figure_size = figure_size
    plotnine.options.aspect_ratio = aspect_ratio
    plotnine.options.dpi = dpi  # (Ignored for figure_format='svg')
    # Set %R figsize (via %rdefaults)
    # Rdefaults = plot_set_R_figsize(width, height)  # TODO Re-enable after reinstalling my patch of rpy2
    Rdefaults = None  # XXX
    # Show feedback to user
    return dict(
        width=width,
        height=height,
        aspect_ratio=aspect_ratio,
        dpi=dpi,
        figure_format=figure_format(),
        Rdefaults=Rdefaults,
    )


# Sets mpl figsize
def theme_figsize(name='inline', width=None, aspect_ratio=None, dpi=72):
    """
    plotnine theme with defaults for figure_size width + aspect_ratio (which overrides figure_size height if defined):
    - https://plotnine.readthedocs.io/en/stable/generated/plotnine.themes.theme.html#aspect_ratio-and-figure_size
    """
    if name and not (width and aspect_ratio):
        size = get_figsize_named(name)['mpl']
        width = width or size['width']
        aspect_ratio = aspect_ratio or size['aspect_ratio']
    height = width * aspect_ratio
    return theme(
        # height is ignored by plotnine when aspect_ratio is given, but supply anyway so that we can set theme.rcParams
        # into mpl.rcParams since the latter has no notion of aspect_ratio [TODO Submit PR to fix]
        figure_size=[width, height],
        aspect_ratio=aspect_ratio,
        dpi=dpi,
    )


# ~/.matploblib/matploblibrc isn't read by ipykernel, so we call this from ~/.pythonrc which is
#   - TODO What's the right way to init mpl.rcParams?
def plot_set_default_mpl_rcParams():
    mpl.rcParams['figure.facecolor'] = 'white'  # Match savefig.facecolor
    mpl.rcParams['image.interpolation'] = 'nearest'  # Don't interpolate, show square pixels
    # TODO Sync more carefully with ~/.matploblib/matploblibrc?


def plot_set_jupyter_defaults():
    if ipy:
        # 'svg' is pretty, 'retina' is the prettier version of 'png', and 'png' is ugly (on retina macs)
        figure_format('svg')


#
# plotnine
#


def ggbar(*args, **kwargs):
    kwargs.setdefault('geom', geom_bar)
    return gg(*args, **kwargs)


def gghist(*args, **kwargs):
    (df, mapping, geom, kwargs) = _gg_resolve_args(*args, **kwargs)
    kwargs.setdefault('bins', freedman_diaconis_bins(df[mapping['x']]))  # Like stat_bin
    kwargs.setdefault('geom', geom_histogram)
    return gg(*args, **kwargs)


def ggdens(*args, **kwargs):
    kwargs.setdefault('geom', geom_density)
    return gg(*args, **kwargs)


def ggpoint(*args, **kwargs):
    kwargs.setdefault('geom', geom_point)
    return gg(*args, **kwargs)


def ggline(*args, **kwargs):
    kwargs.setdefault('geom', geom_line)
    return gg(*args, **kwargs)


def gg(*args, **kwargs):
    (df, mapping, geom, kwargs) = _gg_resolve_args(*args, **kwargs)
    return ggplot(df, mapping) + geom(**kwargs)


def _gg_resolve_args(df_or_series, x: str = None, y: str = None, mapping=None, geom=None, **kwargs):
    mapping = mapping or aes()
    if isinstance(df_or_series, pd.Series):
        df = pd.DataFrame({'x': df_or_series})
        x = 'x'
    elif isinstance(df_or_series, pd.DataFrame):
        df = df_or_series
    if x: mapping.setdefault('x', x)
    if y: mapping.setdefault('y', y)
    return (df, mapping, geom, kwargs)


def graph(f, x: np.array) -> pd.DataFrame:
    return pd.DataFrame({
        'x': x,
        'y': f(x),
    })


#
# %R
#


def load_ext_rpy2_ipython():
    if not ipy:
        return False
    else:
        try:
            ipy.run_cell(
                '%%capture\n'
                '%load_ext rpy2.ipython'
            )
        except:
            return False
        else:
            return True


def plot_set_R_defaults():
    if load_ext_rpy2_ipython():
        ipy.run_line_magic('Rdevice', 'svg')  # 'svg' | 'png'


def plot_set_R_figsize(width, height):
    """
    Set figsize for %R/%%R magics
    """
    if load_ext_rpy2_ipython():
        extend_magic_R_with_defaults.default_line = R_line_width_height(width, height)
        return extend_magic_R_with_defaults.default_line


@singleton
class extend_magic_R_with_defaults:
    """
    Wrapper around %%R/%R that allows defaults
    """

    def __init__(self):
        self.default_line = None

    def __call__(self):
        _R = ipy.magics_manager.magics['cell']['R']
        def R(line, cell=None):
            if self.default_line:
                line = f'{self.default_line} {line}'
            return _R(line, cell)
        ipy.register_magic_function(R, 'line_cell', 'R')


# TODO Parse short/long opts generically to support all kwargs understood by theme_figsize, like figsize does
def extend_magic_R_with_sizename():
    """
    Wrapper around %%R/%R that allows -s/--size-name
    """
    _R = ipy.magics_manager.magics['cell']['R']
    def R(line, cell=None):
        import re
        line = line.strip()
        # If '-s'/'--size-name' exists, replace the first occurrence with '-w... -h...'
        match = re.match(r'(.*?)(?:(?:-s\s*|--size-name(?:\s+|=))(\w+\b))(.*)', line)
        if not match:
            # No more occurrences, stop
            return _R(line, cell)
        else:
            # Replace '-s'/'--size-name' with '-w... -h...'
            [prefix, size_name, suffix] = match.groups()
            width_height = R_line_width_height(**get_figsize_named(size_name)['R'])
            line = f"{prefix}{width_height}{suffix}"
            # Maybe more occurrences, recur
            return R(line, cell)
    ipy.register_magic_function(R, 'line_cell', 'R')


def R_line_width_height(width, height):
    """
    Format width/height args for %%R/%R magics
    """
    return f"-w{width} -h{height}"


def register_R_magics():
    extend_magic_R_with_defaults()
    extend_magic_R_with_sizename()


if load_ext_rpy2_ipython():
    register_R_magics()


#
# mpl
#


def plot_plt(
    passthru=None,
    tight_layout=plt.tight_layout,
):
    tight_layout and tight_layout()
    plt.show()
    return passthru


def plot_img(data, basename_suffix=''):
    data = _plot_img_cast(data)
    with potoo.mpl_backend_xee.basename_suffix(basename_suffix):
        return potoo.mpl_backend_xee.imsave_xee(data)


def _plot_img_cast(x):
    try:
        import IPython.core.display
        ipython_image_type = IPython.core.display.Image
    except:
        ipython_image_type = ()  # Empty tuple of types for isinstance, always returns False
    if isinstance(x, ipython_image_type):
        return PIL.Image.open(x.filename)
    else:
        return x


def plot_img_via_imshow(data):
    'Makes lots of distorted pixels, huge PITA, use imsave/plot_img instead'
    (h, w) = data.shape[:2]  # (h,w) | (h,w,3)
    dpi    = 100
    k      = 1  # Have to scale this up to ~4 to avoid distorted pixels
    with tmp_rcParams({
        'image.interpolation': 'nearest',
        'figure.figsize':      puts((w/float(dpi)*k, h/float(dpi)*k)),
        'savefig.dpi':         dpi,
    }):
        img = plt.imshow(data)
        img.axes.get_xaxis().set_visible(False)  # Don't create padding for axes
        img.axes.get_yaxis().set_visible(False)  # Don't create padding for axes
        plt.axis('off')                          # Don't draw axes
        plt.tight_layout(pad=0)                  # Don't add padding
        plt.show()


@contextmanager
def tmp_rcParams(kw):
    _save_mpl = mpl.RcParams(**mpl.rcParams)
    _save_plt = mpl.RcParams(**plt.rcParams)
    try:
        mpl.rcParams.update(kw)
        plt.rcParams.update(kw)  # TODO WHY ARE THESE DIFFERENT
        yield
    finally:
        mpl.rcParams = _save_mpl
        plt.rcParams = _save_plt


#
# ggplot
#   - Docs are incomplete but have some helpful examples: http://yhat.github.io/ggplot/docs.html
#   - Use the source for actual reference: https://github.com/yhat/ggplot
#


def plot_gg(
    g,
    tight_layout=None,  # Already does some sort of layout tightening, doing plt.tight_layout() makes it bad
):
    # TODO g.title isn't working? And is clobbering basename_suffix somehow?
    # with potoo.mpl_backend_xee.basename_suffix(g.title or potoo.mpl_backend_xee.basename_suffix.value()):
    # repr(g)  # (Over)optimized for repl/notebook usage (repr(g) = g.make(); plt.show())
    # TODO HACK Why doesn't theme_base.__radd__ allow multiple themes to compose?
    if not isinstance(g.theme, theme_rc):
        g += theme_rc({}, g.theme)
    g.make()
    tight_layout and tight_layout()
    plt.show()
    # return g # Don't return to avoid plotting a second time if repl/notebook


def gg_sum(*args):
    "Simpler syntax for lots of ggplot '+' layers when you need to break over many lines, comment stuff out, etc."
    return reduce(lambda a, b: a + b, args)


# TODO Update for plotnine
# import ggplot as gg
# class theme_rc(gg.themes.theme):
#     '''
#     - Avoids overriding key defaults from ~/.matplotlib/matplotlibrc (including figure.figsize)
#     - Allows removing existing mappings by adding {k: None}
#     - Avoids mutating the global class var theme_base._rcParams
#     - Hacks up a way to compose themes (base themes don't compose, and they also dirty shared global state)
#     - Can also passthru kwargs to gg.themes.theme, e.g. x_axis_text=attrs(kwargs=dict(rotation=45))
#     '''
#
#     def __init__(
#         self,
#         rcParams={},
#         theme=gg.theme_gray(),  # HACK: Copy default from ggplot.theme
#         **kwargs
#     ):
#         super(theme_rc, self).__init__(**kwargs)
#         rcParams.setdefault('figure.figsize', None)  # Use default, e.g. from ~/.matplotlib/matplotlibrc
#         self.rcParams = rcParams  # Don't mutate global mutable class var theme_base._rcParams
#         self.theme = theme
#
#     def __radd__(self, other):
#         self.theme.__radd__(other)                    # Whatever weird side effects
#         return super(theme_rc, self).__radd__(other)  # Our own weird side effects
#
#     def get_rcParams(self):
#         return {
#             k: v
#             for k, v in dict(self.theme.get_rcParams(), **self.rcParams).items()
#             if v is not None  # Remove existing mapping
#         }
#
#     def apply_final_touches(self, ax):
#         return self.theme.apply_final_touches(ax)
#
#
# import ggplot as gg
# class scale_color_cmap(gg.scales.scale.scale):
#     '''
#     ggplot scale from a mpl colormap, e.g.
#
#         scale_color_cmap('Set1')
#         scale_color_cmap(plt.cm.Set1)
#
#     Docs: http://matplotlib.org/users/colormaps.html
#     '''
#
#     def __init__(self, cmap):
#         self.cmap = cmap if isinstance(cmap, mpl.colors.Colormap) else plt.cm.get_cmap(cmap)
#
#     def __radd__(self, gg):
#         color_col = gg._aes.data.get('color', gg._aes.data.get('fill'))
#         n_colors = 3 if not color_col else max(gg.data[color_col].nunique(), 3)
#         colors = [self.cmap(x) for x in np.linspace(0, 1, n_colors)]
#         gg.colormap = self.cmap        # For aes(color=...) + continuous
#         gg.manual_color_list = colors  # For aes(color=...) + discrete
#         gg.manual_fill_list = colors   # For aes(fill=...)  + discrete
#         # ...                          # Any cases I've missed?
#         return gg


class gg_xtight(object):

    def __init__(self, margin=0.05):
        self.margin = margin

    def __radd__(self, g):
        g          = deepcopy(g)
        xs         = g.data[g._aes['x']]
        lims       = [xs.min(), xs.max()]
        margin_abs = float(self.margin) * (lims[1] - lims[0])
        g.xlimits  = [xs.min() - margin_abs, xs.max() + margin_abs]
        return g


class gg_ytight(object):

    def __init__(self, margin=0.05):
        self.margin = margin

    def __radd__(self, g):
        g          = deepcopy(g)
        ys         = g.data[g._aes['y']]
        lims       = [ys.min(), ys.max()]
        margin_abs = float(self.margin) * (lims[1] - lims[0])
        g.ylimits  = [ys.min() - margin_abs, ys.max() + margin_abs]
        return g


class gg_tight(object):

    def __init__(self, margin=0.05):
        self.margin = margin

    def __radd__(self, g):
        return g + gg_xtight(self.margin) + gg_ytight(self.margin)


#
# seaborn
#


def plot_sns(passthru=None):
    # TODO No way to set figsize for all seaborn plots? e.g. sns.factorplot(size, aspect) always changes figsize
    plt.show()
    return passthru


def sns_size_aspect(
    rows=1,
    cols=1,
    scale=1,
    figsize=np.array(mpl.rcParams['figure.figsize']),
):
    '''
    e.g. http://seaborn.pydata.org/generated/seaborn.factorplot.html
    '''
    (figw, figh) = figsize
    rowh = figh / rows * scale
    colw = figw / cols * scale
    return dict(
        size   = rowh,
        aspect = colw / rowh,
    )
