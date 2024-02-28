import pandas as pd
import numpy as np
import paths
from utilities import *


pd.options.display.width = 999
pd.options.display.max_columns = 999


def prep_gleam(gleam, gleam_col_match):

    # Replace NaN w/zero - for most GLEAM countries, zeroes are outputted, but several output #NA
    gleam['item'] = gleam['item'].fillna('All items')
    gleam.fillna(0, inplace=True)

    # Merge w/new column names and footprint type, drop rows w/no match
    gleam = gleam.merge(gleam_col_match, on='gleam_variable', how='left')
    gleam.drop(columns=['gleam_variable', 'unit'], inplace=True)
    gleam = gleam[gleam['attribute'].notnull()]

    # Unpivot country columns
    index_cols = ['species', 'system', 'item', 'attribute']
    gleam = gleam.melt(id_vars=index_cols, var_name='country', value_name='value')

    gleam.to_csv(paths.diagnostic / 'item_footprints_gleam_unpivot.csv', index=False)

    # Separate out and pivot footprint-type-specific data, specific to species and system but not item
    system_ghg = s_filter(gleam, col='attribute', substring='system_kg_co2') \
        .pipe(s_pivot, idx=['country', 'species', 'system'], cols=['attribute'], vals=['value'])

    # Add a row for non-LUC ghge, then unpivot back
    system_ghg['system_kg_co2e_excl_luc'] = system_ghg['system_kg_co2e_total'] \
                                            - system_ghg['system_kg_co2_luc_feed_soy'] \
                                            - system_ghg['system_kg_co2_luc_feed_palm'] \
                                            - system_ghg['system_kg_co2_luc_pasture']
    system_ghg = system_ghg.melt(id_vars=['country', 'species', 'system', 'system_kg_co2e_total'],
                                  var_name='footprint_type', value_name='system_ghg')

    # Compute %s allocated to each footprint type within each system
    system_ghg['system_ghg_%'] = system_ghg['system_ghg'] / system_ghg['system_kg_co2e_total']

    check_duplicate_indices(system_ghg, ['country', 'species', 'system', 'footprint_type'])

    # Separate out and pivot item-level data, i.e., footprints and production
    # Indexed by country, species, system, item
    gleam = s_filter(gleam, col='attribute', list=['kg_co2e/kg_protein', 'kg_protein/year', 'kg_primary/year']) \
        .pipe(s_pivot, ['country','species','system','item'], ['attribute'], ['value'])

    return [gleam, system_ghg]


def derive_item_footprints(gleam, derived, production):
# Offals, butter, and cream are not included in GLEAM-i
# Derive footprints of these items based on parent products

    derived = derived.merge(gleam.rename(columns={
        'fbs_item_code': 'parent_item_code',
        'fbs_item': 'parent_item',
        'footprint': 'parent_footprint'}),
        on=['parent_item_code', 'parent_item'], how='left')
    derived['footprint'] = derived['parent_footprint'] / derived['product_fraction'] * derived['value_fraction']


    """
    # Separate non-offal footprints
    cols = ['country_code', 'country', 'gleam_region', 'fbs_item_code', 'fbs_item', 'footprint_type', 'footprint']
    non_offals = derived[~derived['fbs_item'].isin(['Bovine offals', 'Swine offals'])][cols]


    # Offal footprint = avg of bovine and pig offals, weighed by country production of bovine and pig meat
    offals = derived[derived['fbs_item'].isin(['Bovine offals', 'Swine offals'])] \
        .merge(production, left_on=['country_code', 'parent_item_code'],
               right_on=['country_code', 'fbs_item_code'], how='left')
    offals = offals.groupby(['country_code', 'country', 'gleam_region', 'footprint_type'])\
        .apply(wavg, 'footprint', 'mt_production')\
        .rename('footprint').reset_index()
    offals['fbs_item_code'] = 2736
    offals['fbs_item'] = 'Offals, Edible'
    """

    # Concat derived footprints, drop NaN values
    cols = gleam.columns
    gleam = pd.concat([gleam, derived], sort=False)[cols]
    gleam = gleam[gleam['footprint'].notna()]
    return gleam


