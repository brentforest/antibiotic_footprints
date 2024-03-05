import numpy as np
import pandas as pd
from utilities import *

pd.options.display.max_columns = 999
pd.options.mode.chained_assignment = None

OUTPUT_PATH = '../data/output/summary_tables/'

def summarize_by_group(df, attributes=[], groupby=''):
# Generate table of summary statistics by group
# attributes refers to one or more coloumns with numeric data


    # If input data are in wide format, convert to long and filter attributes
    df = df.melt(id_vars=groupby, var_name='attribute', value_name='value')
    df = s_filter(df, col='attribute', list=attributes)
    df['value'] = df['value'].astype(float)

    df = df.groupby(groupby + ['attribute']).describe(percentiles=[.05, .25, .5, .75, .95], include='all').reset_index()

    # df has two header rows; flatten to just one and rename columns
    # https://towardsdatascience.com/how-to-flatten-multiindex-columns-and-rows-in-pandas-f5406c50e569
    df.columns = [''.join(col) for col in df.columns.values]
    df.columns = df.columns.str.replace('value','')
    df = df.rename(columns={'count': 'n'})

    # Sort
    #df = s_categorical_sort(df, col='season', sort_order=SEASON_ORDER)
    df = df.sort_values(by='attribute')

    if groupby==['helper_col']:
        df = df.drop(columns='helper_col')

    return df

# Main method
def summary_tables():
    # Input ****************************************************************************************************************

    # diet footprints by scenario
    df = pd.read_csv('../data/output/diet_footprints_by_country_diet.csv')

    # item footprints
    fp = pd.read_csv('../data/output/per_kg_edible_wt_footprints_by_species.csv')[['item', 'footprint_type', 'footprint']]

    # **********************************************************************************************************************

    # Filter/rename
    df = df.rename(columns={'diet': 'scenario', 'income_class': 'income_group',
                                  'attribute': 'footprint_type', 'value': 'footprint'}) \
        .pipe(s_filter, col='footprint_type', list=['kg_co2e_total', 'mg_abx_total']) \
        .replace({'kg_co2e_total': 'kg CO2e/capita/year', 'mg_abx_total': 'mg antibiotics/capita/year'})

    # Summarize by scenario
    summarize_by_group(df[['scenario', 'footprint_type', 'footprint']],groupby=['scenario', 'footprint_type']) \
        .sort_values(by=['footprint_type', 'scenario']) \
        .to_csv(OUTPUT_PATH + 'diet_footprints_by_scenario_summary.csv', index=False)

    # Summarize by income class
    s_filter(df, col='scenario', list=['baseline'])[['income_group', 'footprint_type', 'footprint']] \
        .pipe(summarize_by_group, groupby=['income_group', 'footprint_type']) \
        .sort_values(by=['footprint_type', 'income_group']) \
        .to_csv(OUTPUT_PATH + 'diet_footprints_by_income_summary.csv', index=False)

    # Item footprints
    fp = summarize_by_group(fp, groupby=['item', 'footprint_type']).sort_values(by=['item', 'footprint_type'])
    fp.to_csv(OUTPUT_PATH + 'per_kg_edible_wt_footprints_summary.csv', index=False)
