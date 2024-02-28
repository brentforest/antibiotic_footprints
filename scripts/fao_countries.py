import pandas as pd
import gc # Garbage collection module, to save memory
import numpy as np
import paths
from datetime import datetime
from utilities import *

pd.options.display.max_columns = 999
pd.options.mode.chained_assignment = None

# Main method
def fao_countries():

    # Input ************************************************************************************************************

    run_params = pd.read_excel(paths.params, sheet_name='parameters', skiprows=1).set_index('parameter')

    countries = pd.read_excel(paths.input / 'fao/fao_countries.xlsx', sheet_name='fao_countries')
    countries_renamed = pd.read_csv(paths.input / 'fao/fao_countries_renamed_for_2022.csv')
    wb = pd.read_excel(paths.input / 'world_bank_income_classification.xlsx', sheet_name='countries')[
        ['country_iso_code', 'income_class']]

    # Merge World Bank income class ************************************************************************************

    # "many:1" merge since countries has multiple rows w/blank iso codes
    countries = s_merge(countries, wb, on='country_iso_code', how='left', validate='m:1',
                        left_name='countries', right_name='world bank income classes', beep=False)

    countries['income_class'] = countries['income_class'].fillna('Unclassified')

    # Rename countries for 2022 ****************************************************************************************

    countries = countries.merge(countries_renamed, on='country_code', how='left', validate='1:1')
    countries['country'] = choose_first_notna(countries[['country_renamed', 'country']], default_value='ERROR')
    countries.drop(columns=['country_renamed'], inplace=True)

    countries.to_csv(paths.interim/'fao_countries.csv', index=False)