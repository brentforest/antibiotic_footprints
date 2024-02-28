import pandas as pd
import numpy as np
import paths
from utilities import *
from utilities_diet_climate import *

pd.options.display.max_columns = 999
pd.options.mode.chained_assignment = None

COUNTRY_VARS = ['region', 'income_class', 'oecd']


def combine_results(fp_by_coo, fp_bootstrap):

    # Compute differences between centiles
    # This must be done BEFORE combining footprint types, see explanation below.
    fp_bootstrap['centile_up'] = fp_bootstrap['centile_75'] - fp_bootstrap['centile_50']
    fp_bootstrap['centile_down'] = fp_bootstrap['centile_50'] - fp_bootstrap['centile_25']

    # Concat by_coo and bootstrap footprint results
    fp_bootstrap.rename(columns={'centile_50': 'diet_footprint'}, inplace=True)
    fp = pd.concat([fp_by_coo, fp_bootstrap], sort=False)

    # Combine footprint types (e.g., blue WF + pond blue WF, GHG + LUC GHG)
    # ***
    # Note: For some output groups (e.g., vegetable oils and soy), this combines data from by_coo and bootstrap;
    # by_coo data are added to the median bootstrap value, but NOT to the 25th and 75th centiles;
    # for this reason centiles should be dropped at this point, refer instead to centile_down and centile_up.
    # ***
    # Note: this is likely not the first time footprint types have been grouped; see item_footprints_grouped.
    index_cols = ['country_code', 'country', 'diet', 'output_group'] # Don't include "type" here unless it's included in bootstraps
    results_cols = ['centile_up', 'diet_footprint', 'centile_down']
    fp = combine_footprint_types(fp, index_cols, results_cols, keep_originals=True).drop(columns=['centile_25', 'centile_75'])
    check_duplicate_indices(fp, index_cols + ['footprint_type'])

    # Rename cols
    fp.rename(columns={'footprint_type': 'attribute', 'diet_footprint': 'value'}, inplace=True)

    # Concat diet model to footprints
    # cols = fp.columns
    #fp = pd.concat([fp, dm_by_group])[cols]

    return fp


def group_by_country_diet(fp):
# Group by country diet, compare to baseline

    # Group
    fp_by_cd = fp.groupby(['country_code', 'country', 'diet', 'attribute'] + COUNTRY_VARS).sum(numeric_only=True).reset_index()

    # Compare to baseline
    index_cols = ['country_code', 'attribute']
    fp_baseline = fp_by_cd[fp_by_cd['diet'] == 'baseline']
    fp_by_cd = fp_by_cd.merge(fp_baseline[index_cols + ['value']], on=index_cols, how='left', suffixes=('', '_baseline'))
    fp_by_cd['diff_baseline'] = fp_by_cd['value'] - fp_by_cd['value_baseline']
    fp_by_cd['%_diff_baseline'] = fp_by_cd['diff_baseline'] / fp_by_cd['value_baseline']

    # Compare to baseline adjusted
    index_cols = ['country_code', 'attribute']
    fp_typical = fp_by_cd[fp_by_cd['diet'] == 'baseline_adjusted']
    fp_by_cd = fp_by_cd.merge(fp_typical[index_cols + ['value']], on=index_cols, how='left', suffixes=('', '_baseline_adj'))
    fp_by_cd['diff_baseline_adj'] = fp_by_cd['value'] - fp_by_cd['value_baseline_adj']
    fp_by_cd['%_diff_baseline_adj'] = fp_by_cd['diff_baseline_adj'] / fp_by_cd['value_baseline_adj']

    return fp_by_cd


def group_sum(fp, index_cols):
# group results and sum over population

    fp_g = fp.copy()

    # Whole country footprints
    fp_g['value_total'] = fp_g['value'] * fp_g['population']

    # Group and sum by index cols
    # Note: Previously we computed the average footprint, weighted by population
    # But footprint subtypes (e.g., LUC) did not add up to totals,
    # likely because this only averaged rows w/values, and there are no rows for zero values
    fp_g = fp_g.groupby(index_cols)[['value_total', 'population']].sum().reset_index()

    # Divide by population to get per capita avg
    fp_g['value_per_cap_avg'] = fp_g['value_total'] / fp_g['population']

    # OLD CODE for comparing to baseline
    """
    # compare to baseline
    fpb = fp[fp['diet']=='baseline'].copy()
    fpb.drop(columns=['diet', 'value'], inplace=True)
    fpb.rename(columns={'value/10^9': 'baseline_value/10^9'}, inplace=True)
    fp = s_merge(fp, fpb, on='footprint_type', how='left', validate='m:1')
    fp['%_change_baseline'] = (fp['value/10^9'] - fp['baseline_value/10^9']) / fp['baseline_value/10^9']
    
    fpab = fp[fp['diet'] == 'baseline_adjusted'].copy()
    fpab.drop(columns=['diet', 'value'], inplace=True)
    fpab.rename(columns={'value/10^9': 'adj_baseline_value/10^9'}, inplace=True)
    fp = s_merge(fp, fpab, on='footprint_type', how='left', validate='m:1', left_name='fp', right_name='fp_adjusted_baseline')
    fp['%_change_adj_baseline'] = (fp['value/10^9'] - fp['adj_baseline_value/10^9']) / fp['adj_baseline_value/10^9']
    """

    return fp_g


