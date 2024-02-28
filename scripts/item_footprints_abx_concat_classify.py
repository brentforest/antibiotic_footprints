import pandas as pd
import numpy as np
import paths
from utilities import *

pd.options.display.width = 250
pd.options.display.max_columns = 999


def classify_group_abx(abx, abx_groups_drug, index_cols):

    # Match to drug classes and group by drug class.
    # for meat, the grouping step combines meat and feed footprints.
    abx_groups_drug = abx_groups_drug.drop_duplicates()  # Only keep unique values in drug_groups to ensure a 1:1 match
    abx = s_merge_rename(abx, abx_groups_drug, col='footprint_type', new_name_col='footprint_type_reclassified') \
        .groupby(index_cols)['footprint'].sum().reset_index()

    # Diagnostic: Check for duplicate indices
    check_duplicate_indices(abx, index_cols=index_cols)

    """
    # Add suffix indicating medically important vs. not.
    # Appending a suffix to the existing footprint_type, rather than adding a new column (which would be unique to abx footprints),
    # seems more compatible with the 'combine_footprint_types' function
    abx = s_merge_rename(abx, abx_groups_mi, col='footprint_type', new_name_col='footprint_type_mi')
    """
    return abx


def item_footprints_abx_concat_classify(production_system='baseline'):

    # Note: this script used to group by WHO importance,
    # but we can't group footprint types until AFTER computing regional/global averages.
    # For example, if quantity of drug A is country-specific but quantity of drug B needs to be based on a regional average,
    # we need to compute the regional footprint for drug B before summing the total abx footprint.

    # Input ************************************************************************************************************

    # Assigning columns when loading files flags an error if any of these cols are missing
    index_cols = ['country_code', 'country', 'gleam_region', 'fbs_item_code', 'fbs_item', 'footprint_type']
    cols = index_cols + ['footprint']

    # Make sure feed is included in abx_meat. If it's not, include it here.
    # If it is, don't include it here otherwise we double count.
    abx_crops = pd.read_csv(paths.interim / 'item_footprints/item_footprints_abx_crops.csv')[cols]
    abx_aqua = pd.read_csv(paths.interim/'item_footprints/item_footprints_abx_aqua.csv')[cols]

    abx_groups_drug = pd.read_excel(paths.input/'antibiotic_use/abu_classifications.xlsx', sheet_name='drug_classes', skiprows=3)[
        ['footprint_type', 'footprint_type_reclassified']]
    #abx_groups_mi = pd.read_excel(paths.input/'item_footprints/abx/abx_classification_who_mi.xlsx', sheet_name='data', skiprows=2)[
    #    ['footprint_type', 'footprint_type_mi']]

    if production_system=='intensive':
        abx_meat = pd.read_csv(paths.interim / 'item_footprints/item_footprints_abx_meat_intensive.csv')[cols]
    else:
        abx_meat = pd.read_csv(paths.interim / 'item_footprints/item_footprints_abx_meat.csv')[cols]

    # ******************************************************************************************************************

    # Concat abx footprints by species
    abx = pd.concat([abx_crops, abx_aqua, abx_meat], sort=False)

    abx = classify_group_abx(abx, abx_groups_drug, index_cols)

    if production_system == 'intensive':
        abx.to_csv(paths.interim/'item_footprints/item_footprints_abx_all_intensive.csv', index=False)
    else:
        abx.to_csv(paths.interim / 'item_footprints/item_footprints_abx_all.csv', index=False)