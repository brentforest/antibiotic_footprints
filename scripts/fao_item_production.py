import pandas as pd
import paths
from utilities import *

pd.options.display.max_columns = 999
pd.options.mode.chained_assignment = None


def fao_item_production():

    # Input ************************************************************************************************************
    run_params = pd.read_excel(paths.params, sheet_name='parameters', skiprows=1).set_index('parameter')

    # Terrestrial inputs
    crops = eval('pd.read_csv(paths.input/"fao//item_production/crops_primary.csv").pipe(snake_case_cols)')
    crops_proc = eval('pd.read_csv(paths.input/"fao/item_production/crops_processed.csv").pipe(snake_case_cols)')
    livestock = eval('pd.read_csv(paths.input/"fao/item_production/livestock_primary.csv").pipe(snake_case_cols)')
    livestock_proc = eval('pd.read_csv(paths.input/"fao/item_production/livestock_processed.csv").pipe(snake_case_cols)')

    # Filter ***********************************************************************************************************

    # Convert years parameter to list of integers
    fao_years = run_params.loc['fao_data_years', 'value']
    fao_years = string_to_int_list(fao_years)

    proc_years = run_params.loc['fao_processed_item_production_years', 'value']
    proc_years = string_to_int_list(proc_years)

    # Filter by year
    # Production data for processed items may cover a different set of years, so for these we use a different parameter
    crops = crops[crops['year'].isin(fao_years)]
    livestock = livestock[livestock['year'].isin(fao_years)]
    crops_proc = crops_proc[crops_proc['year'].isin(proc_years)]
    livestock_proc = livestock_proc[livestock_proc['year'].isin(proc_years)]

    # Combine items
    fao_prod = pd.concat([crops, crops_proc, livestock, livestock_proc])

    # Rename cols; note that different years of data might use slightly different names
    fao_prod.rename(columns={
        'area_code': 'country_code',
        'area_code_fao': 'country_code',
        'area': 'country',
        'item_code': 'fao_item_code',
        'item_code_fao': 'fao_item_code',
        'item': 'fao_item'},
        inplace=True
    )
    fao_prod = fao_prod[fao_prod['unit'] == 'tonnes']
    #fao_prod = fao_prod[fao_prod['year'].isin(fao_years)]

    # Compute avg ******************************************************************************************************

    # Pivot on year, calculate average over years
    # Including 'domain' in index_cols ignores duplicate index errors where the same fbs appears multiple times,
    # e.g., in both crops and crops processed
    index_cols = ['domain', 'country_code', 'country', 'fao_item_code', 'fao_item']
    fao_prod = s_pivot(fao_prod, index_cols, ['year'], ['value'])
    fao_prod['mt_production'] = fao_prod[fao_years + proc_years].mean(axis='columns')

    # Since there is no production data on specific offal types, use weighted avg of pig and cattle meat production
    offals_prod = fao_prod[fao_prod['fao_item'].isin(['Meat, cattle', 'Meat, pig'])]
    offals_prod['fao_item_code'].replace({
        867: 868,
        1035: 1036},
        inplace=True
    )
    offals_prod['fao_item'].replace({
        'Meat, cattle': 'Offals, edible, cattle',
        'Meat, pig': 'Offals, pigs, edible'},
        inplace=True
    )
    fao_prod = pd.concat([fao_prod, offals_prod])

    # If an fbs item is repeated across multiple domains (e.g., crops, crops processed), only keep the first instance
    index_cols = ['country_code', 'country', 'fao_item_code', 'fao_item']
    fao_prod.set_index(index_cols, inplace=True)
    fao_prod = fao_prod[~fao_prod.index.duplicated(keep='first')]\
        .reset_index()\
        .drop(columns='domain')
    fao_prod.set_index(index_cols, verify_integrity=True)

    # Output result
    fao_prod.to_csv(paths.interim/'fao_item_production.csv', index=False)

