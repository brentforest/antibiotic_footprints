import numpy as np
import pandas as pd
import gc # Garbage collection module, to save memory
import math
import paths
import winsound
from datetime import datetime
from utilities import *
from utilities_diet_climate import *

pd.options.display.max_columns = 999
pd.options.mode.chained_assignment = None

INPUT_PATH = 'antibiotic_use/abu_crops.xlsx'

def prep_taylor_reeder(tr, sea, prod):

    # Note: for rice production, we could use either FAO production or FBS production.
    # FAO item production reports on production of two different rice items: 'rice, paddy' and milled equivalent;
    # oddly, quantities of 'rice, paddy' (and not milled equivalent) in FAO production match quantities
    # of 'rice, milled equivalent' in FBS production. I wonder if this is an error on FAO's part.
    # Quantities of paddy rice are generally 50% higher than quantities of milled rice, so the choice of which to use
    # could significantly impact our results.
    # I think I'll go with FBS production, consistent with how we handle USGS data.
    rice_prod = s_filter(prod, col='fbs_item', list=['Rice (Milled Equivalent)'])[
        ['country_code', 'country', 'gleam_region', 'crop', 'mt_production']]

    # Merge SEA countries w/rice production
    sea = s_merge(sea, rice_prod, on=['country_code', 'country'], how='left')

    # Sum total production over all SEA countries; this is the denominator,
    # NOT individual country production
    sea['mt_production_sea_total'] = sea['mt_production'].sum()

    # Merge to get every permutation of abx use, country, and production
    sea['crop'] = 'Rice'
    tr = s_merge(sea, tr, on='crop', how='left')

    # Compute mg/kg footprint; the denominator is TOTAL production over all SEA countries
    tr['mg_abx/year'] = tr['mt_abx/year'] * 1000000000
    tr['kg_production'] = tr['mt_production_sea_total'] * 1000
    tr['footprint'] = tr['mg_abx/year'] / tr['kg_production']

    return tr

def prep_usgs(usgs, run_params, prod):

    # Use low, high, or avg kg/year depending on run params; remove cols
    usgs.rename(columns={run_params.loc['abx_crops_low_high', 'value']: 'kg_abx/year',
                        'abx': 'footprint_type'}, inplace=True)

    # Groupby drug class, since there may be data for multiple specific compounds with a given drug class;
    # Drop non-food crops; note cotton is technically included since it gets matched with the FBS item "cottonseed oil".
    usgs = usgs.groupby(['crop', 'footprint_type'])['kg_abx/year'].sum().reset_index()

    # Output a prepped version of USGS, pasture only, for use in the feed script
    s_filter(usgs, col='crop', list=['Pasture_and_hay']).to_csv(
        paths.interim/'item_footprints/item_footprints_abx_pasture.csv', index=False)

    # Remove cotton - we excluded cottonseed oil from FBS items, and it has so many non-food uses anyway
    # Remove animal feeds - there are no production data for these, so if we do include them in the model,
    # we'd have to use a different method than the one applied here.
    # Note alfalfa does not have any footprint associated with it anyway.
    usgs = s_filter(usgs, col='crop', excl_list=['Alfalfa', 'Pasture_and_hay', 'Cotton'])

    # Compute mg/kg ****************************************************************************************************
    # USGS estimates are totals for the US, so we're only interested in US production data
    prod = s_filter(prod, col='country', list=['United States of America'])

    # Group and sum production by crop, i.e., sum over individual FBS items associated w/each crop
    prod = prod.groupby(['gleam_region', 'country_code', 'country', 'crop'])['mt_production'].sum().reset_index()

    # Match abx data to US production data
    usgs = s_merge(usgs, prod, on='crop', how='left', validate='m:1', left_name='usgs', right_name='production')

    # Compute abx footprint
    # Note: do this BEFORE merging abx with FBS items, otherwise we risk double counting.
    # If we compute footprint after merging, we would need to allocate total US use over each FBS item.
    usgs['mg_abx/year'] = usgs['kg_abx/year'] * 1000000
    usgs['kg_production'] = usgs['mt_production'] * 1000
    usgs['footprint'] = usgs['mg_abx/year'] / usgs['kg_production']
    #usgs['footprint_type'] = 'mg_abx_' + usgs['footprint_type'].astype(str)

    usgs['source'] = 'Wieben C.M., 2021. Estimated annual agricultural pesticide use by major crop or crop group for states of the conterminous United States, 1992-2019.'

    return(usgs)


