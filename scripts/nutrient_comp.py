import pandas as pd
import numpy as np
import paths
from utilities import *

def nutrient_comp():

    # Input ************************************************************************************************************

    fbs = pd.read_csv(paths.interim/'nutrient_comp_fbs_items.csv')
    spl = pd.read_excel(paths.input/'nutrient_comp_custom_items.xlsx', sheet_name='nutrient_comp')

    # ******************************************************************************************************************

    # Average and s_pivot nutrient comp for special items
    spl = spl.groupby(['fbs_item_code', 'fbs_item', 'nutrient'])['amount_per_kg_primary'].mean().reset_index()
    spl = s_pivot(spl, idx=['fbs_item_code', 'fbs_item'], cols=['nutrient'], vals=['amount_per_kg_primary'])
    spl.rename(columns={'kcal': 'kcal/kg', 'g_protein': 'g_protein/kg', 'mcg_b12': 'mcg_b12/kg' }, inplace=True)

    # Append w/fbs items
    cols = spl.columns
    nutrient_comp = pd.concat([spl, fbs], sort=False)[cols]
    nutrient_comp.to_csv(paths.interim/'nutrient_comp.csv', index=False)