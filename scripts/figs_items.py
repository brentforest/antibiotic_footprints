import numpy as np
import pandas as pd
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
OUTPUT_PATH = '../figures/item_footprints/'
ORDER = ['Sheep & goat', 'Pig meat',  'Bovine meat', 'Aquatic animals', 'Poultry meat','Crops']
BKO_ORDER = ['Pigmeat, intensive',  'Pigmeat, extensive', 'Poultry Meat, intensive','Poultry Meat, extensive']

def prep_abx(abx_meat, abx_aqua, abx_crops, abx_groups_drug):

    # We use item index as a standardized way to differentiate each dot in the plot,
    # e.g., for terrestrial meat the index is country, but for aquaculture it is the item.

    # Define items and item indices:
    abx_meat = abx_meat.rename(columns={'country': 'item_index', 'fbs_item': 'item'})

    abx_crops = s_filter(abx_crops, col='country', list=['United States of America', 'India'])
    abx_crops['footprint_type'] = 'mg_abx_' + abx_crops['footprint_type']
    abx_crops['item_index'] = abx_crops['country'] + '_' + abx_crops['crop']
    abx_crops['item'] = 'Crops'

    abx_aqua = abx_aqua.rename(columns={'schar_item': 'item_index'})
    abx_aqua['item'] = 'Aquatic animals'

    # Concat
    abx = pd.concat([abx_meat, abx_aqua, abx_crops], sort=False)

    # Reclassify and group by drug
    abx = classify_group_abx(abx, abx_groups_drug, ['item_index', 'item', 'footprint_type']) \
        .groupby(['item_index', 'item'])['footprint'].sum().reset_index()

    abx['footprint_type'] = 'mg_abx'

    abx.to_csv(paths.diagnostic / 'abx/abx_item_strip_plot_data.csv', index=False)

    return abx


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


def prep_abx_bko(bko_abx_meat, abx_groups_drug):

    bko_abx_meat = s_filter(bko_abx_meat, col='system', list=['extensive', 'intensive'])

    bko_abx_meat['item'] = bko_abx_meat['fbs_item'] + ', ' + bko_abx_meat['system']

    # Define items and item indices:
    bko_abx_meat = bko_abx_meat.rename(columns={'country_iso_code': 'item_index', 'mg/kg_cw': 'footprint'})

    # Reclassify and group by drug, filter to MI drugs only
    bko_abx_meat = classify_group_abx(bko_abx_meat, abx_groups_drug, ['item_index', 'item', 'footprint_type']) \
        .groupby(['item_index', 'item'])['footprint'].sum().reset_index()

    bko_abx_meat['footprint_type'] = 'mg_abx_bko'

    bko_abx_meat.to_csv(paths.diagnostic / 'abx/abx_item_strip_plot_data_bko.csv', index=False)

    return bko_abx_meat


def prep_ghg_bko(ghg_bko):

    # Filter, sum over footprint types, merge w/production data
    ghg_bko = s_filter(ghg_bko, col='fbs_item', list=['Pigmeat', 'Poultry Meat']) \
            .pipe(s_filter, col='system', list=['intensive', 'extensive']) \
            .groupby(['country', 'system', 'fbs_item'])['footprint'].sum().reset_index()

    ghg_bko['item'] = ghg_bko['fbs_item'] + ', ' + ghg_bko['system']
    ghg_bko['footprint_type'] = 'kg_co2e_bko'
    ghg_bko = ghg_bko[['item', 'country', 'footprint_type', 'footprint']].rename(columns={'country': 'item_index'})

    return ghg_bko



