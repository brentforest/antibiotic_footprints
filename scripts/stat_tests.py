import numpy as np
import pandas as pd
import math
import paths
import winsound
from utilities import *
from utilities_stats import *

pd.options.display.max_columns = 999
pd.options.mode.chained_assignment = None

# Main method
def stat_tests():

    # Input ************************************************************************************************************

    fp = pd.read_csv(paths.output / 'diet_footprints_by_country_diet.csv')

    # ******************************************************************************************************************

    # Filter
    fp = s_filter(fp, col='attribute', list=['mg_abx_total', 'kg_co2e_total'])
    fp = s_filter(fp, col='diet', list=['baseline'])

    # Convert from long to wide-form dataframe
    fp = fp.pivot_table(index=['country', 'region', 'income_class', 'diet'], columns='attribute', values='value').reset_index()
    corr = test_corr(fp, x='mg_abx_total', y='kg_co2e_total')
    print(corr)

    classes = fp['income_class'].drop_duplicates().tolist()
    classes.remove('Unclassified')

    for inc in classes:
        print('\n',inc)
        df = s_filter(fp, col='income_class', list=[inc])
        corr = test_corr(df, x='mg_abx_total', y='kg_co2e_total')
        print(corr)


