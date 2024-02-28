import numpy as np
import pandas as pd
import gc # Garbage collection module, to save memory
import math
import paths
import winsound
from datetime import datetime
from utilities import *

pd.options.display.max_columns = 999
pd.options.mode.chained_assignment = None


def prep_abx(abx, run_params):

    # Use low, high, or mean mg_abx/kg depending on run params;
    abx.rename(columns={run_params.loc['abx_aqua_low_high', 'value']: 'mg/kg',
                    'abx': 'footprint_type'}, inplace=True)
    abx = abx[['schar_item', 'mg/kg']]

    return abx


def allocate_abx_by_drug(abx, drugs):

    # Drop unused blank rows from drugs
    # Dropping rows means totals are just under 100%, so recalculate %s
    drugs = drugs[drugs['footprint_type'].notna()]
    drugs['adj_%_total'] = drugs['%_by_drug_class'].sum()
    drugs['%_by_drug_class'] /= drugs['adj_%_total'] / 100

    # Merge w/drug classes and allocate
    abx['merge_dummy_var'] = 'dummy'
    drugs['merge_dummy_var'] = 'dummy'
    abx = s_merge(abx, drugs, on='merge_dummy_var', how='left')
    abx['footprint'] = abx['mg/kg'] * (abx['%_by_drug_class'] / 100)

    # Diagnostic check: make sure allocated values = original totals
    abx['diagnostic_check'] = abx.groupby(['schar_item'])['footprint'].transform('sum').astype(int)
    abx['diagnostic_compare'] =  abx['mg/kg'] - abx['diagnostic_check']
    if (abx['diagnostic_compare'] != 0).any():
        print('ERROR: sum of allocated abx values by drug do not match original totals')
        winsound.Beep(400, 400)

    abx = abx[['schar_item', 'footprint_type', 'footprint']]
    return abx


def prep_asfis(asfis, isscaap):

    asfis = snake_case_cols(asfis)
    asfis.rename(columns={'isscaap': 'isscaap_code'}, inplace=True)

    # Production data include either the english name or the scientific name in the same column
    # For matching purposes, create a single column that includes both english and scientific names
    asfis_sci = asfis.copy()[['isscaap_code', 'scientific_name']].\
        rename(columns={'scientific_name': 'asfis_species'})
    asfis = asfis[['isscaap_code', 'english_name']].\
        rename(columns={'english_name': 'asfis_species'})
    asfis = pd.concat([asfis, asfis_sci])

    # Merge asfis w/isscaap codes, so we can later go to schar items or FBS items
    asfis = asfis.merge(isscaap, on='isscaap_code', how='left', validate='m:1')

    return asfis


def merge_prod(prod, asfis, schar_fw_match, countries):

    # Exclude data for totals and numbered items like whales, seals, etc.
    prod = prod[prod['Unit (Name)'] == 'Tonnes - live weight']

    prod.rename(columns={'Country (Name)': 'fishstat_country',
                         'ASFIS species (Name)': 'asfis_species',
                         "[2019]": 'mt_production/yr',
                         'Detailed production source (Name)': 'system'}, inplace=True)

    # Remove brackets from scientific names so we can match them to ASFIS species
    prod['asfis_species'] = prod['asfis_species'].str.replace('[', '')
    prod['asfis_species'] = prod['asfis_species'].str.replace(']', '')

    prod = prod[['fishstat_country', 'asfis_species', 'system', 'mt_production/yr']]

    # Merge w/asfis so we can get FBS items
    # A few don't have matches, that's okay
    prod = prod.merge(asfis, on='asfis_species', how='inner')

    # Match prod to Schar items that will eventually need to be weighted-averaged into Freshwater fish
    # Only a few issccaap items have matches in schar
    # Assign the rest to "none" so they don't get dropped when later using groupby
    prod = prod.merge(schar_fw_match, on='species_group', how='left', validate='m:1')
    prod['schar_freshwater_item'] = prod['schar_freshwater_item'].fillna('non_freshwater')

    # Match prod to FAO countries
    # A few don't have matches, that's okay
    prod = prod.merge(countries, on='fishstat_country', how='inner', validate='m:1')

    return prod