# Main method
def figs_items():

    # Input ************************************************************************************************************

    # Aquaculture and crop data undergo numerous adaptations, e.g., to FBS items;
    # strip plots reflect source data for these foods, prior to adaptation
    abx_meat = pd.read_csv(paths.interim / 'item_footprints/item_footprints_abx_meat.csv')
    abx_aqua = pd.read_csv(paths.interim / 'item_footprints/item_footprints_abx_aqua_by_schar_item.csv')
    abx_crops = pd.read_csv(paths.interim / 'item_footprints/item_footprints_abx_crops_by_crop.csv')

    abx_groups_drug = pd.read_excel(paths.input / 'antibiotic_use/abu_classifications.xlsx', sheet_name='drug_classes', skiprows=3)[
        ['footprint_type', 'footprint_type_reclassified']]

    # item names
    item_names = pd.read_csv(paths.input / 'figures/item_names.csv')

    # GHGe footprints, for side-by-side comparisons
    ghg_gleam = pd.read_csv(paths.interim / 'item_footprints/item_footprints_gleam.csv')
    ghg_coo = pd.read_csv(paths.interim / 'item_footprints/item_footprints_by_coo.csv')
    ghg_dist = pd.read_excel(paths.input / 'ghge/ghge_lit_review_distributions.xlsx', sheet_name='ghge_combined', skiprows=3)

    # Abx broken out by system / source
    abx_bko_meat = pd.read_csv(paths.interim / 'item_footprints/item_footprints_abx_meat_by_system.csv')

    # GHGe broken out by system
    ghg_bko = pd.read_csv(paths.interim / 'item_footprints/item_footprints_gleam_by_system.csv')

    # Carcass to edible weight conversions
    edible_wt = pd.read_csv(paths.input / 'edible_wt_factors.csv')[['item', 'edible_fraction']]

    # Prep *************************************************************************************************************

    # Set font
    font = {'family': 'Arial',
            'size': 6.15}
    matplotlib.rc('font', **font)

    # prep abx, ghg, abx broken out by source
    abx = prep_abx(abx_meat, abx_aqua, abx_crops, abx_groups_drug)
    ghg = prep_ghg(ghg_gleam, ghg_coo, ghg_dist)
    abx_bko = prep_abx_bko(abx_bko_meat, abx_groups_drug)
    ghg_bko = prep_ghg_bko(ghg_bko)

    # concat
    fp = pd.concat([abx, ghg], sort=False)
    bko = pd.concat([abx_bko, ghg_bko], sort=False)

    # adjust carcass weight to edible weight
    fp = s_merge(fp, edible_wt, on='item', how='left', validate='m:1')
    fp['footprint'] /= fp['edible_fraction']
    bko = s_merge(bko, edible_wt, on='item', how='left', validate='m:1')
    bko['footprint'] /= bko['edible_fraction']

    # Rename items
    fp = s_merge_rename(fp, item_names, col='item', new_name_col='item_renamed')

    # Compute medians
    fp['median'] = fp.groupby(['item', 'footprint_type'])['footprint'].transform('median')
    bko['median'] = bko.groupby(['item', 'footprint_type'])['footprint'].transform('median')

    # Sort
    fp = s_categorical_sort(fp, col='item', sort_order=ORDER)
    bko = s_categorical_sort(bko, col='item', sort_order=BKO_ORDER)

    # Output files BEFORE formatting item name
    fp.to_csv('../data/output/per_kg_edible_wt_footprints_by_species.csv', index=False)
    bko.to_csv('../data/output/per_kg_edible_wt_footprints_by_species_system.csv', index=False)

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
    #plot_strip_items(fp, hue='footprint_type', palette=['silver', 'orange'], y_max=600)
    #show_save_plot(show=SHOW_FIGS, path=OUTPUT_PATH, filename='abx_item_strip_plot_combo_strip_plot')

    plot_strip_items(s_filter(fp, col='footprint_type', list=['mg_abx']), color='orange', y_label='mg antibiotics per kg food')
    show_save_plot(show=SHOW_FIGS, path=OUTPUT_PATH, format=['png', 'pdf'], filename='abx_item_strip_plot_w_outliers')

    plot_strip_items(s_filter(fp, col='footprint_type', list=['mg_abx']), color='orange', y_label='mg antibiotics per kg food', y_max=990)
    show_save_plot(show=SHOW_FIGS, path=OUTPUT_PATH, format=['png', 'pdf'], filename='abx_item_strip_plot')

    plot_strip_items(s_filter(fp, col='footprint_type', list=['kg_co2e']), color='lightcoral', y_label='kg CO2e per kg food', y_max=188)
    show_save_plot(show=SHOW_FIGS, path=OUTPUT_PATH, format=['png', 'pdf'], filename='abx_item_strip_plot_ghg')

    # Break out by source
    plot_strip_items(s_filter(bko, col='footprint_type', list=['mg_abx_bko']), color='orange', y_label='mg antibiotics per kg food')
    show_save_plot(show=SHOW_FIGS, path=OUTPUT_PATH, format=['png', 'pdf'], filename='abx_item_strip_plot_abx_bko_w_outliers')

    plot_strip_items(s_filter(bko, col='footprint_type', list=['mg_abx_bko']), color='orange', y_label='mg antibiotics per kg food', y_max=715)
    show_save_plot(show=SHOW_FIGS, path=OUTPUT_PATH, format=['png', 'pdf'], filename='abx_item_strip_plot_abx_bko')

    plot_strip_items(s_filter(bko, col='footprint_type', list=['kg_co2e_bko']), color='lightcoral', y_label='kg CO2e per kg food', y_max=27)
    show_save_plot(show=SHOW_FIGS, path=OUTPUT_PATH, format=['png', 'pdf'], filename='abx_item_strip_plot_ghg_bko')