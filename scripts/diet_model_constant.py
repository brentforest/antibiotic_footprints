import pandas as pd
import numpy as np
import paths
from datetime import datetime
from utilities import *

pd.options.display.max_columns = 999
pd.options.mode.chained_assignment = None

def combine_country_with_constant_diet(g, dm_constant, item_cols):
    # Helper function to merge and then re-populate needed columns

    country_code = g[1]['country_code'].iloc[0]
    country = g[1]['country'].iloc[0]

    result = g[1].merge(dm_constant, how='right', on=item_cols).reset_index()
    result['country'] = country
    result['country_code'] = country_code
    return result


def diet_model_constant():
    # Hold consumption constant; differences in results by country are explained by COO

    # Input ************************************************************************************************************
    dm = pd.read_csv(paths.interim/'diet_model_baseline.csv')
    countries = pd.read_csv(paths.interim/'fao_countries.csv') \
        [['country_code', 'income_class', 'oecd']]
    countries_to_run = pd.read_excel(paths.params, sheet_name='countries_incl', skiprows=1)
    run_params = pd.read_excel(paths.params, sheet_name='parameters', skiprows=1).set_index('parameter')

    # ******************************************************************************************************************

    constant_diet = run_params.loc['diet_model_constant', 'value']
    print(constant_diet)

    # Check if there any filtered countries, in which case use the last saved version
    countries_to_run['run'] = countries_to_run['run'].apply(str)
    countries_to_run = countries_to_run[countries_to_run['run'] == 'yes']['country_code'].tolist()
    if countries_to_run:
        print('NOT ENOUGH COUNTRIES IN PARAMETERS TO COMPUTE DIET MODEL CONSTANT; using last saved version')
        dm = pd.read_csv(paths.interim / 'diet_model_constant.csv')
        dm = dm[dm['country_code'].isin(countries_to_run)]
        dm.to_csv(paths.interim / 'diet_model_constant.csv', index=False)
        return

    baseline_cols = dm.columns[dm.columns.str.startswith('baseline')].tolist()
    results_cols = [col.replace('baseline_', '') for col in baseline_cols]
    constant_cols = [col.replace('baseline_', 'constant_') for col in baseline_cols]
    item_cols = ['fbs_item_code', 'fbs_item', 'output_group', 'type']

    # Assign all results values to values for an average of countries
    dm_constant = dm.merge(countries, on='country_code', how='left')\
        .pipe(s_filter, col='income_class', list=['High income'])
    if constant_diet=='baseline_oecd':
        print('Filtering to high income OECD countries only')
        dm_constant = s_filter(dm_constant, col='oecd', list=['yes'])

    country_list = dm_constant['country'].unique()
    country_code_list = dm_constant['country_code'].unique()
    print('countries included in dm_constant:', country_list)

    # Compute average baseline consumption patterns over countries
    # Note: Watch for cases where this might be ignoring NAN
    print('checking for null results before computing mean (should be empty):',
          dm_constant[dm_constant[baseline_cols].isna().any(axis=1)])
    dm_constant = dm_constant.groupby(item_cols)[baseline_cols].mean().reset_index()
    dm_constant[constant_cols] = dm_constant[baseline_cols]
    dm_constant = dm_constant[['fbs_item_code'] + constant_cols]

    # Merge dm with dm_constant
    dm = s_merge(dm, dm_constant, on='fbs_item_code', how='left', validate='m:1')

    # Assign all results values to values for an average of countries,
    # unless a country is among those countries, in which case use baseline values.
    # Unlike the previous version (in the archive folder), if a food is missing from a country's supply, it is not added.
    # So the diets of a few LMICs are not exactly the same as the high-income avg, but it's close enough and much simpler to code this way.
    dm[results_cols] = dm[constant_cols]
    conds = dm['country_code'].isin(country_code_list)
    for c in range(0, len(results_cols)):
        dm.loc[conds, results_cols[c]] = dm.loc[conds, baseline_cols[c]]

    dm['diet'] = constant_diet
    dm['scaling_method'] = 'constant'

    dm.to_csv(paths.interim/'diet_model_constant.csv', index=False)
