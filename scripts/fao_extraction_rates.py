import pandas as pd
import numpy as np
import paths
from datetime import datetime
from utilities import wavg

pd.options.display.max_columns = 999
pd.options.mode.chained_assignment = None

def fao_extraction_rates():

    # Inputs ***********************************************************************************************************

    er = pd.read_csv(paths.input/'fao_extraction_rates_raw.csv', skiprows=1)
    item_prod = pd.read_csv(paths.interim/'fao_item_production.csv')\
        [['country_code', 'fao_item_code', 'mt_production']]

    # ******************************************************************************************************************

    # Filter to extraction rates only
    er = er[er['element_name'] == 'Extr Rate (Hg/Mt)']
    er.rename(columns={'num_2011' : 'extr_rate_hg/mt'}, inplace=True)
    er['extr_rate_mt/mt'] = er['extr_rate_hg/mt'] / 10000
    er = er[['country_code', 'country', 'fao_item_code', 'fao_item', 'extr_rate_mt/mt']]

    # Remove zero values, otherwise they will be included in subsequent merges and factored in the world averages.
    # Assume a zero value indicates no data for that country-item pair.
    er = er[er['extr_rate_mt/mt']!=0]

    # Compute avg extraction rates, for use as global avg (when weighted avg is unavailable)
    er_avg = er.groupby(['fao_item_code', 'fao_item'])['extr_rate_mt/mt'].mean()\
        .rename('avg').reset_index()

    # Compute weighted avg extraction rates, for use as global avg
    # Note at least 3/4 of country-item pairs do NOT have production data (see diagnostic file for details)
    # and will instead use an unweighted avg.
    # See also the wavg function in utilities.py for details on how missing production data are handled.
    er_wavg = er.merge(item_prod, on=['country_code', 'fao_item_code'], how='left')
    er_wavg.to_csv(paths.diagnostic / 'fao_extraction_rates_before_avg.csv', index=False)
    er_wavg = er_wavg.groupby(['fao_item_code', 'fao_item'])\
        .apply(wavg, 'extr_rate_mt/mt', 'mt_production', alerts=False)\
        .rename('wavg').reset_index()

    # If a weighted avg is available, use it, otherwise use unweighted avg
    er_world = er_avg.merge(er_wavg, on=['fao_item_code', 'fao_item'], how='left')
    er_world['extr_rate_world_mt/mt'] = np.where(np.isnan(er_world['wavg']), er_world['avg'], er_world['wavg'])

    # Output results
    er.to_csv(paths.interim/'fao_extraction_rates.csv', index=False)
    er_world.to_csv(paths.interim/'fao_extraction_rates_world.csv', index=False)
