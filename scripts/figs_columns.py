import numpy as np
import pandas as pd
import math
import paths
import winsound
from datetime import datetime
from utilities import *
from utilities_figs import *

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.transforms as mtrans
import matplotlib.patches as mpatches
from pandas.api.types import CategoricalDtype

pd.options.display.max_columns = 999
pd.options.mode.chained_assignment = None

MIN_POPULATION = 5000000
KWARGS = {'show_figs': False, 'file_path':'../figures/'}
MI_COLORS = ['#994f00', '#cc7700', '#ffa500', '#ffd27f']
WIDTH = 4.1
PCT_CUTOFF = 0.885

def get_filter_sort_list(df, idx, col, pct, return_df=False):
# Takes long-form dataframe, groups by index, returns a list of filtered and sorted indices.
# The list can then be applied to a categorical sort, e.g., after pivoting a df to wide form for plotting.
# This allows us the flexibility to save and re-use the same list across multiple plots,
# e.g., abx footprint by food group can use countries sorted by critically important footprint.

    # Make a copy before filtering and sorting,
    # in case we want to return the filtered df instead of just the list of indices
    # Group by index
    fs = df.copy().groupby(idx)[col].sum().reset_index()

    # Filter out values below given percentile
    fs = s_filter_percentile(fs, col=col, pct=pct)

    # Sort
    fs = fs.sort_values(by=col, ascending=False)
    fs_list = fs[idx].tolist()

    if return_df:
        # Return filtered and sorted dataframe
        return s_filter(df, col=idx, list=fs_list)\
            .pipe(s_categorical_sort, col=idx, sort_order=fs_list)
    else:
        # Return list of indices
        return fs_list


def prep_inputs(dm, fp, supply, country_names, who_groups_mi):

    # Adjust units
    fp['diet_footprint'] /= 1000  # grams
    fp['diet_footprint_whole_pop'] /= 1000000000000  # 1000 mt

    # Apply shorter country names; alert set to false since new names only apply to a small set of countries
    dm = s_merge_rename(dm, country_names, col='country', alert=False)
    supply = s_merge_rename(supply, country_names, col='country', alert=False)
    fp = s_merge_rename(fp, country_names, col='country', alert=False)

    # Filter to abx, baseline only
    fp = fp.pipe(s_filter, col='diet', list=['baseline']) \
        .pipe(s_filter, col='footprint_type', substring='mg_abx_')

    # By MI
    # Group by importance (summing over food items, origins)
    fp_mi = s_filter(fp, col='footprint_type', excl_str='_total') \
        .pipe(s_merge, who_groups_mi, how='left', on='footprint_type') \
        .groupby(['country', 'mi', 'income_class'])[['diet_footprint', 'diet_footprint_whole_pop']].sum().reset_index()
    fp_mi['mi'] = fp_mi['mi'].str.replace('_', ' ').str.capitalize().str.replace(' important', '\nimportant')

    # all abx total
    fp = s_filter(fp, col='footprint_type', list=['mg_abx_total'])

    fp.to_csv('../figures/baseline_per_cap/baseline_per_cap.csv', index=False)
    fp_mi.to_csv('../figures/baseline_per_cap/baseline_per_cap_mi.csv', index=False)

    return (dm, supply, fp, fp_mi)


def pivot_filter_sort(df, cols, vals, idx_list, idx='', idx_pivot='', idx_sort_filter='', col_sort=[]):
# Pivot, filter, sort, plot

    # In some cases we may want a separate index for sorting and filtering vs. pivoting,
    # e.g., [country, diet] as the index for pivoting but just [country] for filtering and sorting
    if idx_pivot=='':
        idx_pivot=idx
    if idx_sort_filter=='':
        idx_sort_filter=idx

    df = s_pivot(df, idx=idx_pivot, cols=cols, vals=vals)\
        .pipe(s_filter, col=idx_sort_filter, list=idx_list)\
        .pipe(s_categorical_sort, col=idx_sort_filter, sort_order=idx_list)

    # Sort columns L-R (these become stacked bars in figures)
    if len(col_sort) > 0:
        if isinstance(idx_pivot, str): idx_pivot = [idx_pivot]  # If index is a string, make it a list so it can be combined w/col_order
        old_cols = df.columns.tolist()
        new_cols = idx_pivot + col_sort

        # Alert on mismatch between new and old columns - this could cause information to be lost
        if set(old_cols) != set(new_cols):
            print('ALERT: Missing/extra column found when sorting. Original columns:', old_cols)
            print('New columns:',new_cols)
            winsound.Beep(400,400)

            # Drop new cols that aren't in old cols
            new_cols = [c for c in new_cols if c in old_cols]

        df = df[new_cols]

    return df


