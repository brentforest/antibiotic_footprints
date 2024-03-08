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
FILE_PATH = '../figures/diet_shifts_income/'
FIG_FORMAT = ['png', 'pdf']
DIETS = ['Baseline', 'High income', 'EAT-Lancet']

# %_diff: compute percent difference from baseline
# abs_diff: compute absolute difference from baseline
DIFF_PARAM = 'abs_diff'
STATIC_AXIS_RANGES = True # if True, x- and y-ranges are the same across all scatterplot panels
POPULATION_DOT_SCALING = True

if DIFF_PARAM == 'abs_diff':
    X_LABEL = 'Change in antibiotics from baseline, grams / capita / year'
    Y_LABEL = 'Change in GHGe from baseline, mt CO2e / capita / year'
else:
    X_LABEL='% change in ABU' # Note % change is agnostic to per capita of population-wide
    Y_LABEL='% change in GHGe'

def prep_abx_ghg(fp, diet_names, income_reclassification,population):

    # Adjust units
    fp['value'] /= 1000  # mg to grams abx, kg to mt CO2e
    fp['value_baseline'] /= 1000

    # Rename diets; filter; add income classes; rename columns for fig display
    fp = s_merge_rename(fp, diet_names, col='diet') \
        .pipe(s_filter, col='diet', list=DIETS) \
        .pipe(s_merge_rename, income_reclassification, col='income_class') \
        .rename(columns={'attribute': 'footprint_type'})

    # Prep abx
    # Since this has a groupby and sum, be sure to add population size AFTER the groupby
    # We add population so we can use it for dot size and global footprints
    abx = s_filter(fp, col='footprint_type', list=['mg_abx_total']) \
        .groupby(['country_code', 'country', 'diet', 'income_class', 'footprint_type'])[['value', 'value_baseline']].sum().reset_index() \
        .pipe(s_merge, population, on=['country_code', 'country'], how='left', validate='m:1')

    # Prep ghg
    ghg = s_filter(fp, col='footprint_type', list=['kg_co2e_total']) \
        .pipe(s_merge, population, on=['country_code', 'country'], how='left', validate='m:1')

    # We could recombine these into one dataframe before computing population totals in one step instead of two,
    # but they need to be separate files for plotting box plots anyway
    abx['value_pop_total'] = abx['value'] * abx['population'] / 1000000000 # grams to 1000 mt
    ghg['value_pop_total'] = ghg['value'] * ghg['population'] / 1000000000 # mt to GT

    return (abx, ghg)


def prep_diff(abx, ghg):

    abx['attribute'] = 'diff_abx'
    ghg['attribute'] = 'diff_ghg'

    # Concat
    diff = pd.concat([ghg, abx], sort=False)

    # Compute % difference, pivot on footprint type
    diff['diff'] = diff['value'] - diff['value_baseline']
    if DIFF_PARAM == '$_diff':
        diff['diff'] /= diff['value_baseline'] * 100
    diff = s_pivot(diff, idx=['country_code', 'country', 'income_class', 'diet', 'population'], cols=['attribute'], vals=['diff'])

    # Sorting makes sure the largest dots are always in the back so they don't obscure smaller dots
    #diff['dot_size'] = (diff['population'] / 2500000) + 5
    diff['dot_size'] = (diff['population'] / 1000000) + 1
    diff = diff.sort_values(by='dot_size', ascending=False)

    return diff


