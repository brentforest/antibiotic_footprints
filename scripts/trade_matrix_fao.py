import pandas as pd
import gc # Garbage collection module, to save memory
import numpy as np
import paths
from datetime import datetime
from utilities import *

pd.options.display.max_columns = 999
pd.options.mode.chained_assignment = None

startTime = datetime.now()


def rename_filter_cols(tm):

    tm.rename(columns={
        'reporter_country_code': 'country_code',
        'reporter_countries': 'country',
        'partner_country_code': 'coo_code',
        'partner_countries': 'coo'},
        inplace=True
    )

    tm = tm[['country_code', 'country', 'coo_code', 'coo', 'item_code',
             'item', 'unit', 'year', 'value']]
    tm = tm[tm['unit'] == 'tonnes']

    return tm


# Main method
def trade_matrix_fao():

    # Input ************************************************************************************************************

    run_params = pd.read_excel(paths.params, sheet_name='parameters', skiprows=1).set_index('parameter')

    """
    # Filter raw trade matrix file to imports only so we don't need to load the entire thing every time.
    # This is commented out because it only needs to be executed once after downloading new trade matrix data.
    tm_raw = pd.read_csv('../data/input/fao/' + fao_folder + '/fao_trade_matrix_all_data_normalized.csv',  encoding='latin-1').pipe(snake_case_cols)
    tm_raw = tm_raw[tm_raw['element'] == 'Import Quantity']
    tm_raw = tm_raw[tm_raw['year'] >= 2011]
    tm_raw.to_csv('../data/input/fao/' + fao_folder + '/fao_imports.csv', index=False)
    """

    extr_rates = (pd.read_csv(paths.interim / 'fao_extraction_rates.csv')
        [['country_code', 'fao_item_code', 'extr_rate_mt/mt']])
    extr_rates_world = (pd.read_csv(paths.interim / 'fao_extraction_rates_world.csv')
        [['fao_item_code', 'extr_rate_world_mt/mt']])
    fao_to_fbs = (pd.read_excel(paths.input / 'fao_items_to_fbs.xlsx', sheet_name='final_appended')
        [['fao_item_code', 'fbs_item_code']])
    item_params = (pd.read_excel(paths.input / 'item_parameters.xlsx', sheet_name='fbs_items')
        .pipe(snake_case_cols)
        [['fbs_item_code', 'fbs_item', 'ignore_extraction_rate']])

    tm = pd.concat([
        pd.read_csv(paths.input/'fao/trade_matrices/fao_imports_2016.csv'),
        pd.read_csv(paths.input / 'fao/trade_matrices/fao_imports_2017.csv'),
        pd.read_csv(paths.input / 'fao/trade_matrices/fao_imports_2018.csv'),
        pd.read_csv(paths.input / 'fao/trade_matrices/fao_imports_2019.csv')], sort=False)


    # Filter to selected years *****************************************************************************************

    tm = rename_filter_cols(tm)

    fao_years = run_params.loc['fao_data_years', 'value']
    fao_years = string_to_int_list(fao_years)
    tm = tm[tm['year'].isin(fao_years)]

    # Compute average over years ***************************************************************************************

    index_cols = ['country_code', 'country', 'coo_code', 'coo', 'item_code', 'item', 'unit']
    tm = s_pivot(tm, index_cols, ['year'], ['value'])
    tm['imports_avg_mt/yr'] = tm[fao_years].mean(axis=1, skipna=True)

    # Adjust to primary equivalents ************************************************************************************

    # Merge w/extraction rates, items, and item_parameters (the latter two are to determine where to ignore extr rates)
    extr_rates = extr_rates.rename(columns = {'country_code': 'coo_code'})
    tm = (tm.rename(columns = {'item_code': 'fao_item_code'})
          .merge(extr_rates, on=['coo_code', 'fao_item_code'], how='left')
          .merge(extr_rates_world, on='fao_item_code', how='left')
          .merge(fao_to_fbs, on='fao_item_code', how='left')
          .merge(item_params, on='fbs_item_code', how='left'))

    # Use country-specific extraction rate where available, otherwise use global avg
    conds = [tm['ignore_extraction_rate'] == 'yes', tm['extr_rate_mt/mt'].notna(),
             tm['extr_rate_world_mt/mt'].notna()]
    choices = [1, tm['extr_rate_mt/mt'], tm['extr_rate_world_mt/mt']]
    tm['extr_rate_final_mt/mt'] = np.select(conds, choices, default=1)

    # Calculate imported quantities as primary equivalent, output
    tm['imports_primary_equivalent_mt/yr'] = tm['imports_avg_mt/yr'] / tm['extr_rate_final_mt/mt']
    tm.to_csv(paths.diagnostic / 'fao_trade_matrix_avg_primary_before_grouping.csv', index=False)

    # Group by countries and FBS item
    index_cols = ['country_code', 'country', 'coo_code', 'coo',
                  'fbs_item_code', 'fbs_item']
    tm = tm.groupby(index_cols)['imports_primary_equivalent_mt/yr'].sum().reset_index()

    # Output
    tm.to_csv(paths.interim/'fao_trade_matrix_avg_primary.csv', index=False)