# **********************************************************************************************************************
# Prep data for plotting

def plot_baseline_fp_per_cap(fp, fp_mi, dm):

    # filter out countries below population treshhold
    country_list = get_filter_sort_list(
        fp.groupby(['country'])['diet_footprint'].sum().reset_index(),
        idx='country', col='diet_footprint', pct=PCT_CUTOFF)

    # filter countries
    fp = s_filter(fp, col='country', list=country_list)
    fp_mi = s_filter(fp_mi, col='country', list=country_list)

    fp.to_csv('../figures/baseline_per_cap/baseline_per_cap_filtered.csv', index=False)
    fp_mi.to_csv('../figures/baseline_per_cap/baseline_per_cap_mi_filtered.csv', index=False)

    # by MI
    pivot_filter_sort(fp_mi, idx='country', cols='mi', vals='diet_footprint',
                      idx_list=country_list, col_sort=['Critically\nimportant', 'Highly\nimportant', 'Important', 'Others']) \
        .pipe(plot_bar, x='country', ylabel='Grams antibiotics per capita/year', colors=MI_COLORS, width=WIDTH, x_rotate_degrees=60,x_shift=3,
              filename='baseline_per_cap/abx_baseline_per_cap_mi', **KWARGS)

    # by food group
    fp_g = fp.copy().pipe(s_merge, food_groups, on='output_group', how='left', validate='m:1')\
        .groupby(['country', 'food_group'])[['diet_footprint', 'diet_footprint_whole_pop']].sum().reset_index()
    pivot_filter_sort(fp_g, idx='country', cols='food_group', vals='diet_footprint',
                      idx_list=country_list, col_sort=food_order_abx) \
        .pipe(plot_bar, x='country', ylabel='Grams antibiotics per capita/year', colors=food_colors_abx, width=WIDTH,x_rotate_degrees=60,x_shift=3,
               filename='baseline_per_cap/abx_baseline_per_cap_by_food', **KWARGS)

    # Group by origin
    fp_o = fp.copy().groupby(['country', 'origin'])[['diet_footprint', 'diet_footprint_whole_pop']].sum().reset_index()
    fp_o['origin'] = fp_o['origin'].str.title()
    pivot_filter_sort(fp_o, idx='country', cols='origin', vals='diet_footprint',
                      idx_list=country_list) \
        .pipe(plot_bar, x='country', ylabel='Grams antibiotics per capita/year', colors=['#cc7700', '#ffd27f'],width=WIDTH,x_rotate_degrees=60,x_shift=3,
              filename='baseline_per_cap/abx_baseline_per_cap_by_origin', **KWARGS)

    # Plot kcal
    # Filter, merge and group by food groups
    dm = s_filter(dm, col='diet', list=['baseline'])\
        .pipe(s_filter, col='attribute', list=['loss_adj_kcal/cap/day'])\
        .pipe(s_merge, food_groups, on='output_group', how='left')\
        .groupby(['country', 'food_group'])['value'].sum().reset_index()

    pivot_filter_sort(dm, idx='country', cols='food_group', vals='value',
                      idx_list=country_list, col_sort=food_order_all) \
        .pipe(plot_bar, x='country', ylabel='kcal/capita/day', colors=food_colors_all, width=WIDTH,x_rotate_degrees=60,x_shift=3,
              filename='baseline_per_cap/kcal_per_cap_by_food', **KWARGS)


