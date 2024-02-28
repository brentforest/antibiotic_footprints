import numpy as np
import pandas as pd
import gc # Garbage collection module, to save memory
import paths
import winsound
from datetime import datetime
from utilities import *
from utilities_diet_climate import *

pd.options.display.max_columns = 999
pd.options.mode.chained_assignment = None



def compute_supply_side_fp(fp):

    # Compute supply side footprint
    # For compatibility w/FBS production data, convert footprint/kg to footprint/1000 mt (1,000 mt = 1,000,000 kg)
    # Do this BEFORE grouping by output group, otherwise we group and sum per kg item footprints which is incorrect!
    # TODO: consider renaming these vars so it is clear they represent a share of the footprint, not actual domestic production or exports
    fp['footprint'] *= 1000000
    fp['supply_side_total'] = fp['footprint'] * fp['production_1000_mt']
    fp['supply_side_exports'] = fp['footprint'] * fp['exports_1000_mt']
    fp['supply_side_domestic'] = fp['supply_side_total'] - fp['supply_side_exports']

    # Edge cases w/FBS data:
    # Some countries have 0 production but >0 exports.
    # Some countries have >0 production but exports > production (e.g., Denmark, freshwater fish).
    # Presumably these case occur because countries are re-exporting imports.
    # Since domestic footprint = production fp - exports fp, this results in a <0 domestic fp.
    # In this case it would be more appropriate to set the domestic footprint to zero.
    fp['supply_side_domestic'] = np.where(fp['supply_side_domestic'] < 0, 0, fp['supply_side_domestic'])

    index_cols=['country_code', 'country', 'fbs_item_code', 'fbs_item', 'footprint_type']
    check_duplicate_indices(fp, index_cols)
    fp.to_csv(paths.diagnostic/'supply_side_footprints_by_country_item.csv', index=False)

    return fp


def compute_demand_side_by_origin(diet_fp):

    # Pivot diet footprints so domestic/imported are separate columns
    diet_fp = diet_fp[diet_fp['diet'] == 'baseline']
    index_cols = ['country_code', 'country', 'fbs_item_code', 'fbs_item', 'footprint_type']
    diet_fp = s_pivot(diet_fp, idx=index_cols, cols=['origin'], vals=['diet_footprint_whole_pop'])

    # There may be null values after the pivot, e.g., if a country has imported footprints but no domestic footprints or vice versa;
    # important to assign these to 0, otherwise when later compute the sum of both, any value + null = null
    diet_fp[['domestic', 'imported']] = diet_fp[['domestic', 'imported']].fillna(0)

    # Total demand-side
    diet_fp['demand_side_total_by_coo_only'] = diet_fp['domestic'] + diet_fp['imported']

    diet_fp.rename(
        columns={'domestic': 'demand_side_domestic_by_coo_only', 'imported': 'demand_side_imported_by_coo_only'},
        inplace=True)

    return diet_fp


# Main method
def supply_side_footprints():

    # Input ************************************************************************************************************

    fbs = pd.read_csv(paths.interim/'fao_fbs_avg_loss_unadj.csv')[
        ['country_code', 'country', 'fbs_item_code', 'fbs_item', 'production_1000_mt', 'exports_1000_mt']]

    fp = pd.read_csv(paths.interim/'item_footprints/item_footprints_by_coo.csv')[
        ['country_code', 'country', 'fbs_item_code', 'fbs_item', 'footprint_type', 'footprint']]

    item_params = pd.read_excel(paths.input / 'item_parameters.xlsx', sheet_name='fbs_items').pipe(snake_case_cols)[
        ['fbs_item_code', 'fbs_item', 'type', 'output_group', 'include_in_model']]

    diet_fp = pd.read_csv(paths.output / 'by_coo_only/diet_footprints_by_origin_diet_item.csv')[
        ['income_class', 'country_code', 'country', 'origin', 'diet', 'fbs_item_code', 'fbs_item', 'footprint_type', 'diet_footprint_whole_pop']]

    countries = pd.read_csv(paths.interim /'fao_countries.csv')[
        ['country_code', 'country', 'region', 'income_class']]

    # ******************************************************************************************************************

    # Merge w/item params to get type and output group,
    # Exclude items not included in model
    fbs = s_merge(fbs, item_params, on=['fbs_item', 'fbs_item_code'], how='left', validate='m:1')
    fbs = fbs[fbs['include_in_model'] == 'yes']

    # Merge fbs with associated footprint data,
    # Drop rows with no footprint data
    print('Merging FBS with footprint data; we do not have coo-specific footprint data for some foods (e.g., honey, some seafood); these rows will be excluded')
    fp = s_merge(fbs, fp, on=['country_code', 'country', 'fbs_item_code', 'fbs_item'], how='left', validate='m:m',
                 left_name='fbs', right_name='item_footprints')
    fp = fp[~fp['footprint'].isna()]

    # Compute supply side footprints
    supply_fp = compute_supply_side_fp(fp)

    # Compute demand-side diet footprints by origin (domestic v imported), so they can compared to supply-side in the same file
    # Note: Demand-side results only include data specific to COO, so some items and footprint types are excluded
    diet_fp = compute_demand_side_by_origin(diet_fp)

    # Note some countries have production data for certain foods but not consumption+trade, so some may be missing
    # TODO: unclear if the mismatch is because of missing countries, missing country-food pairs, or both
    print('Comparing supply- and demand-side footprints; some country-food pairs may have production data but not demand-side data')
    fp = s_merge(fp, diet_fp, on=['country_code', 'country', 'fbs_item_code', 'fbs_item', 'footprint_type'], how='left',
                 validate='1:1',
                 left_name='supply-side footprints', right_name='demand-side footprints')

    # Add region and income status
    fp = s_merge(fp, countries, on=['country_code', 'country'], how='left', validate='m:1')

    # TODO: NOTE: Even though this file includes both demand-side and supply-side footprints,
    # it should only be used for supply-side analyses, or supply-demand comparisons.
    # It should NOT be used for demand-side analyses because countries without supply-side dsta get dropped during the merge.
    fp.to_csv(paths.output/'by_coo_only/supply_side_footprints_by_country_item.csv', index=False)