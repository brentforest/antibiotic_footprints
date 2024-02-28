import numpy as np
import pandas as pd
import gc # Garbage collection module, to save memory
import math
import paths
import winsound
from datetime import datetime
from utilities_figs import *
from utilities import *

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.transforms as mtrans
import matplotlib.patches as mpatches
from pandas.api.types import CategoricalDtype

pd.options.display.max_columns = 999
pd.options.mode.chained_assignment = None

SHOW_FIGS = False

def line_plot(df):

    x = 'country_iso_code'

    fig, ax = plt.subplots(nrows=1, ncols=1, figsize=(16, 5), dpi=80)

    df.plot.line(ax=ax, x=x, y='supply_side_kg_tiseo')
    df.plot.line(ax=ax, x=x, y='supply_side_kg')

    #plt.xticks(np.arange(0, 50, 5))

    #plt.xticks(x, df[x].tolist()[::2], rotation='vertical')
    #ax.set_xticks(df[x].values[::2])
    #ax.set_xticklabels(x[::2], rotation=45)

    show_save_plot(show=SHOW_FIGS, path='../figures/', filename='abx_supply_side_compare')


# Main method
def supply_side_compare():

    # Input ************************************************************************************************************

    supply = pd.read_csv(paths.output / 'by_coo_only/supply_side_footprints_by_country_item.csv')
    tiseo = pd.read_csv(paths.input / 'antibiotic_use/abu_by_producers_2017_to_compare.csv', skiprows=1)[
        ['country_iso_code', 'mg_abx_use_by_producers']]

    countries = pd.read_csv(paths.interim / 'fao_countries.csv')[['country_code', 'country_iso_code']]


    # ******************************************************************************************************************

    # Filter to abx only, terrestrial meat only since we're comparing to Tiseo et al.
    supply = s_filter(supply, col='footprint_type', list=['mg_abx_total'])
    supply = s_filter(supply, col='type', excl_list=['plant', 'a_animal'])
    supply = s_filter(supply, col='fbs_item', excl_list=['Mutton & Goat Meat'])

    # Groupby by country; we're not interested individual items
    supply = supply.groupby(['country_code', 'country'])['supply_side_total'].sum().reset_index()

    supply = s_merge(supply, countries, on='country_code', how='left')\
        .pipe(s_merge, tiseo, on='country_iso_code', how='left')

    supply['mg_abx_use_by_producers'] *= 1000000
    supply['supply_side_total'] *= 1000000
    supply = supply.rename(columns={'mg_abx_use_by_producers': 'supply_side_kg_tiseo', 'supply_side_total': 'supply_side_kg'})

    supply = supply[['country_iso_code', 'country', 'supply_side_kg_tiseo', 'supply_side_kg']]
    supply['diff'] = supply['supply_side_kg'] - supply['supply_side_kg_tiseo']
    supply['%_diff'] = supply['diff'] / supply['supply_side_kg_tiseo']

    supply.to_csv(paths.diagnostic / 'supply_side_compared.csv', index=False)

    # Tried plotting it in Python but found it easier to just do it in Excel (see separate excel file)
    line_plot(supply)