def plot_baseline_fp_per_cap_by_whole_country(fp, fp_mi, dm):
# Plot per capita footprints, ranked by whole country footprints

    # filter out countries below population treshhold
    country_list = get_filter_sort_list(
        fp.groupby(['country'])['diet_footprint_whole_pop'].sum().reset_index(),
        idx='country', col='diet_footprint_whole_pop', pct=PCT_CUTOFF)

    print(country_list)

    # filter countries
    fp = s_filter(fp, col='country', list=country_list)
    fp_mi = s_filter(fp_mi, col='country', list=country_list)

    fp.to_csv('../figures/baseline_per_cap/baseline_per_cap_filtered_wc.csv', index=False)
    fp_mi.to_csv('../figures/baseline_per_cap/baseline_per_cap_mi_filtered_wc.csv', index=False)

    # by MI
    pivot_filter_sort(fp_mi, idx='country', cols='mi', vals='diet_footprint',
                      idx_list=country_list, col_sort=['Critically\nimportant', 'Highly\nimportant', 'Important', 'Others']) \
        .pipe(plot_bar, x='country', ylabel='Grams antibiotics per capita/year', colors=MI_COLORS, width=WIDTH, x_rotate_degrees=60,x_shift=3,
              filename='baseline_per_cap/abx_baseline_per_cap_by_wc_mi', **KWARGS)

    # by food group
    fp_g = fp.copy().pipe(s_merge, food_groups, on='output_group', how='left', validate='m:1')\
        .groupby(['country', 'food_group'])[['diet_footprint', 'diet_footprint_whole_pop']].sum().reset_index()
    pivot_filter_sort(fp_g, idx='country', cols='food_group', vals='diet_footprint',
                      idx_list=country_list, col_sort=food_order_abx) \
        .pipe(plot_bar, x='country', ylabel='Grams antibiotics per capita/year', colors=food_colors_abx, width=WIDTH,x_rotate_degrees=60,x_shift=3,
               filename='baseline_per_cap/abx_baseline_per_cap_by_wc_food', **KWARGS)

    # Group by origin
    fp_o = fp.copy().groupby(['country', 'origin'])[['diet_footprint']].sum().reset_index()
    fp_o['origin'] = fp_o['origin'].str.title()
    pivot_filter_sort(fp_o, idx='country', cols='origin', vals='diet_footprint',
                      idx_list=country_list) \
        .pipe(plot_bar, x='country', ylabel='Grams antibiotics per capita/year', colors=['#cc7700', '#ffd27f'],width=WIDTH,x_rotate_degrees=60,x_shift=3,
              filename='baseline_per_cap/abx_baseline_per_cap_by_wc_origin', **KWARGS)

    # Plot kcal
    # Filter, merge and group by food groups
    dm = s_filter(dm, col='diet', list=['baseline']) \
        .pipe(s_filter, col='attribute', list=['loss_adj_kcal/cap/day']) \
        .pipe(s_merge, food_groups, on='output_group', how='left') \
        .groupby(['country', 'food_group'])['value'].sum().reset_index()

    pivot_filter_sort(dm, idx='country', cols='food_group', vals='value', idx_list=country_list, col_sort=food_order_all) \
        .pipe(plot_bar, x='country', ylabel='kcal/capita/day', colors=food_colors_all, width=WIDTH, x_rotate_degrees=60,
              x_shift=3, filename='baseline_per_cap/kcal_per_cap_wc_by_food', **KWARGS)