def plot_diets(abx, ghg):

    abx['income_class'] = abx['income_class'].str.replace(' income', '')
    ghg['income_class'] = ghg['income_class'].str.replace(' income', '')

    income_order = ['High', 'Upper middle', 'Lower middle', 'Low / unclassified']

    # Box and whisker plots
    kwargs = {'bottom': 0.32, 'show_figs': SHOW_FIGS, 'file_path': FILE_PATH, 'file_format': FIG_FORMAT}

    """
    plot_box(abx, x='diet', y='value', order=DIETS, ymax=25, color='orange', xlabel='Scenario', ylabel='grams antibiotics / capita / year', filename='box_plot_abx_by_scenario', **kwargs)
    plot_box(ghg, x='diet', y='value', order=DIETS, ymax=4.5, yint=1, color='indianred', xlabel='Scenario', ylabel='mt CO2e / capita / year', filename='box_plot_ghg_by_scenario', **kwargs)
    """
    # Baseline only
    abx_bl = s_filter(abx, col='diet', list=['Baseline'])
    ghg_bl = s_filter(ghg, col='diet', list=['Baseline'])
    """
    plot_box(abx_bl, x='income_class', y='value', ymax=15, order=income_order, color='orange', xlabel='Income class', ylabel='grams antibiotics / capita / year', filename='box_plot_abx_by_income',  **kwargs)

    plot_box(abx_bl, x='income_class', y='value', ymax=15, order=income_order, color='orange', xlabel='Income class', ylabel='grams antibiotics / capita / year', filename='box_plot_abx_by_income_wide',
             rotate_x_label=False, width=3.7, **kwargs)

    plot_box(ghg_bl, x='income_class', y='value', ymax=4.5, yint=1, order=income_order, color='indianred',
             xlabel='Income class', ylabel='mt CO2e / capita / year', filename='box_plot_ghg_by_income',  **kwargs)
    """
    # Global total by income class (UNUSED)
    #abx_inc = abx.groupby(['diet', 'income_class', 'footprint_type'])['value'].sum().reset_index()
    #ghg_inc = ghg.groupby(['diet', 'income_class', 'footprint_type'])['value'].sum().reset_index()

    # EDGE CASE: A few (3?) countries probably don't have any pork production, so scaling up pigmeat to replace bovine
    # results in an footprint of infinity.
    abx = s_filter(abx, col='value', excl_list=[np.inf])
    ghg = s_filter(ghg, col='value', excl_list=[np.inf])

    # Global total
    abx_glob = abx.groupby(['diet', 'footprint_type'])['value_pop_total'].sum().reset_index() \
        .pipe(s_categorical_sort, col='diet', sort_order=DIETS)
    ghg_glob = ghg.groupby(['diet', 'footprint_type'])['value_pop_total'].sum().reset_index() \
        .pipe(s_categorical_sort, col='diet', sort_order=DIETS)

    plot_bar(abx_glob, x='diet', width=3, height=2.8, stacked=False, xlabel='Diet', ylabel='1,000 mt MI antibiotics / year',
             colors='orange', edgecolor='k', legend=False, filename='abx_global', **kwargs)
    plot_bar(ghg_glob, x='diet', width=3, height=2.8, stacked=False, xlabel='Diet', ylabel='GT CO2e / year',
             colors='indianred', edgecolor='k', legend=False, filename='ghg_global', **kwargs)
    #plot, x = 'country', y_label = 'kcal/capita/day', colors = food_colors_all, filename = 'kcal_per_cap_by_food')

    # Strip plots by diet
    abx['median'] = abx.groupby(['diet'])['value'].transform('median')
    ghg['median'] = ghg.groupby(['diet'])['value'].transform('median')

    plot_strip_diets(abx, x='diet', y='value', order=DIETS, color='orange', y_max=28, y_label='grams antibiotics / capita / year')
    show_save_plot(show=SHOW_FIGS, path=FILE_PATH, format=FIG_FORMAT, filename='strip_plot_abx_by_scenario')

    plot_strip_diets(ghg, x='diet', y='value', order=DIETS, color='lightcoral', y_max=4.5, y_label='mt CO2e / capita / year')
    show_save_plot(show=SHOW_FIGS, path=FILE_PATH, format=FIG_FORMAT, filename='strip_plot_ghg_by_scenario')

    # Strip plots by income
    abx_bl['median'] = abx_bl.groupby(['income_class'])['value'].transform('median')
    ghg_bl['median'] = ghg_bl.groupby(['income_class'])['value'].transform('median')
    plot_strip_diets(abx_bl, x='income_class', y='value', order=income_order, color='orange', y_max=15,dot_size=3,
                     y_label='grams antibiotics / capita / year')
    show_save_plot(show=SHOW_FIGS, path=FILE_PATH, format=FIG_FORMAT, filename='strip_plot_abx_by_income')

    plot_strip_diets(abx_bl, x='income_class', y='value', order=income_order, color='orange', y_max=15, dot_size=3,
                     y_label='grams antibiotics / capita / year', rotate_x_label=False, width=3.9)
    show_save_plot(show=SHOW_FIGS, path=FILE_PATH, format=FIG_FORMAT, filename='strip_plot_abx_by_income_wide')

    plot_strip_diets(ghg_bl, x='income_class', y='value', order=income_order, color='lightcoral', y_max=3, dot_size=3,
                     y_label='mt CO2e / capita / year')
    show_save_plot(show=SHOW_FIGS, path=FILE_PATH, format=FIG_FORMAT, filename='strip_plot_ghg_by_income')


def plot_diff(diff, diet, x_max, y_max, label_dots=[], x_min=-100, y_min=-100, file_suffix='', clip_on=False):

    if STATIC_AXIS_RANGES:
        x_min = -25
        x_max = 25
        y_min = -4
        y_max = 4

    diff = s_filter(diff, col='diet', list=[diet])
    diff = diff.rename(columns={'income_class': 'Income class'})

    # These get passed to plot_scatter and unpacked when plot_scatter calls sns.scatterplot
    scatter_kwargs = {'alpha': 1,
              'hue': 'Income class', 'hue_order': income_order, 'palette': income_colors,
              'linewidth': 0.25, 'edgecolors': 'white'}

    # These get unpacked upon calling plot_scatter
    diff = diff.rename(columns={'income_class': 'Income class'})
    plot_scatter(diff, x='diff_abx', y='diff_ghg', size='dot_size',
                 x_min=x_min, x_max=x_max, y_min=y_min,  y_max=y_max,
                 x_label=X_LABEL, y_label=Y_LABEL,
                 legend=False, clip_on=clip_on, x_tick_interval=5,
                 scatter_kwargs = scatter_kwargs)

    # Add labels to each dot

    # For whatever reason df index may be out of sorts, so we reset it so it starts at 0
    if label_dots != []:
        df = diff.reset_index()

        for i in range(0, len(df['diff_ghg'])):
            #if df['population'][i] > 50000000:
            if df['country'][i] in label_dots:
                plt.text(x=df['diff_abx'][i]+.05, y=df['diff_ghg'][i]+0.1, s=df['country'][i],
                     fontdict=dict(color='k', size=6.15))

    #diet = diet.replace('/', '_')

    show_save_plot(show=SHOW_FIGS, path=FILE_PATH, filename='abx_ghg_scatter_by_income_' + diet + file_suffix, format=FIG_FORMAT)

    # Version w/outliers
    plot_scatter(diff, x='diff_abx', y='diff_ghg', size='dot_size',
                 x_label=X_LABEL, y_label=Y_LABEL, x_tick_interval=5,
                 scatter_kwargs=scatter_kwargs)

    show_save_plot(show=SHOW_FIGS, path=FILE_PATH, filename='abx_ghg_scatter_by_income_w_outliers_' + diet + file_suffix, format=FIG_FORMAT)


