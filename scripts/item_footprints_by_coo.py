import pandas as pd
import numpy as np
import paths
from utilities import *
from utilities_diet_climate import *

pd.options.display.width = 250
pd.options.display.max_columns = 999


def item_footprints_by_coo(production_system = 'baseline'):

    # Input ************************************************************************************************************

    soy_palm = pd.read_csv(paths.interim/'item_footprints/item_footprints_soy_palm_luc.csv')
    countries = pd.read_csv(paths.interim/'fao_countries.csv')\
        [['country_code', 'country', 'gleam_region']]
    item_params = pd.read_excel(paths.input/'item_parameters.xlsx', sheet_name='fbs_items').pipe(snake_case_cols)
    prod = pd.read_csv(paths.interim/'fbs_item_production.csv')\
        [['country_code', 'fbs_item_code', 'mt_production']]
    run_params = pd.read_excel(paths.params, sheet_name='parameters', skiprows=1).set_index('parameter')

    if production_system == 'intensive':
        gleam = pd.read_csv(paths.interim / 'item_footprints/item_footprints_gleam_intensive.csv')
        abx = pd.read_csv(paths.interim / 'item_footprints/item_footprints_abx_all_intensive.csv')
    else:
        gleam = pd.read_csv(paths.interim / 'item_footprints/item_footprints_gleam.csv')
        abx = pd.read_csv(paths.interim / 'item_footprints/item_footprints_abx_all.csv')

    # ******************************************************************************************************************

    # Concat item footprints, remove unnecessary cols
    cols = ['country_code', 'country', 'gleam_region',
            'fbs_item_code', 'fbs_item', 'footprint_type', 'footprint']
    fp = pd.concat([gleam, soy_palm], sort=False)[cols]

    # Concat antimicrobial footprints
    if run_params.loc['include_abx_footprints', 'value'] == 'yes':
        fp = pd.concat([fp, abx], sort=False)[cols]

    # Diagnostic: Check for duplicate indices;
    # each country-item-footprint type trio should be unique
    check_duplicate_indices(fp, index_cols=['country_code', 'country', 'fbs_item_code', 'fbs_item', 'footprint_type'])

    # Filter fbs items not in study
    fp = fp.merge(item_params[['fbs_item_code', 'include_in_model']], on='fbs_item_code', how='inner')
    fp = fp[fp['include_in_model'] == 'yes']

    fp = apply_regional_global_wavg(fp, prod, countries)

    # Combine other footprint types (e.g., blue WF + pond blue WF, GHG + LUC GHG, MI abx).
    # Best to do this as early as possible so combined types are included in all output files.
    # These must be combined AFTER regional and world footprints are computed; see abx_concat_classify for an example of why.
    # so zero LUC footprints should be added before computing combined footprints.
    # Geographic_resolution should NOT be included in index columns because some grouped footprints
    # might group data across more than one resolution (resulting in duplicate totals).
    index_cols = ['country_code', 'country', 'gleam_region', 'fbs_item_code', 'fbs_item']
    fp_grouped = combine_footprint_types(fp, index_cols, results_cols=['footprint'], keep_originals=False)
    fp_grouped['geographic_resolution'] = 'grouped_data'
    fp = pd.concat([fp, fp_grouped], sort=False)

    # Check for duplicate indices
    index_cols = ['country_code', 'country', 'fbs_item_code', 'fbs_item', 'footprint_type']
    check_duplicate_indices(fp, index_cols)

    # Set column order
    fp = fp[['country_code', 'country', 'gleam_region', 'fbs_item_code', 'fbs_item',
            'footprint_type', 'footprint',  'geographic_resolution']]

    # Output results
    if production_system=='intensive':
        fp.to_csv(paths.interim/'item_footprints/item_footprints_by_coo_intensive.csv', index=False)
    else:
        fp.to_csv(paths.interim / 'item_footprints/item_footprints_by_coo.csv', index=False)