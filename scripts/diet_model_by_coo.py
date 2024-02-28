import numpy as np
import pandas as pd
import gc # Garbage collection module, to save memory
import paths
import winsound
from datetime import datetime
from utilities import *
from utilities_diet_climate import *

pd.options.display.max_columns = 999
pd.options.mode.chained_assignment = None

def domestic(dm_):
# Compute % domestic based on FBS

    # Make a copy to avoid altering original dataframe
    dm = dm_.copy()

    dm['coo'] = dm['country']
    dm['coo_code'] = dm['country_code']
    dm['%_from_coo'] = 1 - dm['%_imported'] #total % imported is from FBS, not trade matrix

    # Drop NaN and zero values
    dm = dm[(dm['%_from_coo'].notna()) & (dm['%_from_coo'] != 0)]
    return dm


def world(dm_):
# Compute % from world avg., i.e., imported items with no coo data in the trade matrix

    # Make a copy to avoid altering original dataframe
    dm = dm_.copy()

    # If item is imported but has no import data from trade matrix, associate % imported with 'World'
    dm['coo'] = 'World'
    dm['coo_code'] = 0
    dm.loc[(dm['%_imported'] > 0) & (dm['sum_imports_mt/yr'] <= 0), '%_from_coo'] = dm['%_imported']

    # Drop NaN and zero values
    dm = dm[(dm['%_from_coo'].notna()) & (dm['%_from_coo'] != 0)]
    return dm


def imports(dm_, tm):
# Compute % from coo

    # Make a copy to avoid altering original dataframe
    dm = dm_.copy()

    # Merge dm w/trade matrix on item and country; drop duplicates
    dm = pd.merge(dm, tm, on=['fbs_item_code', 'country_code'], how='left', suffixes=('', '_x'))
    dm.drop(columns=list(dm.filter(regex='_x')), inplace=True)

    # % from coo = % imported from coo * % imported
    # Note that % imported is calculated from FBS data and is not specific to COO;
    # We use it because there are fewer assumptions involved compared to summing imports by COO
    dm['%_from_coo'] = (dm['imports_mt/yr'] / dm['sum_imports_mt/yr']) * dm['%_imported']

    # Drop NaN and zero values
    dm = dm[(dm['%_from_coo'].notna()) & (dm['%_from_coo'] != 0)]
    return dm