def plot_diff_all_scenarios(diff, diets, label_dots=[],  file_suffix=''):
# Show all diets on the same plot, although this gets very busy

    diff = s_filter(diff, col='diet', list=diets)
    diff = diff.rename(columns={'income_class': 'Income class'})

    # These get passed to plot_scatter and unpacked when plot_scatter calls sns.scatterplot
    scatter_kwargs = {'alpha': 1,
              'hue': 'diet', 'hue_order': DIETS,
              'linewidths': 200, 'linewidth': 0.25, 'edgecolors': 'white'}

    # These get unpacked upon calling plot_scatter
    diff = diff.rename(columns={'income_class': 'Income class'})
    plot_scatter(diff, x='diff_abx', y='diff_ghg', size=5,
                 x_min=-40, x_max=40, y_min=-4, y_max=4,
                 x_label=X_LABEL, y_label=Y_LABEL,
                 legend=False,
                 scatter_kwargs = scatter_kwargs)

    show_save_plot(show=SHOW_FIGS, path=FILE_PATH, filename='abx_ghg_scatter_all_scenarios_abs_diff',
                   format=FIG_FORMAT)

# Main method
def figs_diet_shifts_income():

    # Input ************************************************************************************************************

    # Diet footprints
    fp_cols = ['country_code', 'country', 'income_class', 'diet', 'attribute', 'value', 'value_baseline']
    fp = pd.read_csv(paths.output / 'diet_footprints_by_country_diet.csv')[fp_cols]

    diet_names = pd.read_csv(paths.input / 'figures/diet_names_sort_order_all.csv')

    population = pd.read_csv(paths.interim / 'fao_population.csv')

    income_reclassification = pd.read_csv(paths.input / 'figures/income_reclassification.csv')

    global income_colors
    income_colors = pd.read_csv(paths.input / 'figures/income_class_order_color.csv') \
        [['income_class', 'color_ghg']].set_index('income_class').T.to_dict('records')[0]

    # hue_order determines order in which each series is displayed in the legend
    global income_order
    income_order = pd.read_csv(paths.input / 'figures/income_class_order_color.csv')['income_class'].to_list()

    # Prep *************************************************************************************************************

    # Set font
    font = {'family': 'Arial',
            'size': 6.15}
    matplotlib.rc('font', **font)

    # Prep data
    # TODO: NOTE CHANGE IN UNITS FROM MG TO G ANTIBIOTICS, KG TO MT CO2E
    (abx, ghg) = prep_abx_ghg(fp, diet_names, income_reclassification, population)

    # Compute % diff in footprints from diet shifts
    diff = prep_diff(abx, ghg)

    # Make a version with LMICs only and just the US
    diff_lmic = s_filter(diff, col='income_class', excl_list=['High income'])
    diff_us_lmic = s_filter(diff, col='country', list=['United States of America'])
    diff_us_lmic = pd.concat([diff_lmic, diff_us_lmic])

    # Plot
    plot_diets(abx, ghg)
    plot_diff(diff, 'EAT-Lancet', x_max=250, y_max=250, label_dots=['India',  'Nigeria', 'Bangladesh', 'Brazil'], clip_on=True)
    plot_diff(diff, 'High income', x_min=-80, x_max=20, y_min=-40, y_max=60, label_dots=['India', 'Nigeria', 'Bangladesh', 'Brazil'], clip_on=True)

    """
    # LMICs only
    lmic = s_filter(diff, col='income_class', list=['Low income / unclassified', 'Lower middle income'])

    plot_diff(lmic, 'EAT-Lancet', x_max=250, y_max=250, label_dots=['India', 'Indonesia', 'Pakistan', 'Nigeria', 'Bangladesh', 'Ethiopia'], file_suffix='_lmic')
    plot_diff(lmic, 'High income diet', x_max=850, y_max=850, label_dots=['India', 'Indonesia', 'Pakistan', 'Nigeria', 'Bangladesh', 'Ethiopia'], file_suffix='_lmic')
    plot_diff(lmic, 'Extensive monogastrics', x_min=-70, x_max=10, y_min=-20, y_max=60, label_dots=[], file_suffix='_lmic')
    """