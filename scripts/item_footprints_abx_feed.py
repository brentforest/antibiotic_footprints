import numpy as np
import pandas as pd
import gc # Garbage collection module, to save memory
import math
import paths
import winsound
from datetime import datetime
from utilities import *
from utilities_diet_climate import *
from item_footprints_abx_crops import apply_country_bans

pd.options.display.max_columns = 999
pd.options.mode.chained_assignment = None

def prep_gleam(gleam, gleam_fbs_match, countries):

    gleam_fbs_match = s_filter(gleam_fbs_match, col='item', substring='meat')

    # When merging GLEAM data with FAO countries, a few small countries do not have an FAO match,
    # so we don't use s_merge (to avoid an alert), this is ok.
    # Also note that some GLEAM countries (e.g., mainland China) match to multiple FAO countries (Mainland China, Taiwan).
    # In those cases, both FAO countries will use the same feed data, which is fine.
    # Especially since for our purposes we're only using GLEAM to give us the relative % allocation among species.
    gleam = s_filter(gleam, col='gleam_variable',
                     list=['INTAKE: Total intake - Grains', 'INTAKE: Total intake - Grains & Food crops']) \
        .pipe(s_filter, col='system', list=['All systems']) \
        .drop(columns=['item', 'system', 'gleam_variable', 'unit']) \
        .melt(id_vars='species', var_name='gleam_country', value_name='kg_feed_grains_dm/year') \
        .merge(countries, on='gleam_country', how='left', validate='m:m') \
        .pipe(s_merge, gleam_fbs_match, on='species', how='left')

    gleam = gleam[gleam['country'].notna()]

    # Groupby FBS item combines values for sheep and goat meat
    gleam = gleam.groupby(['country_code', 'country', 'gleam_region', 'fbs_item_code', 'fbs_item'])[
        'kg_feed_grains_dm/year'].sum().reset_index()

    # Compute % by FBS item
    gleam['total_feed_by_country'] = gleam.groupby(['country_code', 'country'])['kg_feed_grains_dm/year'].transform(
        'sum')

    # Some countries have zero feed, so a % allocation results in NAN
    gleam = gleam[gleam['total_feed_by_country'] > 0]

    gleam['feed_%_by_species'] = gleam['kg_feed_grains_dm/year'] / gleam['total_feed_by_country']

    return gleam


def add_pasture_fp(abx, pasture, bans, prod, countries):

    pasture['fbs_item'] = 'Bovine Meat'
    pasture['country'] = 'United States of America'
    pasture = s_filter(pasture, col='kg_abx/year', excl_list=[0])

    # Merge pasture abs use w/US beef production
    pasture = s_merge(pasture, prod, on=['country', 'fbs_item'], how='left')

    # Beef pasture fp = mg US abx use on pasture / kg US beef production
    pasture['mg_abx/yr'] = pasture['kg_abx/year'] * 1000000
    pasture['kg_production'] = pasture['mt_production'] * 1000
    pasture['footprint'] = pasture['mg_abx/yr'] / abx['kg_production']

    # Assign values to all countries
    pasture = apply_regional_global_wavg(pasture, prod, countries)

    # Assign footprint to zero where we know countries have banned certain drugs.
    pasture = apply_country_bans(pasture, bans)

    pasture['fcr'] = 999
    pasture['footprint_type'] = 'mg_abx_' + pasture['footprint_type'].astype(str)

    pasture.to_csv(paths.diagnostic/'abx/item_footprints_abx_pasture.csv', index=False)

    # Concat pasture beef fp onto abx
    abx = pd.concat([abx, pasture], sort=False)

    # Groupby, since beef has duplicate indices now
    abx = abx.groupby(['country_code', 'country', 'gleam_region', 'fbs_item_code', 'fbs_item', 'footprint_type']) \
                              ['footprint'].sum().reset_index()

    return abx


