import numpy as np
import pandas as pd
import gc # Garbage collection module, to save memory
import math
import paths
import winsound
from datetime import datetime
from utilities_figs import *
from utilities import *

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.transforms as mtrans
import matplotlib.patches as mpatches
from pandas.api.types import CategoricalDtype

pd.options.display.max_columns = 999
pd.options.mode.chained_assignment = None

# If SHOW_FIGS == False, figs fig data are saved
SHOW_FIGS = False
OUTPUT_PATH = '../figures/%_exported/'

def add_country_labels(df, x_min=0.35, y_min=6, x_offset=0.03, y_offset=0, size=6.15, excl_labels=[]):
# TODO: make this a shared function w/diet shifts?

    df = df.reset_index()
    for i in range(0, len(df['supply_side_total'])):
        if (df['supply_side_total'][i] > x_min) | (df['%_exported'][i] > y_min):
            if df['country'][i] not in excl_labels:
                plt.text(x=df['supply_side_total'][i] + x_offset, y=df['%_exported'][i] + y_offset, s=df['country'][i],
                     fontdict=dict(color='k', size=size))

# Main method
def figs_scatter_percent_exported():

    # Input ************************************************************************************************************

    supply = pd.read_csv(paths.output / 'by_coo_only/supply_side_footprints_by_country_item.csv')

    income_reclassification = pd.read_csv(paths.input / 'figures/income_reclassification.csv')

    # Convert df to dictionary, adapted from https://stackoverflow.com/questions/26716616/convert-a-pandas-dataframe-to-a-dictionary
    income_colors = pd.read_csv(paths.input / 'figures/income_class_order_color.csv') \
        [['income_class', 'color_abx']].set_index('income_class').T.to_dict('records')[0]
    #print(income_colors)

    # hue_order determines order in which each series is displayed in the legend
    income_order = pd.read_csv(paths.input / 'figures/income_class_order_color.csv')['income_class'].to_list()

    # Set font *********************************************************************************************************

    font = {'family': 'Arial',
            'size': 6.15}
    matplotlib.rc('font', **font)

    # ******************************************************************************************************************

    results_cols = ['supply_side_total', 'supply_side_exports']

    supply = s_filter(supply, col='footprint_type', list=['mg_abx_total'])

    # Groupby by country; we're not interested individual items
    supply = supply.groupby(['country_code', 'country', 'region', 'income_class'])[results_cols].sum().reset_index()

    # Convert to 1,000 metric tons
    for c in results_cols:
        supply[c] /= 1000000000000

    # Compute fraction of supply side production sent out as exports
    supply['%_exported'] = (supply['supply_side_exports'] / supply['supply_side_total']) * 100

    # Edge case:
    # FBS data have some countries exporting more than they produce, leading to %_exported > 100%.
    supply['%_exported'] = supply['%_exported'].clip(upper=100)

    # Combine low income w/unclassified
    supply = s_merge_rename(supply, col='income_class', new_names=income_reclassification)
    supply = supply.rename(columns={'income_class': 'Income class'})

    supply.to_csv(OUTPUT_PATH + 'abx_%_exported.csv', index=False)

    #supply_lmic = s_filter(supply, col='Income class', list=['Low income / unclassified', 'Lower middle income'])


    """
    # Log scale version
    plot_scatter(supply, x='supply_side_total', y='%_exported', clip_on=False,
                 hue='income_class', hue_order=income_order, palette=income_colors, log_scale=True,
                 x_min=0.00001, x_max=100, y_min=0.00001, y_max=100,
                 x_label='1000 mt supply-side antimicrobial use',
                 y_label='% of supply-side antimicrobial use attributable to exports')
    """

    # These get passed to plot_scatter and unpacked when plot_scatter calls sns.scatterplot
    x = 'supply_side_total'
    scatter_kwargs = {'alpha': 1,
                      'hue': 'Income class', 'hue_order': income_order, 'palette': income_colors,
                      'linewidths': 0.05, 'edgecolors': 'white'}

    plot_scatter(supply, x=x, y='%_exported', clip_on=False,
                 x_min=0, x_max=3.8, y_min=0, y_max=100,
                 gridlines=False,
                 x_label='1000 mt supply-side antimicrobial use',
                 y_label='% of supply-side antimicrobial use attributable to exports', show_figs=None, scatter_kwargs=scatter_kwargs)
    add_country_labels(supply)

    """
    # LMIC version
    plot_scatter(supply_lmic, x='supply_side_total', y='%_exported', clip_on=False,
                 log_scale=False, x_max=3.0, y_max=60,
                 gridlines=False,
                 x_label='1000 mt supply-side antimicrobial use',
                 y_label='% of supply-side antimicrobial use attributable to exports', show_figs=None, scatter_kwargs = scatter_kwargs)

    # Add LMIC labels
    supply = supply.replace({'country': {'United States of America': 'United States'}})
    for i in range(supply.shape[0]):
        # if supply['supply_side_total'][i] > .1:
        if (supply['supply_side_total'][i] > 0.35) & (supply['supply_side_total'][i] < 3.5) & (
                supply['%_exported'][i] > 6) & (supply['Income class'][i] in ['Low income / unclassified', 'Lower middle income']):
            plt.text(x=supply['supply_side_total'][i] + 0.03, y=supply['%_exported'][i] + 0.0, s=supply['country'][i],
                     fontdict=dict(color='k', size=6.15))
        if (supply['%_exported'][i] > 20) & (
                supply['Income class'][i] in ['Low income / unclassified', 'Lower middle income']):
            plt.text(x=supply['supply_side_total'][i] + 0.03, y=supply['%_exported'][i] + 0.0, s=supply['country'][i],
                     fontdict=dict(color='k', size=6.15))
    """

    show_save_plot(show=SHOW_FIGS, path=OUTPUT_PATH, format=['png', 'pdf'], filename='abx_%_exported')
    #show_save_plot(show=SHOW_FIGS, path=OUTPUT_PATH, format=['png', 'pdf'], filename='abx_%_exported_lmic')

    # Version w/outliers
    plot_scatter(supply, x=x, y='%_exported', clip_on=False,
                 x_min=0, y_min=0,
                 gridlines=False,
                 x_label='1000 mt supply-side antimicrobial use',
                 y_label='% of supply-side antimicrobial use attributable to exports', show_figs=None, scatter_kwargs = scatter_kwargs)
    add_country_labels(supply)
    show_save_plot(show=SHOW_FIGS, path=OUTPUT_PATH, format=['png', 'pdf'], filename='abx_%_exported_w_outliers')

    # ******************************************************************************************************************
    # Log transformed version

    if 0 in supply[x]:
        print('Dropping zeroes from log scale plot')
        supply = supply[supply[x] != 0]

    if supply[x].min() < 0:
        print('WARNING: negative values included in log scale plot; these will not be plotted')

    # Filter so we don't show tiny values
    supply[x] *= 1000 # convert 1000 mt back to mt
    x_min = 1
    supply = supply[supply[x] > x_min]

    plot_scatter(supply, x=x, y='%_exported', zorder=99, clip_on=False,
                 hue='income_class', hue_order=income_order, palette=income_colors, x_log_scale=True, x_min=x_min, x_max=50000, y_min=0, y_max=100,
                 x_label='mt supply-side antimicrobial use',
                 y_label='% of supply-side antimicrobial use attributable to exports', show_figs=None, scatter_kwargs = scatter_kwargs)

    excl_labels=['United Arab Emirates', 'Germany', 'United States of America', 'China, mainland', 'United Kingdom of Great Britain and Northern Ireland',
                 'China, Hong Kong SAR', 'Nicaragua', 'Greece', 'Sweden', 'Russian Federation', 'Botswana', 'Denmark', 'Pakistan', 'Argentina', 'Portugal',
                 'Turkey', 'Bosnia and Herzegovina', 'Guinea-Bissau', 'Guatemala']
    add_country_labels(supply, x_min=1000, y_min=16, x_offset=0, size=6, excl_labels=excl_labels)
    show_save_plot(show=SHOW_FIGS, path=OUTPUT_PATH, format=['png', 'pdf'], filename='abx_%_exported_log_scale')
