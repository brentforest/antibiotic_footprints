import pandas as pd
import paths
from utilities import *

pd.options.display.max_columns = 999
pd.options.mode.chained_assignment = None


def fbs_item_production():

    # Input ************************************************************************************************************

    fbs_prod = pd.read_csv(paths.interim/'fao_fbs_avg_loss_unadj.csv').pipe(snake_case_cols)[
        ['country_code', 'country', 'fbs_item_code', 'fbs_item', 'production_1000_mt']]

    # ******************************************************************************************************************

    # Filter out population data
    fbs_prod = fbs_prod[fbs_prod['fbs_item'] != 'Population']

    fbs_prod['mt_production'] = fbs_prod['production_1000_mt']*1000
    fbs_prod.drop(columns='production_1000_mt', inplace=True)

    fbs_prod.to_csv(paths.interim/'fbs_item_production.csv', index=False)

    # TODO: Should blank production values need to be removed? I think this is already handled downstream...

