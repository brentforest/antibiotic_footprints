import pandas as pd
import gc # Garbage collection module, to save memory
import numpy as np
import paths
from datetime import datetime
from utilities import *

pd.options.display.max_columns = 999
pd.options.mode.chained_assignment = None

startTime = datetime.now()

# Main method
def fao_fbs():

    # Input ************************************************************************************************************

    run_params = pd.read_excel(paths.params, sheet_name='parameters', skiprows=1).set_index('parameter')

    fao_years = run_params.loc['fao_data_years', 'value']
    fao_years = string_to_int_list(fao_years)

    fbs_recoded = pd.read_csv('../data/input/fao/fbs_recoded_items.csv')

    fbs = pd.DataFrame()
    for year in fao_years:
        # To get results to match GEC submission 4, needed to use an excel file for 2013 data since
        # a few manual edits required more decimal points than could be stored in a .csv
        try:
            fbs_year = eval('pd.read_csv(paths.input/"fao/food_balance_sheets/' + str(year) + '.csv")')
        except:
            fbs_year = eval('pd.read_excel(paths.input/"fao/food_balance_sheets/' + str(year) + '.xlsx")')
        fbs = pd.concat([fbs, fbs_year], sort=False)
    fbs = snake_case_cols(fbs)

    # Only used when checking if FBS include any items or countries not included in these files
    item_params = pd.read_excel(paths.input/'item_parameters.xlsx')
    countries = pd.read_csv(paths.interim/'fao_countries.csv')

    # Rename cols ******************************************************************************************************

    fbs = fbs.rename(columns={'item': 'fbs_item',
                                'item_code': 'fbs_item_code',
                                'area': 'country',
                                'area_code': 'country_code'})
    fbs = fbs[['country_code', 'country', 'element', 'fbs_item_code', 'fbs_item', 'year', 'value']]

    # Recode 2022 FBS items so we don't need to recode the entire model ************************************************

    fbs = fbs.merge(fbs_recoded, on=['fbs_item_code', 'fbs_item'], how='left', validate='m:1')
    fbs['fbs_item_code'] = choose_first_notna(fbs[['fbs_item_code_recoded', 'fbs_item_code']], default_value='ERROR')
    fbs['fbs_item_code'] = fbs['fbs_item_code'].astype(str).replace('\.0', '', regex=True).astype(int) # This seems unnecessarily complicated but nothing else worked
    fbs['fbs_item'] = choose_first_notna(fbs[['fbs_item_recoded', 'fbs_item']], default_value='ERROR').astype(str)
    fbs.drop(columns=['fbs_item_code_recoded', 'fbs_item_recoded'], inplace=True)

    # Compute avg values over years indicated in parameters ************************************************************

    fbs = s_pivot(fbs, idx=['country_code', 'country', 'element', 'fbs_item_code', 'fbs_item'],
               cols=['year'], vals=['value'])

    fbs['value'] = fbs[fao_years].mean(axis='columns')
    fbs.drop(columns = fao_years, inplace=True)

    # Gather population ************************************************************************************************

    pop = fbs[fbs['element'] == 'Total Population - Both sexes']
    pop = pop[['country_code', 'country', 'value']]
    pop = pop.drop_duplicates()
    pop = pop.rename(columns={'value' : 'population'})
    pop['population'] *= 1000 #adjust for the fact that FBS counts population in 1000s

    # Output
    pop.to_csv(paths.interim/'fao_population.csv', index=False)

    # Compute nutrient composition *************************************************************************************

    nc = fbs[['country_code', 'country', 'element', 'fbs_item_code', 'fbs_item', 'value']]
    nc = nc[nc['element'].isin(['Food supply quantity (kg/capita/yr)', 'Food supply (kcal/capita/day)',
                                'Protein supply quantity (g/capita/day)'])]
    nc = s_pivot(nc, idx=['country_code', 'country', 'fbs_item_code', 'fbs_item'],
               cols=['element'], vals=['value']).pipe(snake_case_cols)

    # Control for population, convert to standard (daily) units
    # Inner merge drops countries with no population data (e.g., Lao People's Republic, Uzbekistan in 2017 data)
    nc = s_merge(nc, pop, on=['country_code', 'country'], how='inner', validate='m:1')
    nc['pop_kg/day'] = nc['food_supply_quantity_kg/capita/yr'] / 365 * nc['population']
    nc['pop_kcal/day'] = nc['food_supply_kcal/capita/day'] * nc['population']
    nc['pop_g_protein/day'] = nc['protein_supply_quantity_g/capita/day'] * nc['population']

    # Group and sum by FBS item to yield global totals; use this to compute nutrient density per kg
    nc = nc.groupby(['fbs_item_code', 'fbs_item'])[['pop_kg/day', 'pop_kcal/day', 'pop_g_protein/day']].sum().reset_index()
    nc['kcal/kg'] = nc['pop_kcal/day'] / nc['pop_kg/day']
    nc['g_protein/kg'] = nc['pop_g_protein/day'] / nc['pop_kg/day']

    # Output
    nc[['fbs_item_code', 'fbs_item', 'kcal/kg', 'g_protein/kg']].to_csv(paths.interim/'nutrient_comp_fbs_items.csv', index=False)

    # Adjust food supplies to ignore losses ****************************************************************************

    # Pivot on element, convert to snake case
    fbs = fbs[fbs['fbs_item'] != 'Population']
    fbs = s_pivot(fbs, idx=['country_code', 'country', 'fbs_item_code', 'fbs_item'],
                     cols=['element'], vals=['value']).pipe(snake_case_cols)
    fbs = fbs.rename(columns={'domestic_supply_quantity': 'domestic_supply_1000_mt',
                              'production': 'production_1000_mt',
                              'import_quantity': 'imports_1000_mt',
                              'export_quantity': 'exports_1000_mt',
                              'feed': 'feed_1000_mt',
                              'food_supply_quantity_kg/capita/yr': 'supply_kg/cap/yr_raw',
                              'food_supply_kcal/capita/day': 'supply_kcal/cap/day_raw',
                              'protein_supply_quantity_g/capita/day': 'supply_g_pro/cap/day_raw'})
    fbs = fbs.fillna(0)

    # Merge w/population and nutrient density
    # Inner merges drop countries/items with no data
    fbs = s_merge(fbs, pop, on=['country_code', 'country'], how='inner', validate='m:1')
    fbs = s_merge(fbs, nc, on=['fbs_item_code', 'fbs_item'], how='inner', validate='m:1')

    # Compute nutrient losses
    fbs['losses_kg/cap/yr'] = fbs['losses'] / fbs['population'] * 1000000 # FBS expresses losses in 1000 mt
    fbs['losses_kcal/cap/day'] = fbs['losses_kg/cap/yr'] / 365 * fbs['kcal/kg']
    fbs['losses_g_pro/cap/day'] = fbs['losses_kg/cap/yr'] / 365 * fbs['g_protein/kg']

    # Adjust food supplies to ignore losses
    # Where possible, adjust kcal and protein by the same relative amount as kg,
    # otherwise multiply kcal and protein by nutrient density
    fbs['supply_kg/cap/yr'] = fbs['supply_kg/cap/yr_raw'] + fbs['losses_kg/cap/yr']

    fbs['losses_scaling_factor'] = np.where(fbs['supply_kg/cap/yr_raw'] != 0,
                                            fbs['supply_kg/cap/yr'] / fbs['supply_kg/cap/yr_raw'],
                                            np.nan) # Edge case

    fbs['supply_kcal/cap/day'] = np.where(fbs['losses_scaling_factor'].notna(),
                                            fbs['supply_kcal/cap/day_raw'] * fbs['losses_scaling_factor'],
                                            fbs['supply_kcal/cap/day_raw'] + fbs['losses_kcal/cap/day'])

    fbs['supply_g_pro/cap/day'] = np.where(fbs['losses_scaling_factor'].notna(),
                                                fbs['supply_g_pro/cap/day_raw'] * fbs['losses_scaling_factor'],
                                                fbs['supply_g_pro/cap/day_raw'] + fbs['losses_g_pro/cap/day'])

    # Compare FBS against item params and countries list ***************************************************************

    # DIAGNOSTIC: check for missing items
    print('Check for missing FBS items in item parameters:')
    fbs_items = fbs[['fbs_item_code', 'fbs_item']].drop_duplicates()
    s_merge(fbs_items, item_params, on=['fbs_item_code', 'fbs_item'], how='left',
            validate='1:1', left_name='fbs_items', right_name='item_params')

    # DIAGNOSTIC: check for missing countries
    print('Check for missing FBS countries in countries file; China is excluded to avoid double-counting w/sub-regions:')
    fbs_countries = fbs[['country_code', 'country']].drop_duplicates()
    s_merge(fbs_countries, countries, on=['country_code', 'country'], how='left',
            validate='1:1', left_name='fbs_countries', right_name='countries', beep=False)

    # Drop countries with no match in countries file
    fbs = s_merge(fbs, countries, on=['country_code', 'country'], how='inner')

    # Output ***********************************************************************************************************
    fbs = fbs[['country_code', 'country', 'fbs_item_code', 'fbs_item', 'domestic_supply_1000_mt', 'production_1000_mt',
               'imports_1000_mt', 'exports_1000_mt', 'feed_1000_mt', 'supply_kg/cap/yr', 'supply_kcal/cap/day', 'supply_g_pro/cap/day']]

    fbs.to_csv(paths.interim/'fao_fbs_avg_loss_unadj.csv', index=False)

    """
    # Compare old (excel-based) and new fbs files
    df_old = pd.read_csv(paths.interim/'archive/fao_fbs_avg_loss_unadj_from_excel_2019_05_29.csv')
    df_new = pd.read_csv(paths.interim/'fao_fbs_avg_loss_unadj.csv')
    index_cols = ['country_code', 'country', 'fbs_item_code', 'fbs_item']
    compare = compare_dfs(df_old, df_new, index_cols, threshold=0.000000001)
    compare.to_csv(paths.diagnostic/ 'compared/fbs.csv', index=False)
    """