def plot_supply_demand(supply):

    # Filter and merge in WHO footprint names, food groups
    supply = s_filter(supply, col='footprint_type', substring='mg_abx_total_who')\
        .pipe(s_merge_rename, col='footprint_type', new_names=who_fp_types)\
        .pipe(s_merge, food_groups, on='output_group', how='left')

    # Convert to 1,000 metric tons
    results_cols = ['supply_side_domestic', 'supply_side_exports', 'demand_side_domestic_by_coo_only',
                    'demand_side_imported_by_coo_only']
    for c in results_cols:
        supply[c] /= 1000000000000

    ylabel = '1000 mt antimicrobials per year'

    # Group by country and footprint type
    index_cols = ['country_code', 'country', 'footprint_type']
    supply_who = supply.groupby(index_cols)[results_cols].sum().reset_index()

    # Get list of filtered and sorted countries
    countries_supply = s_filter(supply_who, col='footprint_type', list=who_important_fp_types)\
        .pipe(get_filter_sort_list, idx='country', col='supply_side_exports', pct=0.9)

    countries_demand = s_filter(supply_who, col='footprint_type', list=who_important_fp_types)\
        .pipe(get_filter_sort_list, idx='country', col='demand_side_imported_by_coo_only', pct=0.9)

    # Pivot, filter, sort, plot
    pivot_filter_sort(supply_who, idx='country', cols='footprint_type', vals='supply_side_exports',
                      idx_list=countries_supply, col_sort=who_order)\
        .pipe(plot_bar, x='country', ylabel=ylabel, colors=who_colors, filename='abx_supply_exports_who', **KWARGS)

    pivot_filter_sort(supply_who, idx='country', cols='footprint_type', vals='demand_side_imported_by_coo_only',
                      idx_list=countries_demand, col_sort=who_order)\
        .pipe(plot_bar, x='country', ylabel=ylabel, colors=who_colors, filename='abx_demand_imports_who', **KWARGS)

    # Group by food group, filter to important abx only
    supply_food = s_filter(supply, col='footprint_type', list=who_important_fp_types)\
        .groupby(['country_code', 'country', 'food_group'])[results_cols].sum().reset_index()

    # Plot using same list of countries as above
    pivot_filter_sort(supply_food, idx='country', cols='food_group', vals='supply_side_exports',
                      idx_list=countries_supply, col_sort=food_order_abx)\
        .pipe(plot_bar, x='country', ylabel=ylabel, colors=food_colors_abx, filename='abx_supply_exports_food', **KWARGS)

    pivot_filter_sort(supply_food, idx='country', cols='food_group', vals='demand_side_imported_by_coo_only',
                      idx_list=countries_demand, col_sort=food_order_abx)\
        .pipe(plot_bar, x='country', ylabel=ylabel, colors=food_colors_abx, filename='abx_demand_imports_food', **KWARGS)



# Main method
def figs_columns():

    # Input ************************************************************************************************************

    dm = pd.read_csv(paths.output / 'diet_model_by_country_diet_output_group.csv')
    fp = pd.read_csv(paths.output / 'by_coo_only/diet_footprints_by_origin_diet_item.csv')
    #ifp = pd.read_csv(paths.interim / 'item_footprints/item_footprints_abx_grouped.csv') unused
    supply = pd.read_csv(paths.output / 'by_coo_only/supply_side_footprints_by_country_item.csv')
    fpc = pd.read_csv(paths.output / 'by_coo_only/diet_footprints_by_coo_baseline_only.csv')

    country_names = pd.read_csv(paths.input / 'figures/country_short_names.csv')
    population = pd.read_csv(paths.interim / 'fao_population.csv')[['country_code', 'population']]

    global food_groups
    global food_order_abx
    global food_colors_abx
    global food_order_all
    global food_colors_all

    who_groups_mi = pd.read_excel(paths.input / 'antibiotic_use/abu_classifications.xlsx', sheet_name='medical_importance', skiprows=3)[
        ['footprint_type', 'mi']]

    food_groups = pd.read_csv(paths.input / 'figures/food_groups.csv')
    food_order_abx = pd.read_csv(paths.input / 'figures/food_groups_abx_order_colors.csv')['food_group'].tolist()
    food_colors_abx = pd.read_csv(paths.input / 'figures/food_groups_abx_order_colors.csv')['color'].tolist()
    food_order_all = pd.read_csv(paths.input / 'figures/food_groups_all_order_colors.csv')['food_group'].tolist()
    food_colors_all = pd.read_csv(paths.input / 'figures/food_groups_all_order_colors.csv')['color'].tolist()

    # ******************************************************************************************************************

    font = {'family': 'Arial',
            'size': 6.1}
    matplotlib.rc('font', **font)

    # for LMIC sub-analysis
    #fp = s_filter(fp, col='income_class', list=['Low income', 'Unclassified', 'Lower middle income'])
    #supply = s_filter(supply, col='income_class', list=['Low income', 'Unclassified', 'Lower middle income'])

    (dm, supply, fp, fp_mi) = prep_inputs(dm, fp, supply, country_names, who_groups_mi)

    plot_baseline_fp_per_cap(fp, fp_mi, dm)
    plot_baseline_fp_per_cap_by_whole_country(fp, fp_mi, dm)

    #plot_supply_demand(supply)
