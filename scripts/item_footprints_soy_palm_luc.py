import pandas as pd
import numpy as np
import paths
from utilities import *

pd.options.display.width = 250


# Main method
def item_footprints_soy_palm_luc():

    # Input
    countries = pd.read_csv(paths.interim/'fao_countries.csv')[['country_code', 'country', 'gleam_country', 'gleam_region']]
    fp = pd.read_csv(paths.input/'ghge/soy_palm_luc/soy_palm_luc_co2_per_ha.csv')
    processed_items = pd.read_csv(paths.input/'ghge/soy_palm_luc/soy_palm_processed_items.csv')
    yield_ha = pd.read_csv(paths.input/'ghge/soy_palm_luc/soy_palm_yield_per_ha.csv')

    # Average crop yields over 2011-2013
    index_cols = ['country_code', 'country', 'item_code', 'item']
    yield_ha = yield_ha[index_cols + ['value']]\
        .groupby(index_cols).mean() \
        .reset_index().rename(columns={'value': 'hg/ha'})

    # Match crop CO2/ha with FAO countries, crop yield/ha, and allocation fractions
    fp = fp.merge(countries, on='gleam_country', how='left')\
        .merge(yield_ha, on=['item_code', 'item', 'country_code', 'country'], how='left')\
        .merge(processed_items, on=['item_code', 'item'], how='left')

    # Convert hg/ha to kg/ha
    fp['kg/ha'] = fp['hg/ha'] / 10

    # Convert mt CO2/ha to kg CO2/ha
    fp['kg_co2/ha'] = fp['mt_co2/ha'] * 1000

    # Convert kg CO2/ha to kg CO2/kg using yield/ha
    fp['kg_co2/kg'] = fp['kg_co2/ha'] / fp['kg/ha']
    fp['footprint_type'] = 'kg_co2_luc_human_palm_soy'

    # Apply economic allocation
    fp['kg_co2/kg'] = fp['kg_co2/kg'] / fp['product_fraction'] * fp['value_fraction']
    fp['footprint'] = fp['kg_co2/kg']

    # Output
    fp.to_csv(paths.interim/'item_footprints/item_footprints_soy_palm_luc.csv', index=False)