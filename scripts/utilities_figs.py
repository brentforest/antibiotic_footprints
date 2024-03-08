import numpy as np
import pandas as pd
import math
import paths
import winsound
import seaborn as sns
from utilities_figs import *
from utilities import *

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.transforms as mtrans
import matplotlib.patches as mpatches
from pandas.api.types import CategoricalDtype

pd.options.display.max_columns = 999
pd.options.mode.chained_assignment = None


def plot_error_bars(ax, df, x_var, y_var, down_var, up_var):
# Input: long-form dataframe with columns for x var, y var, and up/down y offset for each error bar

    # 2D array: 1st row = down distance, 2nd row = up distance
    # https://matplotlib.org/stable/api/_as_gen/matplotlib.pyplot.errorbar.html
    y_offset = df[[down_var, up_var]].values.transpose()

    # Draw error bars
    ax.errorbar(x=df[x_var], y=df[y_var], yerr=y_offset,
                fmt='none', ecolor='dimgrey', elinewidth=0.75, capsize=1.5, capthick=0.75)


def rotate_x_labels(ax, degrees=45, x_shift=4.2, y_shift=1):
# Rotate xtick labels, shift position
# Be sure to call this function AFTER other functions that may reset xtick label positions,
# otherwise the repositioning may be undone

    ax.set_xticklabels(ax.get_xticklabels(), rotation=degrees, ha='right')

    # Fine tuned positioning:
    # https://stackoverflow.com/questions/48326151/moving-matplotlib-xticklabels-by-pixel-value/48326438#48326438
    trans = mtrans.Affine2D().translate(x_shift, y_shift)
    for t in ax.get_xticklabels():
        t.set_transform(t.get_transform() + trans)


def show_save_plot(show=True, filename='', path='', transparent=False, format=['png']):
# Show or save figure, then close

    #if show==None:
    #    return
    if show:
        plt.show()
    else:
        if type(format) == str:
            format = [format]
        for f in format:
            if filename != '':
                if f == 'png':
                    plt.savefig(path + filename + '.png', format='png', dpi=300, transparent=transparent)
                elif f == 'pdf':
                            plt.savefig(path + filename + '.pdf', format='pdf', transparent=transparent)
                else:
                    print('ALERT: unrecognized image format')

        # Wipe figure after save
        plt.close()


def plot_bar(df, x, height=2.1, width=3.8, left=0.12, right=0.7, bottom=0.28, xlabel='', ylabel='', x_rotate_degrees=45, x_shift=2.2, yint=999, colors=[], edgecolor=None, hatch='', legend=True,
             show_figs=True, file_path='', filename='', file_format=['png', 'pdf'], stacked=True):

    # Explanation for why "subplots" is used even when creating a single plot:
    # https://stackoverflow.com/questions/34162443/why-do-many-examples-use-fig-ax-plt-subplots-in-matplotlib-pyplot-python
    fig, ax = plt.subplots(figsize=(width, height), dpi=80)

    df = df.set_index(x)

    plt.tight_layout
    fig.subplots_adjust(wspace=1, hspace=.15, left=left, right=right, bottom=bottom, top=0.96)
    if len(colors) > 0:
        df.plot.bar(ax=ax, stacked=stacked, width=0.65, edgecolor=edgecolor, color=colors, hatch=hatch)
    else:
        df.plot.bar(ax=ax, stacked=stacked, width=0.65)

    # Axes and grid
    ax.yaxis.grid(zorder=0, color='#D9D9D9')
    ax.set_axisbelow(True)
    ax.set_xlabel(xlabel)

    ax.tick_params(axis='x', length=0) # Set xtick length to zero
    rotate_x_labels(ax, x_shift=x_shift, y_shift=2, degrees=x_rotate_degrees)

    ax.set_ylabel(ylabel, rotation=90, labelpad=2)

    # y tick intervals
    if yint != 999:
        plt.yticks(np.arange(0, 21, yint))

    # Legend, with reversed label order to match stacked bars top-to-bottom
    if legend:
        handles, labels = ax.get_legend_handles_labels()
        ax.legend(reversed(handles), reversed(labels), loc='center left', bbox_to_anchor=(1, 0.5),
              edgecolor='white', handlelength=1.5, handletextpad=0.4)
    else:
        ax.get_legend().remove()

    show_save_plot(show=show_figs, path=file_path, filename=filename, transparent=False, format=file_format)


