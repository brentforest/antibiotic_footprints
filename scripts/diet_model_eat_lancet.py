import pandas as pd
import numpy as np
import paths
from utilities import *

pd.options.display.max_columns = 999
pd.options.mode.chained_assignment = None


def diet_model_eat_lancet():

    # Input **********************************************************************************************************

    # TODO: put extraction rates in baseline diet model?
    dm_lancet = pd.read_csv(paths.input/'eat_lancet/eat_lancet_diet.csv')
    dm_baseline = pd.read_csv(paths.interim/'diet_model_baseline.csv')

    extr_rates = (pd.read_csv(paths.interim / 'fao_extraction_rates.csv')
        [['country_code', 'fao_item_code', 'extr_rate_mt/mt']])
    extr_rates_world = (pd.read_csv(paths.interim / 'fao_extraction_rates_world.csv')
        [['fao_item_code', 'extr_rate_world_mt/mt']])

    matched = (pd.read_csv(paths.input/'eat_lancet/eat_lancet_fbs_item_match.csv')
        [['lancet_item', 'fbs_item_code', 'fao_item_code']])

    # ******************************************************************************************************************

    # Merge lancet w/matched, baseline diet, and extraction rates
    dm = (dm_lancet
          .merge(matched, on='lancet_item', how='left')
          .pipe(s_merge, dm_baseline, on='fbs_item_code', how='inner') # Ony keep items that are in both eat lancet and baseline
          #.merge(dm_baseline, on='fbs_item_code', how='inner', validate=True)
          .merge(extr_rates, on=['country_code', 'fao_item_code'], how='left')
          .merge(extr_rates_world, on='fao_item_code', how='left'))

    # Choose first non-null extraction rate value, assign as 'final'
    cols = ['extr_rate_mt/mt', 'extr_rate_world_mt/mt']
    dm['extr_rate_final'] = choose_first_notna(dm[cols], default_value=1)

    # Convert processed items back to primary equivalents
    # NOTE: this should be applied to mass only, and NOT KCAL.
    # If EAT Lancet says to eat 14 g and 30 kcal of beef,
    # this might equate to producing 18 g beef carcass, but the amount of kcal consumed should remain constant.
    dm['lancet_g/cap/day'] /= dm['extr_rate_final']

    # Allocate quantities of lancet items over FBS items based on loss-adjusted mass
    # NOTE: the caloric density provided by EAT-Lancet is different from that provided by FBS
    dm['bl_loss_adj_kg/cap/yr_by_lancet_item'] = \
        dm.groupby(['country_code', 'diet', 'lancet_item'])['baseline_loss_adj_kg/cap/yr'].transform('sum')
    dm['%_allocated_to_fbs_item'] = dm['baseline_loss_adj_kg/cap/yr'] / dm['bl_loss_adj_kg/cap/yr_by_lancet_item']
    dm['loss_adj_kg/cap/yr'] = dm['%_allocated_to_fbs_item'] * (dm['lancet_g/cap/day'] / 1000 * 365)
    dm['loss_adj_kcal/cap/day'] = dm['%_allocated_to_fbs_item'] * dm['lancet_kcal/cap/day']

    # Reverse (add back in) food losses
    dm['kg/cap/yr'] = dm['loss_adj_kg/cap/yr'] / dm['%_after_losses_postharvest_to_home']
    dm['kcal/cap/day'] = dm['loss_adj_kcal/cap/day'] / dm['%_after_losses_postharvest_to_home']

    dm['scaling_method'] = 'eat_lancet'

    dm.to_csv(paths.interim/'diet_model_eat_lancet.csv', index=False)

