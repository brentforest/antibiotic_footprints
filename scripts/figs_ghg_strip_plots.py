import numpy as np
import pandas as pd
import gc # Garbage collection module, to save memory
import math
import paths
import winsound
from datetime import datetime
from utilities import *
from utilities_figs import *
from item_footprints_abx_concat_classify import *

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.transforms as mtrans
import matplotlib.patches as mpatches
from pandas.api.types import CategoricalDtype

pd.options.display.max_columns = 999
pd.options.mode.chained_assignment = None

SHOW_FIGS = False
PATH = '../figures/ghg_strip_plot/'
ORDER = ['Sheep & goat', 'Pig meat',  'Bovine meat', 'Aquatic animals', 'Poultry meat','Crops']
BKO_ORDER = ['Pigmeat, intensive',  'Pigmeat, extensive', 'Poultry Meat, intensive','Poultry Meat, extensive']

def prep_ghg(ghg_gleam, ghg_coo, ghg_dist):
# Compile GHGe footprint data
# Note that by GLEAM data are BEFORE applying regional or global averages if there were no country-specific data.

    # GLEAM:
    # Drop milk and eggs, sum over footprint types
    ghg_gleam = s_filter(ghg_gleam, col='fbs_item', list=['Bovine Meat', 'Mutton & Goat Meat', 'Pigmeat', 'Poultry Meat'])\
        .groupby(['country', 'fbs_item'])['footprint'].sum().reset_index()\
        .rename(columns={'country': 'item_index', 'fbs_item': 'item'})

    # Crop LUC data:
    # Only applicable to soy; palm oils get dropped from ghg_dist.
    # Compute an average that we will add to ghg_dist.
    ghg_coo = s_filter(ghg_coo, col='fbs_item', list=['Soyabeans'])\
        .pipe(s_filter, col='footprint_type', list=['kg_co2_luc_human_palm_soy'])\
        .groupby('fbs_item')['footprint'].mean().reset_index()\
        .rename(columns={'footprint': 'footprint_luc'})

    # Distributions data:
    # Add soyabean LUC
    ghg_dist = ghg_dist.merge(ghg_coo, on='fbs_item', how='left')
    ghg_dist['footprint_luc'] = ghg_dist['footprint_luc'] .fillna(0)
    ghg_dist['footprint'] += ghg_dist['footprint_luc']

    # Drop insects and special animals, vegetable oils,
    # "special" items (copies of forage fish for per unit plotting purposes), and water footprints
    ghg_dist = s_filter(ghg_dist, col='type', list=['plant', 'a_animal']) \
        .pipe(s_filter, col='fbs_group', excl_list=['Vegetable Oils']) \
        .pipe(s_filter, col='include_in_model', excl_list=['special']) \
        .pipe(s_filter, col='footprint_type', list=['kg_co2e_excl_luc']) \
        .rename(columns={'type': 'item'})[['item', 'footprint']]

    # Add a unique identifier (ghg_dist doesn't have one; countries, sources, etc. are all non-unique)
    ghg_dist['item_index'] = ghg_dist['item'].index

    ghg = pd.concat([ghg_gleam, ghg_dist], sort=False)
    ghg['item'] = ghg['item'].replace({'plant': 'Crops', 'a_animal': 'Aquatic animals'})
    ghg['footprint_type'] = 'kg_co2e'
    ghg.to_csv(paths.diagnostic / 'abx/ghg_for_strip_plot.csv', index=False)

    return ghg


def prep_ghg_bko(ghg_bko):

    # Filter, sum over footprint types, merge w/production data
    ghg_bko = s_filter(ghg_bko, col='fbs_item', list=['Pigmeat', 'Poultry Meat']) \
            .pipe(s_filter, col='system', list=['intensive', 'extensive']) \
            .groupby(['country', 'system', 'fbs_item'])['footprint'].sum().reset_index()

    ghg_bko['item'] = ghg_bko['fbs_item'] + ', ' + ghg_bko['system']
    ghg_bko['footprint_type'] = 'kg_co2e_bko'
    ghg_bko = ghg_bko[['item', 'country', 'footprint_type', 'footprint']].rename(columns={'country': 'item_index'})

    return ghg_bko