def plot_box(df, x, y, order, color, hue=None, ymax=0, yint=999, xlabel='', ylabel='',
             bottom=0.28, width=2.26, rotate_x_label=True, show_figs=True, file_path='', filename='', file_format=['png', 'pdf']):

    # Define figure
    fig, ax = plt.subplots(nrows=1, ncols=1, figsize=(width, 2.8), dpi=80)
    fig.tight_layout()  # Or equivalently,  "plt.tight_layout()"
    fig.subplots_adjust(wspace=.34, hspace=.15, left=0.21, right=0.98, bottom=bottom, top=0.96)

    sns.boxplot(ax=ax, x=df[x], y=df[y], order=order, color=color, zorder=10, hue=hue,
                linewidth=1, width=0.7, whis=1.5, showfliers=False)  # alternate setting: whis=np.inf

    # Change line color
    # https://stackoverflow.com/questions/43434020/black-and-white-boxplots-in-seaborn
    plt.setp(ax.artists, edgecolor='k', facecolor=color)
    plt.setp(ax.lines, color='k')


    #plt.axhline(y=0, color='k', lw=1)

    ax.set_ylim(top=ymax)

    ax.tick_params(axis='x', length=0)  # Set xtick length to zero
    if rotate_x_label:
        rotate_x_labels(ax, x_shift=2, y_shift=2)
    ax.set_xlabel(xlabel)

    ax.yaxis.grid(zorder=0, color='#D9D9D9') # This always seem to draw the grid in front. hmm.
    ax.set_axisbelow(True)

    ax.set_ylabel(ylabel, rotation=90, labelpad=3.5)
    ax.set_ylim(bottom=0)
    if yint != 999:
        plt.yticks(np.arange(0, ymax, yint))

    show_save_plot(show=show_figs, path=file_path, filename=filename, format=file_format)


def get_scale(a=1):  # a is the scale of your negative axis
# I we want axis values <0 scaled differently than values >0
#https://stackoverflow.com/questions/53699677/matplotlib-different-scale-on-negative-side-of-the-axis

    def forward(x):
        x = (x >= 0) * x + (x < 0) * x * a
        return x

    def inverse(x):
        x = (x >= 0) * x + (x < 0) * x / a
        return x

    return forward, inverse


def plot_scatter(df, x, y, size=14, size_range=(5,500), x_label='', y_label='', x_min='', x_max='', x_tick_interval='', y_min='', y_max='', fig_width=3.6, zorder=3,
                 gridlines=True, x_log_scale=False, legend=True, clip_on=False,
                 scatter_kwargs={}, **kwargs):

    fig, ax = plt.subplots(nrows=1, ncols=1, figsize=(fig_width, 3.5), dpi=80)
    fig.tight_layout()  # Or equivalently,  "plt.tight_layout()"
    fig.subplots_adjust(left=0.12, bottom=0.1, top=0.95, right=0.96)

    if x_log_scale:
        ax.set_xscale('log')

    sns.scatterplot(ax=ax, data=df, x=x, y=y, size=size, sizes=size_range, zorder=zorder, clip_on=clip_on, **scatter_kwargs)

    if gridlines:
        plt.axhline(y=0, color='k', lw=1)
        plt.axvline(x=0, color='k', lw=1)

    if legend:
        plt.legend(frameon=False)
    else:
        #ax.get_legend().remove()
        ax.legend().set_visible(False)
        #ax.plot(legend=None)

    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label, rotation=90, labelpad=1.5)

    if x_min == '':
        x_min = ax.get_xlim()[0]
    if x_max == '':
        x_max = ax.get_xlim()[1]
    if y_min == '':
        y_min = ax.get_ylim()[0]
    if y_max =='':
        y_max = ax.get_ylim()[1]

    ax.set_xlim(x_min, x_max)
    ax.set_ylim(y_min, y_max)

    if x_tick_interval != '':
        plt.xticks(np.arange(x_min, x_max+0.01, x_tick_interval))

    """
    forward, inverse = get_scale(a=10)
    ax.set_xscale('function', functions=(forward, inverse))  # this is for setting x axis
    ax.set_yscale('function', functions=(forward, inverse))  # this is for setting x axis
    """

def plot_strip_diets(df, x='item', y='footprint', dot_size=2.5, order='', color='', hue='', palette='', y_max=-999, y_label='', y_axis='left',
                     width=1.8, rotate_x_label=True):
