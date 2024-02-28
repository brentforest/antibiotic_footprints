import numpy as np
import pandas as pd
import gc # Garbage collection module, to save memory
import math
import paths
import winsound
from datetime import datetime
from utilities import *
#from utilities_stats import test_pearson

pd.options.display.max_columns = 999
pd.options.mode.chained_assignment = None

INPUT_PATH = 'antibiotic_use/abu_terrestrial_meat.xlsx'

def proportion_by_system_estimated(gdp):
# Estimate % intensive/extensive by species and country using GDP

    # Drop countries with no GDP data
    # TODO: this effectively drops 18 countries worth of abx data for pork and poultry; discuss possible alternatives
    gdp = gdp[gdp['gdp'].notna()]

    # Compute % intensive/extensive based on GDP, using formula from Gilbert, Conchedda, Boeckel et al.
    gdp['log_10_gdp'] = gdp.apply(lambda row: math.log10(row['gdp']), axis=1)

    # Chickens
    m = 1.064
    L = 3.9
    gdp['Poultry Meat'] = gdp.apply(lambda row:
                                    1 / (1 + math.exp((4 * m / 1) * (row['log_10_gdp'] - L) + 2)),
                                    axis=1)

    # Pigs
    m = 1.355
    A = 0.884
    gdp['Pigmeat'] = gdp.apply(lambda row:
                               A / (1 + math.exp((4 * m / A) * (row['log_10_gdp'] - 4.2) + 2)),
                               axis=1)

    # Unpivot so each country and animal is a row,
    # Compute % intensive
    gdp = gdp.melt(id_vars=['country_iso_code'], value_vars=['Poultry Meat', 'Pigmeat'],
                   var_name='fbs_item', value_name='extensive')
    gdp['intensive'] = 1 - gdp['extensive']

    # Melt systems so each country, animal, and system is a row
    gdp = gdp.melt(id_vars=['country_iso_code', 'fbs_item'], var_name='system', value_name='proportion_est')

    return gdp


def proportion_by_system_observed(gilbert):
# Combine observed %s with estimated %s

    # Drop n/a countries and regions, e.g., Antarctica, Bird island, Arunashal Pradesh, etc.
    # Also drop values where country iso code = NA; these are read by python as "nan"
    gilbert = s_filter(gilbert, col='fao_country_code', excl_list=[-9999]).drop(columns='fao_country_code')
    gilbert = gilbert[gilbert['country_iso_code'].notna()]

    # Melt so both animals are in the same column
    gilbert = gilbert.melt(id_vars=['country_iso_code'], var_name='species', value_name='extensive')

    # Drop data with no observation
    gilbert = gilbert[gilbert['extensive'] != -9999]

    # Compute % int/ext
    # TODO: Gilbert et al. has a value for semi-intensive pig production; here we classify this as intensive
    gilbert['extensive'] *= 0.01
    gilbert['intensive'] = 1 - gilbert['extensive']

    # Add FBS item
    gilbert['fbs_item'] = np.where(gilbert['species'].str.contains('pg'), 'Pigmeat', 'Poultry Meat')
    gilbert = gilbert.drop(columns='species')

    # Melt systems so each country, animal, and system is a row
    gilbert = gilbert.melt(id_vars=['country_iso_code', 'fbs_item'], var_name='system', value_name='proportion_obs')

    return gilbert


def diagnostic_check_systems_countries(abx, systems, countries):

    diagnostic = s_merge(abx, countries, on='country_iso_code', how='inner')  # technically not m:1 because countries has blank codes

    diagnostic = s_merge(diagnostic, systems, on=['country_iso_code', 'fbs_item', 'system'], how='left', validate='m:1', keep_merge_col=True,
                  alert=False)
    # Change iso-3 country codes to FAO country codes and country names
    # Rename columns for compatibility with study model
    # Note some ISO-3 country codes may not have an FAO match, this is ok, we''ll drop them w/an inner merge

    diagnostic.to_csv(paths.diagnostic / 'abx/abx_meat_systems_merge.csv', index=False)