# Main method
def item_footprints_abx_aqua():

    # Input ************************************************************************************************************

    run_params = pd.read_excel(paths.params, sheet_name='parameters', skiprows=1).set_index('parameter')

    # Schar et al.
    abx = pd.read_excel(paths.input/'antibiotic_use/abu_aquatic_animals.xlsx', sheet_name='abu_aqua', skiprows=3)
    schar_to_fbs = pd.read_excel(paths.input/'antibiotic_use/abu_aquatic_animals.xlsx', sheet_name='schar_to_fbs', skiprows=3)
    schar_fw_match = pd.read_excel(paths.input/'antibiotic_use/abu_aquatic_animals.xlsx', sheet_name='isscaap_to_schar_fw_items', skiprows=3)

    # By drug class
    drugs = pd.read_excel(paths.input/'antibiotic_use/abu_aquatic_animals.xlsx', sheet_name='abu_%_by_drug', skiprows=3)[
        ['footprint_type', '%_by_drug_class']]

    # Countries
    countries = pd.read_csv(paths.interim / 'fao_countries.csv')[
        ['fishstat_country', 'country_code', 'country', 'gleam_region']]

    # Production
    #TODO: Consider moving some steps to a separate script if ever need fishtat production data for other parts of the model
    prod = pd.read_csv(paths.input / 'fishstat/production/fishstat_production_by_country_source.csv')
    asfis = pd.read_csv(paths.input / 'fishstat/production/asfis_species.csv', skiprows=1)
    isscaap = pd.read_csv(paths.input / 'fishstat/isscaap_to_fbs.csv', skiprows=2)\
        [['isscaap_code', 'faostat_code', 'species_group', 'fbs_item_code', 'fbs_item']]

    # *****************************************************************************************************************

    # Prep abx
    abx = prep_abx(abx, run_params)

    # Allocate Schar et al. abx intensity estimates over individual drug classes.
    # Output result (without diadromous avg, since that averages salmon and trout) so it can be used in item footprint figures
    abx = allocate_abx_by_drug(abx, drugs)
    s_filter(abx, col='schar_item', excl_list=['diadromous_avg']).\
        to_csv(paths.interim / 'item_footprints/item_footprints_abx_aqua_by_schar_item.csv', index=False)

    # Drop salmon and trout (these are represented as diadromous avg);
    # Merge w/FBS items
    abx = s_filter(abx, col='schar_item', excl_list=['salmon', 'trout'])
    abx = s_merge(abx, schar_to_fbs, on='schar_item', how='left')

    # Prep production data *********************************************************************************************

    # Merge production data
    asfis = prep_asfis(asfis, isscaap)
    prod = merge_prod(prod, asfis, schar_fw_match, countries)
    prod.to_csv(paths.diagnostic / 'abx/fishstat_prod_matched.csv', index=False)

    # Group and sum production data by isscaap code and fao country;
    # this resolves duplicate indices and simplifies the data
    index_cols = ['country_code', 'country', 'fbs_item_code', 'fbs_item', 'schar_freshwater_item', 'system']
    prod = prod.groupby(index_cols)[['mt_production/yr']].sum().reset_index()

    # Pivot system so we can compute % of production from aquaculture
    index_cols = ['country_code', 'country', 'fbs_item_code', 'fbs_item', 'schar_freshwater_item']
    prod = s_pivot(df=prod, idx=index_cols, cols=['system'], vals=['mt_production/yr'])
    prod = prod.fillna(0)
    prod['mt_production_aqua'] = prod['Aquaculture production (freshwater)'] \
                                        + prod['Aquaculture production (brackishwater)'] \
                                        + prod['Aquaculture production (marine)']
    prod['mt_production_total'] = prod['mt_production_aqua'] + prod['Capture production']
    prod.to_csv(paths.diagnostic / 'abx/fishstat_prod_grouped_pivot.csv', index=False)

    # Group by fbs item and compute % from aquaculture *****************************************************************
    # This has to be done with a copy of abx that will be merged back later,
    # because we need to use groupby.wavg
    index_cols = ['country_code', 'country', 'fbs_item_code', 'fbs_item']
    aqua = prod.copy()
    aqua = aqua.groupby(index_cols)[['mt_production_aqua', 'mt_production_total']].sum().reset_index()
    aqua['%_production_aqua'] = (aqua['mt_production_aqua'] / aqua['mt_production_total'])\
        .fillna(0)
    aqua.to_csv(paths.diagnostic / 'abx/%_aqua.csv', index=False)

    # Merge abx w/production data **************************************************************************************
    abx = s_merge(abx, prod, on=['fbs_item_code', 'fbs_item', 'schar_freshwater_item'], how='left', validate='m:m')
    abx.to_csv(paths.diagnostic / 'abx/abx_aqua_merged.csv', index=False)

    # Compute weighted avg for freshwater fish
    index_cols = ['country_code', 'country', 'fbs_item_code', 'fbs_item', 'footprint_type']
    abx = abx.groupby(index_cols).apply(wavg, 'footprint', 'mt_production_aqua')\
        .rename('footprint').reset_index()

    # Weighted avg generates NAN values if weight (production) = zero;
    # Replace NAN with footprint of zero;
    # this is the correct assignment if that country produces no aquaculture for that species
    abx['footprint'] = abx['footprint'].fillna(0)
    abx.to_csv(paths.diagnostic / 'abx/abx_aqua_wavg.csv', index=False)

    # merge and multiply footprints by % of production from aquaculture
    abx = s_merge(abx, aqua, on=['country_code', 'country', 'fbs_item_code', 'fbs_item'], how='left')
    abx['footprint_unadj'] = abx['footprint']
    abx['footprint'] *= abx['%_production_aqua']

    # Add back regions
    countries = countries[['country_code', 'country', 'gleam_region']]
    abx = s_merge(abx, countries, on=['country_code', 'country'], how='left', validate='m:1')

    abx['source'] = 'Schar D., et al. 2020. Global trends in antimicrobial use in aquaculture.'

    # Final output
    abx.to_csv(paths.interim/'item_footprints/item_footprints_abx_aqua.csv', index=False)