# OLD CODE: This uses weighted average change, which is wonky and hard to explain; better to work off global totals
def group_by_diet(fp, population):
# Description

    # Filter
    attributes = ['kg_co2e_total', 'l_blue_wf_total', 'l_green_wf', 'l_blue_green_wf']
    fp = fp[fp['attribute'].isin(attributes)]

    # Centiles
    fp.rename(columns={'attribute' : 'footprint_type'}, inplace=True)
    fp = fp.melt(id_vars=['country_code', 'diet', 'footprint_type'],
                 value_vars=['value', '%_diff_baseline', '%_diff_baseline_adj'], var_name='attribute')
    index_cols = ['diet', 'footprint_type', 'attribute']
    fp_centile_25 = fp.groupby(index_cols)['value'].quantile(0.25).rename('centile_25')
    fp_centile_50 = fp.groupby(index_cols)['value'].quantile(0.50).rename('centile_50')
    fp_centile_75 = fp.groupby(index_cols)['value'].quantile(0.75).rename('centile_75')

    # Weighted avg
    fp = fp.merge(population, on='country_code', how='left')
    fp_wavg = fp.groupby(index_cols).apply(wavg, 'value', 'population').rename('w_avg')

    # Concat
    fp = pd.concat([fp_centile_25, fp_centile_50, fp_centile_75, fp_wavg], axis=1).reset_index()

    # Error bars
    fp['centile_up'] = fp['centile_75'] - fp['centile_50']
    fp['centile_down'] = fp['centile_50'] - fp['centile_25']

    return fp


def results_combine():

    # Input ************************************************************************************************************

    fp_by_coo = pd.read_csv(paths.output/'by_coo_only/diet_footprints_by_origin_diet_item.csv')
    fp_bootstrap = pd.read_csv(paths.interim/'diet_footprints_bootstrap.csv').pipe(snake_case_cols)
    population = pd.read_csv(paths.interim/'fao_population.csv')
    countries = pd.read_csv(paths.interim/'fao_countries.csv')[['country_code', 'country'] + COUNTRY_VARS]

    # ******************************************************************************************************************

    # Group by_origin data by country and output group (i.e., sum over origin)
    index_cols = ['country_code', 'country', 'diet', 'type', 'output_group', 'footprint_type']
    fp_by_coo = fp_by_coo.groupby(index_cols)['diet_footprint'].sum().reset_index()

    # Combine by_coo and bootstrapped results
    fp = combine_results(fp_by_coo, fp_bootstrap)

    # Add region and other country attributes
    fp = s_merge(fp, countries, on=['country_code', 'country'], how='left', validate='m:1')

    # Output
    fp.to_csv(paths.output/'diet_footprints_by_country_diet_food_group.csv', index=False)

    # Group results by country diet
    group_by_country_diet(fp) \
        .to_csv(paths.output/'diet_footprints_by_country_diet.csv', index=False)

    # Merge w/country population so we can compute population totals
    fp = s_merge(fp, population, on='country_code', how='left')

    group_sum(fp, index_cols=['country_code', 'country', 'diet', 'output_group', 'attribute'] + COUNTRY_VARS) \
        .to_csv(paths.output / 'diet_footprints_population_total_by_country_diet_food_group.csv', index=False)

    group_sum(fp, index_cols=['region', 'diet', 'output_group', 'attribute']) \
        .to_csv(paths.output / 'diet_footprints_population_total_by_region_diet_food_group.csv', index=False)

    group_sum(fp, index_cols=['diet', 'output_group', 'attribute']) \
        .to_csv(paths.output / 'diet_footprints_population_total_global_by_diet_food_group.csv', index=False)

    group_sum(fp, index_cols=['diet', 'attribute']) \
        .to_csv(paths.output / 'diet_footprints_population_total_global_by_diet.csv', index=False)