# It's probably inefficient have two separate strip plot functions, but the dimensions and inputs are so different between different plots (e.g., items vs. diets)
# that it ended up being more work to try and create one function to do everything.

    fig, ax = plt.subplots(nrows=1, ncols=1, figsize=(width, 2.8), dpi=80)
    fig.tight_layout()  # Or equivalently,  "plt.tight_layout()"
    fig.subplots_adjust(wspace=.34, hspace=.15, left=0.25, right=0.98, bottom=0.28, top=0.96)

    # Optional arguments
    if order != '':
        df = s_categorical_sort(df, col=x, sort_order=order)

    # Hack for adding medians as a scatterplot:
    # https://stackoverflow.com/questions/67481900/how-to-add-a-mean-line-to-a-seaborn-stripplot-or-swarmplot
    #sns.scatterplot(ax=ax, data=df, x=x, y='median', marker="|", s=1, linewidth=20, color='black', zorder=30)

    # Optional arguments
    kwargs = {}
    if order !='':
        kwargs['order']=order
    if hue != '':
        kwargs = {**kwargs, **{'hue': hue, 'palette': palette}}  # Append additional key:value pairs
    elif color !='':
        kwargs['color'] = color  # Add key:value pair

    ax.yaxis.grid(zorder=0, color='#D9D9D9')
    ax.set_axisbelow(True)

    # clip_on puts dots in front of axes
    # cut: linewidth=0.25, edgecolor='white'
    sns.stripplot(ax=ax, data=df, x=x, y=y, dodge=True, jitter=0.3, size=dot_size, marker='o', zorder=10, linewidth=0.25, edgecolor='white', clip_on=False, **kwargs)

    # Explanation of why zorder has to be set for boxprops:
    # https://stackoverflow.com/questions/44615759/how-can-box-plot-be-overlaid-on-top-of-swarm-plot-in-seaborn
    sns.boxplot(ax=ax, x=df[x], y=df[y], order=order, boxprops={'fill': None, "zorder":999}, zorder=999, linewidth=1, width=0.7, whis=1.5, showfliers=False)  # alternate setting: whis=np.inf

    # Change line color
    # https://stackoverflow.com/questions/43434020/black-and-white-boxplots-in-seaborn
    plt.setp(ax.artists, edgecolor='k')
    plt.setp(ax.lines, color='k')

    ax.tick_params(axis='x', length=0)  # Set xtick length to zero
    plt.xlabel('')
    if rotate_x_label:
        rotate_x_labels(ax, x_shift=2, y_shift=2)

    plt.ylabel(y_label)

    ax.set_ylim(bottom=0)

    if y_max != -999:
        ax.set_ylim(top=y_max)

    # Put y-axis on the right side, in case we're trying to make a dual-axis plot
    if y_axis == 'right':
        ax.yaxis.tick_right()


def plot_strip_items(df, x='item', y='footprint', order='', color='', hue='', palette='', y_max=-999, y_label='', y_axis='left'):
# It's probably inefficient have two separate strip plot functions, but the dimensions and inputs are so different between different plots (e.g., items vs. diets)
# that it ended up being more work to try and create one function to do everything.

    # Define figure and subplots
    fig, ax = plt.subplots(nrows=1, ncols=1, figsize=(3.5, 2.2), dpi=80)
    fig.tight_layout()  # Or equivalently,  "plt.tight_layout()"
    fig.subplots_adjust(wspace=.34, hspace=.15, left=0.11, bottom=0.18, top=0.98)

    """
    # Hack for adding medians as a scatterplot:
    # https://stackoverflow.com/questions/67481900/how-to-add-a-mean-line-to-a-seaborn-stripplot-or-swarmplot
    if order != '': 
        df = s_categorical_sort(df, col=x, sort_order=order)
    sns.scatterplot(ax=ax, data=df, x=x, y='median', marker="|", s=1, linewidth=20, color='black', zorder=30)
    """

    # Optional arguments
    kwargs = {}
    if order !='':
        kwargs['order']=order
    if hue != '':
        kwargs = {**kwargs, **{'hue': hue, 'palette': palette}}  # Append additional key:value pairs
    elif color !='':
        kwargs['color'] = color  # Add key:value pair

    ax.yaxis.grid(zorder=0, color='#D9D9D9')
    ax.set_axisbelow(True)

    # Sort L-R by median and plot
    # clip_on puts dots in front of axes
    sns.stripplot(ax=ax, data=df, x=x, y=y, dodge=True, jitter=0.3, size=2.5, marker='o', zorder=10, linewidth=0.25, edgecolor='white', clip_on=False, **kwargs)

    # Explanation of why zorder has to be set for boxprops:
    # https://stackoverflow.com/questions/44615759/how-can-box-plot-be-overlaid-on-top-of-swarm-plot-in-seaborn
    sns.boxplot(ax=ax, x=df[x], y=df[y], boxprops={'fill': None, "zorder": 999}, zorder=999, linewidth=1,
                width=0.7, whis=1.5, showfliers=False)  # alternate setting: whis=np.inf

    # Change line color
    # https://stackoverflow.com/questions/43434020/black-and-white-boxplots-in-seaborn
    plt.setp(ax.artists, edgecolor='k')
    plt.setp(ax.lines, color='k')

    ax.tick_params(axis='x', length=0)  # Set xtick length to zero
    plt.xlabel('')

    plt.ylabel(y_label)

    ax.set_ylim(bottom=0)

    if y_max != -999:
        ax.set_ylim(top=y_max)

    # Put y-axis on the right side, in case we're trying to make a dual-axis plot
    if y_axis == 'right':
        ax.yaxis.tick_right()
