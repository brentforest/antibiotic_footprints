import numpy as np
import pandas as pd
import math
import paths
import winsound
from utilities_figs import *
from utilities import *
from utilities_figs import *
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.transforms as mtrans
import matplotlib.patches as mpatches
from pandas.api.types import CategoricalDtype

pd.options.display.max_columns = 999
pd.options.mode.chained_assignment = None

# If SHOW_FIGS == False, figs fig data are saved
SHOW_FIGS = False
FILE_PATH = '../figures/diets_by_food/'
DIETS = ['Baseline', 'High income', 'EAT-Lancet']

def prep_abx_ghg(fp, dm, diet_names, food_groups, food_order, population):

    fp = pd.concat([fp, dm], sort=False)

    # A few (3?) countries probably don't have any pork production, so scaling up pigmeat to replace bovine
    # results in an footprint of infinity.
    fp = s_filter(fp, col='value', excl_list=[np.inf])

    # Rename diets; filter; groupby
    fp = s_merge_rename(fp, diet_names, col='diet') \
        .pipe(s_filter, col='diet', list=DIETS) \
        .pipe(s_filter, col='attribute', list=['mg_abx_total', 'kg_co2e_total', 'loss_adj_kcal/cap/day']) \
        .pipe(s_merge, food_groups, on='output_group', how='left') \
        .groupby(['country_code', 'country', 'diet', 'attribute', 'food_group'])['value'].sum().reset_index() \
        .pipe(s_merge, population, on=['country_code', 'country'], how='left', validate='m:1')

    # compute country population totals
    fp['value_pop_total'] = fp['value'] * fp['population']

    # sum global total
    fp = fp.groupby(['diet', 'attribute', 'food_group'])[['value_pop_total', 'population']].sum().reset_index()

    # Adjust units:
    # abx: mg to 1000 mt
    # ghg: kg to GT
    # kcal: global avg
    # We have to get population from FP; if we get it from population it includes duplicate countries (e.g., china / mainland china)
    global_population = fp['population'][0]
    fp['value_pop_total'] = np.where(fp['attribute'] == 'loss_adj_kcal/cap/day',
                                     fp['value_pop_total'] / global_population,
                                     fp['value_pop_total'] / 1000000000000)

   # Pivot so each food is a column
    fp = s_pivot(fp, idx=['diet', 'attribute'],  cols=['food_group'], vals='value_pop_total') \
        .pipe(s_categorical_sort, col='diet', sort_order=DIETS)

    # reorder food columns
    fp = fp[['diet', 'attribute'] + food_order]

    abx = s_filter(fp, col='attribute', list=['mg_abx_total'])
    ghg = s_filter(fp, col='attribute', list=['kg_co2e_total'])
    kcal = s_filter(fp, col='attribute', list=['loss_adj_kcal/cap/day'])

    return (abx, ghg, kcal)


def plot_diets(abx, ghg, dm, food_colors):

    # Plot the things
    kwargs = {'bottom': 0.28, 'show_figs': SHOW_FIGS, 'file_path': FILE_PATH, 'edgecolor':None}

    plot_bar(abx, x='diet', colors=food_colors, width=1.8, height=2.8, left=.25, right=0.98, stacked=True,  ylabel='1,000 mt antibiotics / year',
             legend=False, filename='abx_global', **kwargs)
    plot_bar(ghg, x='diet', colors=food_colors, width=1.8, height=2.8, left=.25,right=0.98,stacked=True, ylabel='GT CO2e / year',
               legend=False, filename='ghg_global', **kwargs)
    plot_bar(dm, x='diet', colors=food_colors, width=1.8, height=2.8, left=.25,right=0.98, stacked=True,
             ylabel='Average kcal / capita / day',
             legend=False, filename='kcal_global', **kwargs)

    #plot, x = 'country', y_label = 'kcal/capita/day', colors = food_colors_all, filename = 'kcal_per_cap_by_food')


# Main method
def figs_diets_by_food():

    # Input ************************************************************************************************************

    # Diet footprints
    fp_cols = ['country_code', 'country', 'diet', 'output_group', 'attribute', 'value']
    fp = pd.read_csv(paths.output / 'diet_footprints_by_country_diet_food_group.csv')[fp_cols]
    dm = pd.read_csv(paths.output / 'diet_model_by_country_diet_output_group.csv')

    diet_names = pd.read_csv(paths.input / 'figures/diet_names_sort_order_all.csv')
    population = pd.read_csv(paths.interim / 'fao_population.csv')

    food_groups = pd.read_csv(paths.input / 'figures/food_groups.csv')
    food_order = pd.read_csv(paths.input / 'figures/food_groups_all_order_colors.csv')['food_group'].tolist()
    food_colors = pd.read_csv(paths.input / 'figures/food_groups_all_order_colors.csv')['color'].tolist()


    # Prep *************************************************************************************************************

    # Set font
    font = {'family': 'Arial',
            'size': 6.15}
    matplotlib.rc('font', **font)

    # Prep data
    (abx, ghg, dm) = prep_abx_ghg(fp, dm, diet_names, food_groups, food_order, population)

    # Plot
    plot_diets(abx, ghg, dm, food_colors)

