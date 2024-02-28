import numpy as np
import pandas as pd
import gc # Garbage collection module, to save memory
import paths
import winsound
from datetime import datetime
from utilities import *
from utilities_diet_climate import *

pd.options.display.max_columns = 999
pd.options.mode.chained_assignment = None

COUNTRY_VARS = ['region', 'income_class', 'oecd']
OUTPUT_DETAILED_BY_COO = False

def compute_diet_footprints(dm, fp):

    # Merge diet model w/item footprint by coo, compute diet footprints
    # Only include country-item pairs with consumption data AND footprint data (inner merge)

    # If there isn't footprint data for a particular country-item pair, it doesn't get NAN or zero,
    # it just doesn't get a row in the long-form df (which is effectively footprint = 0).
    # We just have to be careful if we ever pivot by footprint type, because that could create NAN values.
    print('Merging diet model w/item footprints')
    fp.rename(columns={'country_code': 'coo_code', 'footprint': 'item_footprint_per_kg'}, inplace=True)
    fp = fp[['coo_code', 'fbs_item_code', 'fbs_item', 'footprint_type', 'item_footprint_per_kg']]
    fp = pd.merge(dm, fp, on=['coo_code', 'fbs_item', 'fbs_item_code'], how='inner', suffixes=('', '_x'))
    fp.drop(columns=list(fp.filter(regex='_x')), inplace=True)

    # Compute diet footprints
    print('Computing diet footprints\n')
    fp['diet_footprint'] = fp['kg/cap/yr_by_coo'] * fp['item_footprint_per_kg']

    # Collect unused memory since we no longer need dm
    del dm
    gc.collect()

    return fp


# Main method
def diet_footprints_by_coo():

    # Input ************************************************************************************************************

    dm = pd.read_csv(paths.output/'diet_model_by_country_diet_item_coo.csv')
    fp = pd.read_csv(paths.interim/'item_footprints/item_footprints_by_coo.csv')
    fp_int = pd.read_csv(paths.interim/'item_footprints/item_footprints_by_coo_intensive.csv')

    # For grouped files
    countries = pd.read_csv(paths.interim/'fao_countries.csv')[['country_code', 'country'] + COUNTRY_VARS]
    population = pd.read_csv(paths.interim / 'fao_population.csv')

    # Compute diet footprints ******************************************************************************************

    # For the high-income diet only, pig and poultry meat use intensive footprint data
    dm_int = s_filter(dm, col='diet', list=['high_income'])
    dm = s_filter(dm, col='diet', excl_list=['high_income'])

    #conds = (dm['diet']=='high_income') & (dm['fbs_item'].isin(['Pigmeat', 'Poultry Meat']))
    #dm.loc[conds, 'fbs_item'] += '_intensive'

    fp_int = compute_diet_footprints(dm_int, fp_int)
    fp = compute_diet_footprints(dm, fp)
    fp = pd.concat([fp, fp_int], sort=False)

    # Remove intermediate columns
    fp.drop(columns=['kg/cap/yr_by_coo'], inplace=True)

    # Add income and other country vars
    fp = s_merge(fp, countries, on=['country_code', 'country'], how='left', validate='m:1')

    # Output ***********************************************************************************************************

    # This file is too large for github so we can deactivate this option
    if OUTPUT_DETAILED_BY_COO:
        fp.to_csv(paths.output/'by_coo_only/diet_footprints_by_country_diet_item_coo.csv', index=False)

    # Further grouping *************************************************************************************************

    # Whole diet, baseline only, by coo
    # Optional to-do: add population data
    fp_by_diet = fp.copy()
    fp_by_diet = fp_by_diet[fp_by_diet['diet'] == 'baseline']
    index_cols = ['country_code', 'country', 'origin', 'coo_code', 'coo', 'diet', 'footprint_type'] + COUNTRY_VARS
    fp_by_diet = fp_by_diet.groupby(index_cols)['diet_footprint'].sum().reset_index()
    fp_by_diet.to_csv(paths.output / 'by_coo_only/diet_footprints_by_coo_baseline_only.csv', index=False)

    # By origin (domestic, imported) and item; w/population data
    fp_by_og = fp.copy()
    index_cols = ['country_code', 'country', 'origin', 'diet', 'type', 'output_group', 'fbs_item_code', 'fbs_item', 'footprint_type'] + COUNTRY_VARS
    fp_by_og = fp_by_og.groupby(index_cols)['diet_footprint'].sum().reset_index()

    fp_by_og = s_merge(fp_by_og, population, on=['country_code', 'country'], how='left', validate='m:1')
    fp_by_og['diet_footprint_whole_pop'] = fp_by_og['diet_footprint'] * fp_by_og['population']

    fp_by_og.to_csv(paths.output / 'by_coo_only/diet_footprints_by_origin_diet_item.csv', index=False)