def apply_country_bans(abx, bans, run_diagnostics=False):

    bans = bans.drop(columns=['source', 'note'])
    bans = bans.melt(id_vars='country', var_name='footprint_type', value_name='approved')
    bans = s_filter(bans, col='country', excl_list=['EU/EEA']) # Drop EU since we have separate rows for each country

    # Diagnostic: make sure all the indices in bans have a match in abx
    if run_diagnostics:
        test = s_merge(bans, abx, on='country', how='left')
        test = s_merge(bans, abx, on='footprint_type', how='left') # note we don't have any data on gentamicin in crops

    # merge w/abx and assign country footprints to zero
    abx = abx.merge(bans, on=['country', 'footprint_type'], how='left', validate='m:1')
    abx['approved'] = abx['approved'].fillna('n.d.')
    abx['footprint'] = np.where(abx['approved']=='no', 0, abx['footprint'])

    return abx


# Main method
def item_footprints_abx_crops():

    # Input ************************************************************************************************************

    # USGS data
    usgs = pd.read_excel(paths.input/INPUT_PATH, sheet_name='abu_usgs_merged_avg', skiprows=3)
    countries = pd.read_csv(paths.interim / 'fao_countries.csv')[
        ['country_code', 'country', 'gleam_region']]
    run_params = pd.read_excel(paths.params, sheet_name='parameters', skiprows=1).set_index('parameter')

    # Rice data from Taylor and Reeder
    tr = pd.read_excel(paths.input/INPUT_PATH, sheet_name='abu_crops_tr', skiprows=3)
    sea =pd.read_excel(paths.input/INPUT_PATH, sheet_name='tr_countries', skiprows=3)

    # Countries wih bans
    bans = pd.read_excel(paths.input/INPUT_PATH, sheet_name='abu_crops_bans', skiprows=3)
    # Used for both
    crops_to_fbs = pd.read_excel(paths.input/INPUT_PATH, sheet_name='crops_to_fbs', skiprows=3)
    prod = pd.read_csv(paths.interim / 'fbs_item_production.csv')

    # *****************************************************************************************************************

    # Match production data for fbs items to crop items used in abx data (m:1)
    # Also get region.
    prod = prod.merge(crops_to_fbs, on=['fbs_item_code', 'fbs_item'], how='left', validate='m:1') \
        .pipe(s_merge, countries, on=['country_code', 'country'], how='left')

    tr = prep_taylor_reeder(tr, sea, prod)
    usgs = prep_usgs(usgs, run_params, prod)

    abx = pd.concat([tr, usgs], sort=False)

    # Export abx footprint by crop; this doesn't get used by the model but may be used for figures, or other analyses
    abx.to_csv(paths.interim / 'item_footprints/item_footprints_abx_crops_by_crop.csv', index=False)

    # ******************************************************************************************************************

    # Merge w/FBS items
    # Crops:FBS is 1:m, so groupby isn't necessary
    abx = s_merge(abx, crops_to_fbs, on='crop', how='left', validate='m:m', left_name='abx', right_name='crops_to_fbs')[
        ['fbs_item_code', 'fbs_item', 'country_code', 'country', 'gleam_region', 'footprint_type', 'footprint', 'source']]

    # In order to apply crop bans, and to use crop data for feed abx estimates,
    # we first need to assign footprints for all countries, using regional and global averages where country-specific data are missing.
    abx = apply_regional_global_wavg(abx, prod, countries)

    # Assign footprint to zero where we know countries have banned certain drugs.
    # I think it's reasonable to do this step AFTER computing regional/global averages;
    # we have data for so few countries that if we average in the banned countries I think it would skew too closely to zero.
    abx = apply_country_bans(abx, bans)

    abx['footprint_type'] = 'mg_abx_' + abx['footprint_type']

    # Final output
    abx.to_csv(paths.interim/'item_footprints/item_footprints_abx_crops.csv', index=False)