# Main method
def item_footprints_abx_feed():

    # Input ************************************************************************************************************

    fbs = pd.read_csv(paths.interim / 'fao_fbs_avg_loss_unadj.csv')[
        ['country_code', 'country', 'fbs_item_code', 'fbs_item', 'feed_1000_mt']]
    abx = pd.read_csv(paths.interim / 'item_footprints/item_footprints_abx_crops.csv')
    prod = pd.read_csv(paths.interim / 'fbs_item_production.csv')
    countries = (pd.read_csv(paths.interim/'fao_countries.csv')[
        ['country', 'country_code', 'gleam_country', 'gleam_region']])

    # gleam
    gleam = pd.read_csv(paths.input / 'ghge/gleam/gleam_i_raw_output_v20_rev3c.csv')
    gleam_fbs_match = pd.read_csv(paths.input / 'ghge/gleam/gleam_item_match.csv')

    # USGS data for pasture only
    pasture = pd.read_csv(paths.interim / 'item_footprints/item_footprints_abx_pasture.csv')
    bans = pd.read_excel(paths.input / 'antibiotic_use/abu_crops.xlsx', sheet_name='abu_crops_bans', skiprows=3)

    # *****************************************************************************************************************

    # Merge crop abx data by quantities used for feed
    # We only keep country-item pairs w/data for both abx and feed use (inner merge)
    abx = abx.merge(fbs, on=['fbs_item_code', 'fbs_item', 'country_code', 'country'], how='inner')

    # Compute total feed abx footprint by country:
    abx['feed_kg'] = abx['feed_1000_mt'] * 1000000
    abx['footprint_mg_country_total'] = abx['footprint'] * abx['feed_kg']

    abx.to_csv(paths.diagnostic/'abx/feed_footprints_raw.csv', index=False)

    # Sum abx footprints over all feed types.
    # We sum feed_kg too so we can get a feed conversion ratio, as an internal check
    abx = abx.groupby(['country_code', 'country', 'footprint_type'])[['footprint_mg_country_total', 'feed_kg']].sum().reset_index()

    # Compute % of each country's feed grain use by country and FBS meat item
    gleam = prep_gleam(gleam, gleam_fbs_match, countries)

    # Merge FBS with GLEAM so we can allocate feed use among species.
    # Only keep countries that have BOTH feed production data AND % by species (inner merge).
    # There are a few FBS countries that don't have a GLEAM match, so we don't use s_merge.
    # This is okay since missing countries will use regional/global averages, calculated in a separate script.
    abx = abx.merge(gleam, on=['country_code', 'country'], how='inner')

    # Allocate by species
    abx['footprint_mg_country_total'] *= abx['feed_%_by_species']
    abx['feed_kg'] *= abx['feed_%_by_species']

    # Merge and divide by meat production to get footprint
    abx = s_merge(abx, prod, on=['country_code', 'country', 'fbs_item_code', 'fbs_item'], how='left', validate='m:1')
    abx['kg_production'] = abx['mt_production'] * 1000
    abx['footprint'] = abx['footprint_mg_country_total'] / abx['kg_production']

    # Computer FCR for internal check
    abx['fcr'] = abx['feed_kg'] / abx['kg_production']

    # If a country produces 0 mt of a given meat item, div by zero = inf.
    # Replace these w/zero since if they don't produce any meat the feed footprint of that country's meat should also by zero.
    abx['footprint'].replace([np.inf, -np.inf, np.nan], 0, inplace=True)

    # Add pasture
    abx = add_pasture_fp(abx, pasture, bans, prod, countries)

    abx['source'] = 'Adapted from Wieben C.M. (2021) and FAO (2017) GLEAM-i v2.0 revision 3.'

    # Diagnostic: Check for duplicate indices
    check_duplicate_indices(abx, index_cols=['country_code', 'country', 'fbs_item_code', 'fbs_item', 'footprint_type'])

    # Output
    # This will later get combined and summed with meat footprints, AFTER classifying by drug.
    abx.to_csv(paths.interim/'item_footprints/item_footprints_abx_feed.csv', index=False)