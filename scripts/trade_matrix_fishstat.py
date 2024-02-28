import pandas as pd
import gc # Garbage collection module, to save memory
import numpy as np
import paths
from datetime import datetime
from utilities import *

pd.options.display.max_columns = 999
pd.options.mode.chained_assignment = None

startTime = datetime.now()


def rename_filter_cols(tm, fishstat_to_isscfc, isscfc_to_isscaap):

    tm.rename(columns={
        'Reporting country (Name)': 'fishstat_country',
        'Partner country (Name)': 'fishstat_coo',
        'Commodity (Name)': 'fishstat_commodity',
        '[2019]': 'imports_mt/yr'}, inplace=True
    )
    tm = tm[tm['Trade flow (Name)'] == 'Imports']
    tm = tm[['fishstat_country', 'fishstat_coo', 'fishstat_commodity', 'imports_mt/yr']]

    fishstat_to_isscfc.rename(columns={
        'FAO_CODE': 'isscfc_code',
        'NAME.EN': 'fishstat_commodity'}, inplace=True
    )
    fishstat_to_isscfc = fishstat_to_isscfc[['fishstat_commodity', 'isscfc_code']]

    isscfc_to_isscaap.rename(columns={
        'Code': 'isscfc_code',
        'ISSCAAP': 'isscaap_code'}, inplace=True
    )
    isscfc_to_isscaap = isscfc_to_isscaap[['isscfc_code', 'isscaap_code']]

    return (tm, fishstat_to_isscfc, isscfc_to_isscaap)


# Main method
def trade_matrix_fishstat():

    # Input ************************************************************************************************************

    tm = pd.read_csv(paths.input / 'fishstat/trade/fishstat_trade_matrix_2019.csv')

    fishstat_to_isscfc = pd.read_csv(paths.input / 'fishstat/trade/fishstat_trade_commodity_metadata.csv', skiprows=2)
    isscfc_to_isscaap = pd.read_csv(paths.input / 'fishstat/trade/isscfc_to_isscaap.csv', skiprows=2)
    isscaaap_to_fbs = pd.read_csv(paths.input / 'fishstat/isscaap_to_fbs.csv', skiprows=2)[[
        'isscaap_code', 'fbs_item_code', 'fbs_item']]

    fao_countries = pd.read_csv(paths.interim / 'fao_countries.csv')[['fishstat_country', 'country', 'country_code']]

    # ******************************************************************************************************************

    (tm, fishstat_to_isscfc, isscfc_to_isscaap) = rename_filter_cols(tm, fishstat_to_isscfc, isscfc_to_isscaap)

    # Match Fishstat items to FBS items and item codes
    fs_to_fbs = s_merge(fishstat_to_isscfc, isscfc_to_isscaap, on='isscfc_code', how='left', validate='1:m').dropna()
    fs_to_fbs = s_merge(fs_to_fbs, isscaaap_to_fbs, on='isscaap_code', how='left', validate='m:m')
    fs_to_fbs = fs_to_fbs[['fishstat_commodity', 'fbs_item_code', 'fbs_item']]
    tm = s_merge(tm, fs_to_fbs, on='fishstat_commodity', how='left', validate='m:m')
    tm.to_csv(paths.diagnostic/'fishstat_trade_matrix_fbs_matched.csv', index=False)

    # Match Fishstat countries to FAO country names and codes
    # TODO: As shown in diagnostic file, there are a handful of tiny island nations that don't have matches, also cote d'ivoire because of unrecognized characters
    tm = tm.merge(fao_countries, on='fishstat_country', how='left', validate='m:1', indicator='country_match')
    fao_countries.rename(columns={'fishstat_country': 'fishstat_coo', 'country':'coo', 'country_code':'coo_code'}, inplace=True)
    tm = tm.merge(fao_countries, on='fishstat_coo', how='left', validate='m:1', indicator='coo_match')
    tm.to_csv(paths.diagnostic / 'fishstat_trade_matrix_country_matched.csv', index=False)
    tm = tm.drop(columns=['fishstat_country', 'fishstat_coo', 'country_match', 'coo_match'])

    #Drop items other than freshwater fish and crustaceans
    # TODO: add other FBS items if they become relevant for other footprint types
    tm = tm[tm['fbs_item'].isin(['Freshwater Fish', 'Crustaceans'])]

    # Group by countries and FBS item
    index_cols = ['country_code', 'country', 'coo_code', 'coo', 'fbs_item_code', 'fbs_item']
    tm = tm.groupby(index_cols)['imports_mt/yr'].sum().reset_index()

    # Output
    tm.to_csv(paths.interim/'fishstat_trade_matrix_fw_crust.csv', index=False)