def plot_strip(df, color='', hue='', palette='', y_max=-999, y_label='', y_axis='left'):

    # Define figure and subplots
    fig, ax = plt.subplots(nrows=1, ncols=1, figsize=(3, 4), dpi=80)
    fig.tight_layout()  # Or equivalently,  "plt.tight_layout()"
    fig.subplots_adjust(wspace=.34, hspace=.15, left=0.15, bottom=0.18, top=0.98)

    # Hack for adding medians as a scatterplot:
    # https://stackoverflow.com/questions/67481900/how-to-add-a-mean-line-to-a-seaborn-stripplot-or-swarmplot
    sns.scatterplot(ax=ax, data=df, x='item', y='median', marker="|", s=1, linewidth=20, color='black', zorder=30)

    # Optional arguments for plotting multiple series
    kwargs = {}
    if hue != '':
        kwargs = {**kwargs, **{'hue': hue, 'palette': palette}}  # Append additional key:value pairs
    elif color !='':
        kwargs['color'] = color  # Add key:value pair

    ax.yaxis.grid(zorder=0, color='#D9D9D9')
    ax.set_axisbelow(True)

    # Sort L-R by median and plot
    # clip_on puts dots in front of axes
    sns.stripplot(ax=ax, data=df, x='item', y='footprint', dodge=True, jitter=0.3, size=2.5, marker='o', zorder=20, clip_on=False, **kwargs)

    ax.tick_params(axis='x', length=0)  # Set xtick length to zero
    plt.xlabel('')
    plt.ylabel(y_label)

    ax.set_ylim(bottom=0)

    if y_max != -999:
        ax.set_ylim(top=y_max)

    # Put y-axis on the right side, in case we're trying to make a dual-axis plot
    if y_axis == 'right':
        ax.yaxis.tick_right()


# Main method
def figs_ghg_strip_plots():

    # Input ************************************************************************************************************

    # item names
    item_names = pd.read_csv(paths.input / 'figures/item_names.csv')

    # GHGe footprints, for side-by-side comparisons
    ghg_gleam = pd.read_csv(paths.interim / 'item_footprints/item_footprints_gleam.csv')
    ghg_coo = pd.read_csv(paths.interim / 'item_footprints/item_footprints_by_coo.csv')
    ghg_dist = pd.read_excel(paths.input/'ghge/ghge_lit_review_distributions.xlsx', sheet_name='ghge_combined', skiprows=3)

    # GHGe broken out by system
    ghg_bko = pd.read_csv(paths.interim / 'item_footprints/item_footprints_gleam_by_system.csv')

    # Prep *************************************************************************************************************

    # Set font
    font = {'family': 'Arial',
            'size': 6.15}
    matplotlib.rc('font', **font)

    # prep abx, ghghe, abx broken out by source
    fp = prep_ghg(ghg_gleam, ghg_coo, ghg_dist)
    bko = prep_ghg_bko(ghg_bko)

    # Rename items
    fp = s_merge_rename(fp, item_names, col='item', new_name_col='item_renamed')

    # Compute medians
    fp['median'] = fp.groupby(['item', 'footprint_type'])['footprint'].transform('median')
    bko['median'] = bko.groupby(['item', 'footprint_type'])['footprint'].transform('median')

    # Sort
    fp = fp.sort_values(by='median', ascending=False)
    #fp = s_categorical_sort(fp, col='item', sort_order=ORDER)
    bko = s_categorical_sort(bko, col='item', sort_order=BKO_ORDER)

    # Add N to item names so they shop up in plots
    fp['n'] = fp.groupby(['item', 'footprint_type'])['footprint'].transform('size')

    # Format item names
    fp['item'] = fp['item'].str.replace(' ', '\n')
    fp = fp.replace({'item': {'Sheep\n&\ngoat': 'Sheep\n& goat',
                              'Crops': 'Crops\n',}})

    bko['item'] = bko['item'].str.replace('Pigmeat, ', 'Pig meat,\n') \
        .str.replace('Poultry Meat, ', 'Poultry meat,\n') \
        .str.replace('Poultry Meat', 'Poultry meat,\n')

    #fp['item'] = fp['item'].str.replace(' ','\n').str.replace('Sheep\n&\ngoat', 'Sheep\n& goat')\
    #    .str.replace('Crops', 'Crops\n').str.replace('

    fp['item'] = fp['item'] + '\n\nN=' + fp['n'].astype(str)


    # Plot

    plot_strip(s_filter(fp, col='footprint_type', list=['kg_co2e']), color='indianred',
               y_label='kg CO2e per kg yield')
    show_save_plot(show=SHOW_FIGS, path=PATH, format=['png', 'pdf'], filename='strip_plot_ghg')



    plot_strip(s_filter(bko, col='footprint_type', list=['kg_co2e_bko']), color='indianred',
               y_label='kg CO2e per kg yield')
    show_save_plot(show=SHOW_FIGS, path=PATH, format=['png', 'pdf'], filename='strip_plot_ghg_bko')