# Main method
def item_footprints_gleam(production_system='baseline'):

    # Input (don't covert gleam files to snake case - columns include country names)
    gleam = pd.read_csv(paths.input/'ghge/gleam/gleam_i_raw_output_v20_rev3c.csv')
    gleam_col_match = pd.read_csv(paths.input/'ghge/gleam/gleam_col_match.csv')
    gleam_item_match = pd.read_csv(paths.input/'ghge/gleam/gleam_item_match.csv')
    gleam_system_match = pd.read_csv(paths.input/'ghge/gleam/gleam_system_match.csv')
    derived = pd.read_csv(paths.input/'ghge/gleam/gleam_derived_items.csv')
    countries = (pd.read_csv(paths.interim/'fao_countries.csv')
        [['country', 'country_code', 'gleam_country', 'gleam_region']])
    production = (pd.read_csv(paths.interim/'fbs_item_production.csv')
        [['country_code', 'fbs_item_code', 'mt_production']])


    # *****************************************************************************************************************#

    # Pivot and separate out data for LUC co2 and all systems data
    [gleam, system_ghg] = prep_gleam(gleam, gleam_col_match)

    # Compute footprint by country, species, system, item
    # See changelog for additional details
    gleam['kg_co2e/kg_primary'] = gleam['kg_co2e/kg_protein'] * (gleam['kg_protein/year'] / gleam['kg_primary/year'])

    # Allocate total GHGe footprint over specific footprint types
    gleam = s_merge(gleam, system_ghg, on=['country', 'species', 'system'], how='left')
    gleam['footprint'] = gleam['kg_co2e/kg_primary'] * gleam['system_ghg_%']

    gleam['footprint_type'] = gleam['footprint_type'].str.replace('system_', '')

    # Match to fao countries, fbs items, and reclassified systems
    # Note a few small GLEAM countries don't have an fbs match
    gleam = gleam.rename(columns={'country': 'gleam_country'}) \
        .merge(countries, on='gleam_country', how='left') \
        .pipe(s_merge, gleam_item_match, on='item', how='left') \
        .pipe(s_merge, gleam_system_match, on='system', how='left', validate='m:1') \
        .rename(columns={'system': 'system_original', 'system_reclassified': 'system'})

    # Output intermediate results before grouping by fbs countries/items
    gleam.to_csv(paths.diagnostic/'item_footprints_gleam_items.csv', index=False)

    # Drop null footprints; these are for countries with no raw kg_co2e/kg_protein,
    # and in most cases (except for some small islands) no meat production.
    # This must be done before computing weighted averages.
    # We could instead replace nan with zero, but I suspect this would have a negligible effect on results,
    # since (except in rare cases) we're averaging results within the same country and item.
    gleam = gleam[~gleam['footprint'].isna()]

    # Group by country, item, system, footprint type; compute average footprint weighted by item production
    gleam = gleam.groupby(['country_code', 'country', 'gleam_region', 'fbs_item_code', 'fbs_item', 'system', 'footprint_type']) \
        .apply(wavg, 'footprint', weight_name='kg_primary/year').rename('footprint').reset_index()

    # Drop 0 values, mostly (exclusively?) applies to LUC footprints.
    # This is consistent with how we originally output GLEAM data, but it shouldn't make any difference either way,
    # since when we compute regional/global averages we first replace NAN LUC values with zero.
    # THIS MUST COME AFTER WAVG CALCULATIONS: When averaging intermediate and backyard pig production, for example,
    # intermediate might have LUC>0 while backyard LUC==0; if we drop the zeroes that skews the average high.
    gleam = gleam[gleam['footprint'] > 0]

    # Offals, butter, and cream are not included in GLEAM-i
    # Derive footprints of these special items based on parent products
    gleam = derive_item_footprints(gleam, derived, production)

    gleam['country_code'] = gleam['country_code'].astype(int)
    gleam['fbs_item_code'] = gleam['fbs_item_code'].astype(int)
    gleam['source'] = 'FAO, 2017. GLEAM-i v2.0 revision 3.'

    # Before filtering to particular systems, output a version w/all systems that could be used for plotting
    gleam.to_csv(paths.interim/'item_footprints/item_footprints_gleam_by_system.csv', index=False)

    # Filter pork and poultry to intensive/extensive if run parameters indicate:
    if production_system == 'intensive':
        print('Filtering GLEAM to intensive results only for pig and poultry meat')
        gleam_int = s_filter(gleam, col='system', list=['intensive']) \
            .pipe(s_filter, col='fbs_item', list=['Poultry Meat', 'Pigmeat'])
        gleam =  s_filter(gleam, col='system', list=['All systems']) \
            .pipe(s_filter, col='fbs_item', excl_list=['Poultry Meat', 'Pigmeat'])
        gleam = pd.concat([gleam, gleam_int], sort=False)
        #conds_int = (gleam['fbs_item'].isin(['Poultry Meat', 'Pigmeat'])) & (gleam['system']=='intensive')
        #gleam = gleam[conds_int]
        #gleam['fbs_item'] = gleam['fbs_item'] + '_intensive'
        gleam.to_csv(paths.interim / 'item_footprints/item_footprints_gleam_intensive.csv', index=False)

    else:
        gleam = s_filter(gleam, col='system', list=['All systems'])
        gleam.to_csv(paths.interim/'item_footprints/item_footprints_gleam.csv', index=False)
