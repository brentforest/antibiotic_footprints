import numpy as np
import pandas as pd
import winsound
from utilities import *
pd.options.display.width = 250


def apply_regional_global_wavg(fp, prod, countries):
# Creates every item-footprint_type-country permutation,
# and assigns a country, regional, or global average footprint
# depending on the resolution of data available.

# Note the "source" column gets dropped in this step.
# At one point it was nice being able to show the source for each item-footprint_type pair,
# but once we started using data with multiple sources for the same pair,
# we run the risk of introducing duplicate indices.

    print('Generating footprints for all countries and applying regional/global averages')

    # Filter df columns
    # If region not included in footprint data, add it:
    countries = countries[['country_code', 'country', 'gleam_region']]
    prod = prod[['country_code', 'fbs_item_code', 'mt_production']]
    if 'gleam_region' not in fp.columns:
        fp = s_merge(fp, countries, on=['country_code', 'country'], how='left')
    fp = fp[['fbs_item_code', 'fbs_item', 'country_code', 'country', 'gleam_region',
             'footprint_type', 'footprint']]

    # Merge fbs item production (used for weighted avg)
    # If there are no production data for an item, assume production=0
    fp = fp.merge(prod, on=['country_code', 'fbs_item_code'], how='left')
    fp['mt_production'] = fp['mt_production'].fillna(0)

    # Make a copy for country footprints
    # Compute regional and world avg footprints, weighted by country production
    # Note: this step includes zero footprint values in averages
    country_cols = ['country_code', 'country', 'fbs_item_code', 'fbs_item', 'footprint_type']
    region_cols = ['gleam_region', 'fbs_item_code', 'fbs_item', 'footprint_type']
    world_cols = ['fbs_item_code', 'fbs_item', 'footprint_type']

    fp_country = fp[country_cols + ['footprint']]\
        .rename(columns = {'footprint': 'country_footprint'})

    # Check for duplicate indices; each country-item-footprint_type trio should be unique
    check_duplicate_indices(fp_country, country_cols)

    # LUC footprints do not use region/world averages, because if there is no country footprint, assume footprint == 0
    fp_not_luc = s_filter(fp, col='footprint_type', excl_str='luc_')

    fp_region = fp_not_luc\
        .groupby(region_cols).apply(wavg, 'footprint', 'mt_production')\
        .rename('region_footprint').reset_index()

    fp_world = fp_not_luc\
        .groupby(world_cols).apply(wavg, 'footprint', 'mt_production')\
        .rename('world_footprint').reset_index()

    # Get a list of unique fbs items and associated valid footprint types.
    fp = fp[['fbs_item_code', 'fbs_item', 'footprint_type']].drop_duplicates()

    # Compute cartesian product of every possible country-item-footprint type trio.
    # Dropping duplicates gives us every item-footprint type pair (without countries).
    fp['merge_dummy_var'] = 1
    countries['merge_dummy_var'] = 1
    fp = fp.merge(countries, on='merge_dummy_var', how='outer').drop(columns='merge_dummy_var')

    # Merge country, region, and world footprints
    fp = fp\
        .merge(fp_country, on=country_cols, how='left')\
        .merge(fp_region, on=region_cols, how='left')\
        .merge(fp_world, on=world_cols, how='left')

    # If a country-item has no matching LUC footprint data, set footprint to 0.
    conds = fp['footprint_type'].str.contains('luc_', case=False)
    fp.loc[conds, 'country_footprint'] = fp.loc[conds, 'country_footprint'].fillna(0)

    # if country footprint exists, use that;
    # if region footprint exists, use that instead;
    # otherwise use world footprint as default.
    conds = [fp['country_footprint'].notnull(), fp['region_footprint'].notnull()]
    choices = [fp['country_footprint'], fp['region_footprint']]
    fp['footprint'] = np.select(conds, choices, default=fp['world_footprint'])
    fp['geographic_resolution'] = np.select(conds, ['country', 'region'], default='world')

    return fp


def combine_footprint_types(fp, index_cols, results_cols, keep_originals):
# Sum footprint types (e.g., blue WF + pond blue WF, GHG + LUC GHG)
# This function may be called more than once, e.g., in item_footprints_by_coo and again in results_combine
# so we exclude totals to make sure it doesn't end up double-counting anything.
# TODO: Adding logic should handle centiles and real values being added together (<- BK forgot what this means)

    # Combine GHG footprints
    fp_ghg = s_filter(fp, col='footprint_type', substring='co2', excl_str='total')
    print('\nCombining footprint types: ', fp_ghg['footprint_type'].unique())
    fp_ghg = fp_ghg.groupby(index_cols)[results_cols].sum().reset_index()
    fp_ghg['footprint_type'] = 'kg_co2e_total'

    # Combine abx footprints
    fp_abx = s_filter(fp, col='footprint_type', substring='abx', excl_str='total')
    print('\nCombining footprint types: ', fp_abx['footprint_type'].unique())
    fp_abx = fp_abx.groupby(index_cols)[results_cols].sum().reset_index()
    fp_abx['footprint_type'] = 'mg_abx_total'

    fp_grouped = pd.concat([fp_ghg, fp_abx], sort=False)

    if keep_originals:

        # Remove grouped footprints from original fp;
        # this prevents duplicate rows in case fp had already been grouped before
        fp = s_filter(fp, col='footprint_type', excl_str='total')
        return pd.concat([fp, fp_grouped], sort=False)

    else:
        return fp_grouped