# Main method
def diet_model_by_coo():

    # Input ************************************************************************************************************

    dm = (pd.read_csv(paths.output/'diet_model_by_country_diet_item.csv')
          [['country_code', 'country', 'diet', 'fbs_item_code', 'fbs_item',
            'output_group', 'type', 'kg/cap/yr', 'loss_adj_kcal/cap/day', '%_imported']])
    tm = pd.read_csv(paths.interim/'fao_trade_matrix_avg_primary.csv').pipe(snake_case_cols)
    tmf = pd.read_csv(paths.interim/'fishstat_trade_matrix_fw_crust.csv')
    income_class = pd.read_csv(paths.interim/'fao_countries.csv')[['country_code', 'country', 'income_class']]

    # ******************************************************************************************************************

      # Rename trade matrix columns
    tm.rename(columns={'imports_primary_equivalent_mt/yr': 'imports_mt/yr'}, inplace=True)

    # Combine fao trade matrix with fishstat trade matrix
    tm = pd.concat([tm, tmf], sort=False)

    # Diagnostic: Check for null %_imported values
    if dm['%_imported'].isna().any():
        winsound.Beep(400, 400)
        print("ERROR: NULL VALUE FOUND IN '%_imported':")
        print(dm[dm['%_imported'].isna()])

    # Diagnostic: Sum total kg before allocating by coo; referenced below
    total_kg = dm['kg/cap/yr'].sum()

    # Replace NaN values with zero - prevents bug when imports_1000_mt is null # TODO: is this still needed?
    dm = dm.fillna(0)

    # Compute total imports by item in the trade matrix, this is used for imports() and world()
    # Note: sum of trade matrix imports should be similar to total imports in the FBS;
    # Values are not identical because of missing data and limitations in our conversions to primary equivalent
    tm_grouped = tm.groupby(['country_code', 'fbs_item_code'])['imports_mt/yr'].sum().reset_index()
    tm_grouped.rename(columns={'imports_mt/yr': 'sum_imports_mt/yr'}, inplace=True)
    dm = pd.merge(dm, tm_grouped, on=['country_code', 'fbs_item_code'], how='left')

    # Replace NaN values with zero after merge - necessary for domestic, imports, and world functions
    # Drop data for items w/zero or negative (e.g., Japan oats) quantity in the diet
    # Note: in the Nature version, only zero values were dropped; negative values were incorrectly allowed to stay
    dm = dm.fillna(0)
    dm = dm[dm['kg/cap/yr'] > 0]

    print('Modeling diets by country of origin\n')

    # Compute % domestic, % from coo, and % from world avg. (i.e., imported items w/no coo data in the trade matrix);
    # TODO: where is the "unnamed" column coming from? is that the index? if so, how to remove?
    dm_domestic = domestic(dm)
    dm_imports = imports(dm, tm)
    dm_world = world(dm)
    dm = pd.concat([dm_domestic, dm_imports, dm_world], sort=False)

    # Define columns
    index_cols = ['country_code','country','diet','fbs_item_code','fbs_item','output_group','type',
                  'coo_code','coo','%_imported']

    # Sum %_from_coo where the same item has multiple coo, i.e., when a country imports to itself
    dm = dm.groupby(index_cols + ['kg/cap/yr', 'loss_adj_kcal/cap/day'])['%_from_coo'].sum().reset_index()

    # Multiply % by coo by quantities of each item in each country-diet pair
    dm['kg/cap/yr_by_coo'] = dm['kg/cap/yr'] * dm['%_from_coo']
    dm['loss_adj_kcal/cap/day_by_coo'] = dm['loss_adj_kcal/cap/day'] * dm['%_from_coo']

    # Add flag for domestic v. imported - useful for things like pie charts
    dm['origin'] = np.where(dm['coo_code'] == dm['country_code'],'domestic','imported')

    # Re-order and filter columns
    dm = dm[index_cols + ['kg/cap/yr', 'loss_adj_kcal/cap/day', 'origin', '%_from_coo',
                          'kg/cap/yr_by_coo', 'loss_adj_kcal/cap/day_by_coo']]

    # Add income class
    dm = s_merge(dm, income_class, on=['country_code', 'country'], how='left', validate='m:1')
    income_class = income_class.rename(columns={'country_code': 'coo_code', 'country': 'coo', 'income_class': 'coo_income_class'})
    dm = s_merge(dm, income_class, on=['coo_code', 'coo'], how='left', validate='m:1')

    # Output diet model
    # To keep the file size manageable we don't include all of the columns here
    dm[['country_code', 'country', 'diet' ,'fbs_item_code', 'fbs_item', 'output_group', 'type', 'coo_code', 'coo', 'origin', 'kg/cap/yr_by_coo']] \
        .to_csv(paths.output/'diet_model_by_country_diet_item_coo.csv', index=False)

    # Sum by output group and domestic vs. imports, baseline diet only
    # This makes for a much more manageable file size
    dm_by_group_origin = dm[dm['diet'] == 'baseline']
    dm_by_group_origin = dm_by_group_origin.groupby(['country_code', 'country', 'diet', 'type', 'output_group', 'origin'])[[
        'kg/cap/yr_by_coo', 'loss_adj_kcal/cap/day_by_coo']].sum().reset_index()
    dm_by_group_origin.to_csv(paths.output/'diet_model_by_country_diet_output_group_origin_baseline_only.csv', index=False)

    # Diagnostics ******************************************************************************************************

    # Diagnostic: sum of kg/cap/day in diet model by coo should match sum in diet model
    print("Diagnostic check: compare total kg/cap/yr by COO with kg/cap/yr before allocating by COO; values should be very close")
    print("Minor differences may be explained by edge cases")
    print("Total by country of origin:", dm['kg/cap/yr_by_coo'].sum())
    print("Total:", total_kg, '\n')

    # Diagnostic: Group and sum diet model by item
    # Note: be sure to sum kg/cap/yr_by_coo, and not kg/cap/yr; the latter is repeated for each coo!
    # Check if summed %_from_coo = 100% for all items; control for rounding errors
    dm_by_item = dm.groupby(['country_code','country','diet','fbs_item_code','fbs_item',
                             'output_group','type'])[['kg/cap/yr_by_coo','%_from_coo']].sum().reset_index()
    # TODO: refactor this if-statement and throw an exception
    if (round(dm_by_item['%_from_coo'],9)==1).all() == False:
        print('ERROR: % from country of origin != 1')
        winsound.Beep(400,400)
    dm_by_item.to_csv(paths.diagnostic/'diet_model_by_country_diet_item_coo_item_total.csv', index=False)