# Main method
def item_footprints_abx_meat(production_system='baseline'):

    # Input ************************************************************************************************************

    abx = pd.read_excel(paths.input/INPUT_PATH, sheet_name='abu_meat', skiprows=3) \
        .rename(columns={'ISO3': 'country_iso_code'}).pipe(snake_case_cols)

    abx_feed = pd.read_csv(paths.interim / 'item_footprints/item_footprints_abx_feed.csv')

    countries = pd.read_csv(paths.interim / 'fao_countries.csv')[
        ['country_iso_code', 'country_code', 'country', 'gleam_region', 'income_class']]
    fbs_match = pd.read_excel(paths.input/INPUT_PATH, sheet_name='abu_meat_to_fbs', skiprows=3)
    gdp = pd.read_excel(paths.input/INPUT_PATH, sheet_name='gdp_per_cap', skiprows=3)[
        ['country_iso_code', '2021']] \
        .rename(columns={'2021': 'gdp'})
    gilbert = pd.read_excel(paths.input/INPUT_PATH, sheet_name='%_by_system', skiprows=3)[
        ['country_iso_code', 'fao_country_code', 'pgext', 'chext']]
    ko = pd.read_excel(paths.input/INPUT_PATH, sheet_name='ko_%', skiprows=3)

    # Compile % of production in intensive/extensive systems ***********************************************************

    # Estimate %s by species and country based on GDP
    systems_est = proportion_by_system_estimated(gdp)
    systems_est.to_csv(paths.diagnostic/'abx/systems_estimated.csv', index=False)

    # Compile observed %s from Gilbert et al.
    systems_obs = proportion_by_system_observed(gilbert)
    systems_obs.to_csv(paths.diagnostic/'abx/systems_observed.csv', index=False)

    # Where observed values exist, replace estimated values
    systems = systems_est.merge(systems_obs, on=['country_iso_code', 'fbs_item', 'system'], how='outer', validate='1:1')
    systems['proportion'] = np.where(systems['proportion_obs'].notna(), systems['proportion_obs'], systems['proportion_est'])

    if production_system == 'baseline':
        print('Assuming baseline shares of intensive/extensive production for pig and poultry abx use')

    # Assume 100% intensive production
    elif production_system == 'intensive':
        print('Assuming 100% intensive production for pig and poultry abx use')
        systems['proportion'] = np.where(systems['system'] == 'intensive', 1, 0)

    systems.to_csv(paths.diagnostic / 'abx/systems.csv', index=False)

    # NOTE: %s are based on proportion of animals, not proportion of meat
    # Proportion of meat would only be relevant if animals from int vs. ext systems differ in terms of meat yield/head
    # Based on a cursory investigation of the literature (see documentation), this would not seem to be the case

    # Transform and compute abx data ***********************************************************************************

    abx.columns = abx.columns.str.replace('_kg', '_mg/kg', regex=True)

    # Unpivot abx data so each drug is a row
    abx = abx[abx['country_iso_code'].notna()] # one of the iso codes is "NA" which gets read as "null"
    abx = abx.melt(id_vars=['country_iso_code', 'species', 'system'], var_name='footprint_type', value_name='mg/kg_lw')
    abx['footprint_type'] = 'mg_abx_' + abx['footprint_type'].str.replace('_mg/kg', '')
    abx['source'] = 'Mulchandani et al. 2023.'

    # Merge abx species with fbs item
    abx = s_merge(abx, fbs_match, on='species', how='left', validate='m:1')
    abx = abx.drop(columns='species')

    # Convert mg/kg live weight to mg/kg carcass weight
    abx = s_merge(abx, ko, on='fbs_item_code', how='left', validate='m:1')
    abx['mg/kg_cw'] = abx['mg/kg_lw'] / abx['ko%'] # (kg abx/kg LW) x (kg LW/kg CW) =  kg abx/kg CW

    # Drop NAN values
    # This must be done BEFORE computing weighted averages by country and species!
    abx = abx[~abx['mg/kg_cw'].isna()]

    # Check for duplicate indices
    index_cols = ['country_iso_code', 'fbs_item_code', 'fbs_item', 'system', 'footprint_type']
    check_duplicate_indices(abx, index_cols)

    # Output results prior to merging w/systems, may be useful for figures
    file = 'item_footprints/item_footprints_abx_meat_by_system.csv'
    abx.to_csv(paths.interim/file, index=False)

    # Merge w/systems
    # copy and separate ruminant meat to concat later since ruminant meat is agnostic to system
    ruminant_meat = abx[(abx['fbs_item'] == 'Bovine Meat') | (abx['fbs_item'] == 'Mutton & Goat Meat')].copy()
    abx = abx[(abx['fbs_item'] != 'Bovine Meat') & (abx['fbs_item'] != 'Mutton & Goat Meat')]

    diagnostic_check_systems_countries(abx, systems, countries)

    print('Merging abx with systems; we don''t know % extensive and % intensive for all countries, so those countries will get dropped.')
    abx = s_merge(abx, systems, on=['country_iso_code', 'fbs_item', 'system'], how='inner', validate='m:1',
                  left_name='abx', right_name='systems', beep=False)

    abx.to_csv(paths.diagnostic/'abx/abx_meat_merged.csv', index=False)

    abx['proportion'] = abx['proportion'].fillna(0.5)

    # Compute avg drug concentration by country, weighted by proportion intensive/extensive
    abx = (abx.groupby(['country_iso_code', 'fbs_item_code', 'fbs_item', 'footprint_type', 'source'])
           .apply(wavg, avg_name='mg/kg_cw', weight_name='proportion')
           .rename('footprint').reset_index())

    # Put ruminant meat back in
    ruminant_meat.rename(columns={'mg/kg_cw': 'footprint'}, inplace=True)
    ruminant_meat = ruminant_meat[['country_iso_code', 'fbs_item_code', 'fbs_item', 'footprint_type', 'footprint', 'source']]
    abx = pd.concat([abx, ruminant_meat], sort=False)

    # Change iso-3 country codes to FAO country codes and country names
    # Rename columns for compatibility with study model
    # Note some ISO-3 country codes may not have an FAO match, this is ok, we''ll drop them w/an inner merge
    abx = s_merge(abx, countries, on='country_iso_code', how='inner', left_name='abx', right_name='countries', beep=False) # technically not m:1 because countries has blank codes
    abx.drop(columns='country_iso_code', inplace=True)

    # Concat meat + feed footprints.
    # I don't think we want to include country-item pairs where we have data for use on feed crops but not in animal production,
    # otherwise we would vastly underestimate the footprint in those countries, and those underestimates
    # would get factored into averages. So we filter feed footprints.
    abx_feed = abx_feed.merge(abx[['country_code', 'fbs_item_code']].drop_duplicates(), on=['country_code', 'fbs_item_code'], how='inner')
    abx_feed['meat_feed'] = 'feed'
    abx['meat_feed'] = 'meat'
    abx = pd.concat([abx, abx_feed], sort=False)

    # Groupby index; drop source since feed and meat data have different sources.
    abx = abx.groupby(['country_code', 'country', 'gleam_region', 'fbs_item_code', 'fbs_item', 'footprint_type', 'meat_feed'])['footprint'].sum().reset_index()

    if production_system == 'intensive':
        #abx = s_filter(abx, 'fbs_item', list=['Pigmeat', 'Poultry Meat'])
        #abx['fbs_item'] = abx['fbs_item'] + '_intensive'
        file = 'item_footprints/item_footprints_abx_meat_intensive.csv'
    else:
        file = 'item_footprints/item_footprints_abx_meat.csv'

     # Final output
    abx.to_csv(paths.interim/file, index=False)

