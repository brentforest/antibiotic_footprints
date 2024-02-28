import pandas as pd
import numpy as np
import paths
from datetime import datetime
from utilities import *

pd.options.display.width = 250
pd.options.display.max_columns = 999

# Random seed for bootstrapping
RANDOM_SEED = 3
N_TRIALS = 10000

# For reporting on script runtime
startTime = datetime.now()


def adjust_aquatic_wf(fp, percent_farmed):
    # Adjust seafood WFs to ignore the share of production that is not farmed

    # Merge w/percent of seafood that is farmed; drop duplicate columns
    fp = fp.merge(percent_farmed, on=['fbs_item_code'],  how='left', suffixes=('', '_x'))
    fp.drop(columns=list(fp.filter(regex='_x')), inplace=True)

    # If there is no match in seafood_percent_farmed, do not adjust WF
    fp['%_farmed'] = fp['%_farmed'].fillna(1)

    # Adjust WFs
    fp.loc[fp['footprint_type'].str.contains('wf', case=False), 'footprint'] *= fp['%_farmed']
    return fp


def normalize_weights(df):
    weight_sum = sum(df['weight'])
    df['weight'] = [weight / weight_sum for weight in df['weight']]
    return df


def merge_separate_clean(level_col, items, fp):
    # Generalized function to gather footprints for items at a provided level of granularity
    # Inputs:
    # `level_column` (string): Name of the grouping column, e.g., 'fbs_item_code', 'bootstrap_subgroup', 'fbs_group')
    # `items` (DataFrame): DataFrame containing the items for which footprints should be gathered,
    #                      as well as metadata about the item's group memberships
    # `fp` (DataFrame): DataFrame containing footprint values that we have across all items
    #
    # Outputs:
    # `fp_result` (DataFrame): DataFrame consisting of items for which footprints were able to be
    #                          gathered at this level of granularity, and the corresponding footprints
    #                          (multiple rows per item, representing each footprint that was found)
    # `fp_tomerge` (DataFrame): DataFrame consisting of items for which footprints could not be gathered
    #                           at this level of granularity (one row per item, with footprint null)

    fp_cols = ['footprint_type', 'footprint', 'weight'] + [level_col]
    merge_cols = ['footprint_type'] + [level_col]

    # Perform the merge. Use a left join so that unmatched items get a 'null' footprint and can be
    # separated out afterward. Items matching one or more footprints will get one row per matched footprint.
    fp_merge = pd.merge(items, fp[fp_cols], on=merge_cols, how='left')

    # Separate out the valid footprint rows based on presence of non-null footprints. Also do not
    # include rows with null values on the grouping level we merged on (e.g. if we merged on subgroup
    # and the subgroup for this item is null, it would not be considered a valid merge result even if
    # the footprint is non-null, because it may have matched to a footprint from a totally different item)
    fp_result = fp_merge[(fp_merge['footprint'].notnull() &
                          fp_merge[level_col].notnull())]

    # Store a record of the level of granularity at which these footprints were gathered
    fp_result = fp_result. \
        assign(distribution_group_level=lambda x: level_col)

    # Diagnostic check
    print('\ngrouping item footprint distribution data by', level_col)
    print('applied to the following footprint type(s):', fp_result['footprint_type'].unique())

    # Separate out the invalid footprint rows based on the same criteria as above.
    # Merge by group only for footprint types where 'boostrap_by_group' == 'yes' in parameters,
    # so filter out non-applicable rows.
    # We also only want one copy of each item-footprint for subsequent merging,
    # otherwise we'll get duplicated footprints, so drop duplicates now too.
    fp_tomerge = fp_merge[fp_merge['footprint_type'].isin(fp_types_bootstrap_by_group)]
    fp_tomerge = fp_tomerge[(fp_tomerge['footprint'].isnull() |
                             fp_tomerge[level_col].isnull())]
    fp_tomerge = fp_tomerge.drop_duplicates(['fbs_item_code', 'footprint_type'])
    return fp_result, fp_tomerge


def gather_footprints(fp, items):
    # Helper function to separate the portion of the code that gathers, and labels properly,
    # all of the valid footprints for each item that will then feed into the bootstrapping method.
    # Includes an escalation procedure to first search for footprint data at the item level, then at
    # the subgroup level, then at the group level.

    # Merge items w/list of footprint types (cartesian product);
    # this is needed in case an item has GHG footprint data at the item level, but WF footprint data at the group level
    # Keys are needed for the merge, then removed
    fp_types = fp['footprint_type'].drop_duplicates().to_frame()
    items['key'] = 1
    fp_types['key'] = 1
    items = pd.merge(items, fp_types, on='key', how='outer').drop('key', axis=1)

    # List of items columns used for merging
    # NB: Output group newly added because we need it later, and it doesn't cause any merge problems
    # since items always have the same output group
    merge_cols = ['fbs_item_code', 'fbs_item', 'bootstrap_subgroup', 'fbs_group', 'footprint_type', 'output_group']

    # Remove actual NaN footprint entries so that they don't cause problems during merging
    fp = fp[fp['footprint'].notnull()]

    # Merge on item code and footprint type
    # (Only merging these on merge_cols prevents duplicates and suffixes)
    fp_item_result, fp_item_tomerge = merge_separate_clean('fbs_item_code', items[merge_cols], fp)

    # Next merge on subgroup and footprint type if needed
    fp_subgroup_result, fp_subgroup_tomerge = merge_separate_clean('bootstrap_subgroup',
                                                                   fp_item_tomerge[merge_cols],
                                                                   fp)

    # Finally, merge on group and footprint type if needed
    fp_group_result, fp_group_tomerge = merge_separate_clean('fbs_group',
                                                             fp_subgroup_tomerge[merge_cols],
                                                             fp)

    # Concatenate item, subgroup, and group footprint distributions
    fp_merge = pd.concat([fp_item_result, fp_subgroup_result, fp_group_result], sort=False)

    # Remove items that don't belong in the bootstrap simulation at all
    fp_valid_types = fp[['output_group', 'footprint_type']].drop_duplicates()

    return fp_merge.merge(fp_valid_types, how='inner', on=['output_group', 'footprint_type'])


def summarize_footprint(diet_data, trial_data):
    # Summarize footprints, return centiles by country, diet, and output group
    # TODO: add documentation

    group_members = diet_data['fbs_item_code']
    diet_data = diet_data.set_index('fbs_item_code')
    diet_quants = diet_data['kg/cap/yr']

    # TODO: restructure diet_model.py outputs to already have 0s instead of NAs if an item
    #       is not consumed in a country/diet/output group

    # This is a little hack: append the list of items from the footprint data with zeroes, then drop
    # duplicates, keeping the first entries. This ensures that anything not in the quants is added with
    # a quant of 0. (There's no left join method available for series-list, so this was cleaner).
    new_quants = pd.Series(data=0,
                           index=group_members)
    diet_quants = diet_quants._append(new_quants)
    diet_quants = diet_quants.groupby(diet_quants.index).first()
    trial_data = trial_data[group_members]

    mat_result = trial_data.dot(diet_quants)
    # NB: np.percentile accepts centiles between 0 and 100, not 0 and 1
    mat_centile_result = np.percentile(mat_result, [25, 50, 75])

    return [mat_centile_result[0], mat_centile_result[1], mat_centile_result[2]]



# Main method
def diet_footprints_bootstrap():

    np.random.seed(RANDOM_SEED)

    # Input
    items = pd.read_excel(paths.input/'item_parameters.xlsx', sheet_name='fbs_items').pipe(snake_case_cols)
    fp = pd.read_excel(paths.input/'ghge/ghge_lit_review_distributions.xlsx', sheet_name='ghge_combined', skiprows=3)
    fp_params = pd.read_csv(paths.input/'footprint_type_bootstrap_parameters.csv')
    dm = pd.read_csv(paths.output/'diet_model_by_country_diet_item.csv').pipe(snake_case_cols)
    percent_farmed = pd.read_csv(paths.input/'aquatic_percent_farmed.csv').pipe(snake_case_cols)

    # Create global list of footprint types for which bootstrap by group applies
    global fp_types_bootstrap_by_group
    fp_types_bootstrap_by_group = fp_params[fp_params['bootstrap_by_group'] == 'yes']['footprint_type'].tolist()

    # Sort item footprint data. Even w/the same footprint values and random seed,
    # bootstrapping generates a different (but equally correct) result unless footprints are in the same sort order.
    # footprint_type_sort_order keeps the sort order static when footprint types are renamed or added.
    fp = s_merge(fp, fp_params[['footprint_type', 'footprint_type_sort_order']], on='footprint_type', how='left')
    fp.sort_values(by=['fbs_item_code', 'footprint_type_sort_order', 'footprint', 'weight'], inplace=True)

    """
    # Adjust seafood WFs to ignore the share of production that is not farmed
    fp = adjust_aquatic_wf(fp, percent_farmed)
    """

    # If quantity in diet is NaN, change to 0
    dm.loc[np.isnan(dm['kg/cap/yr']), 'kg/cap/yr'] = 0

    # Save the output groups to use later
    item_groups = items[['fbs_item_code', 'output_group']].drop_duplicates()

    # Filter out items not in study (terrestrial animal foods (except insects) don't use distribution footprint data);
    # filter out unused columns
    items = items[(items['include_in_model'] != 'no') & (items['type'] != 't_animal')]

    fp_merge = gather_footprints(fp, items)

    fp_grouped = fp_merge.groupby(['fbs_item_code', 'footprint_type'], as_index=False)
    fp_norm = fp_grouped.apply(normalize_weights)
    fp_norm.to_csv(paths.diagnostic/'item_footprint_distributions_normalized.csv', index=False)

    # Set number of samples of every item and footprint type
    n_trials = N_TRIALS

    fp_types = fp_norm['footprint_type'].unique()
    item_codes = fp_norm['fbs_item_code'].unique()

    # Initialize empty results data frame
    results_cols = ['diet', 'output_group', 'country',
                       'footprint_type', 'centile_25',
                       'centile_50', 'centile_75']
    results = pd.DataFrame(columns=results_cols)

    # Iterate over each footprint type
    for fp_type in fp_types:
        print('\nbootstrapping',fp_type)
        fp_trial_data = pd.DataFrame(columns=item_codes)
        for item_code in item_codes:
            fp_match = fp_norm['footprint_type'] == fp_type
            item_match = fp_norm['fbs_item_code'] == item_code
            fp_data = fp_norm[fp_match & item_match]

            if len(fp_data.index) > 0:
                fp_trial_data[item_code] = np.random.choice(
                    fp_data['footprint'], n_trials, p=fp_data['weight'])

        # n_trials*(number of items) data frame with all footprint trial data for
        # this fp type; remove items that don't have data for this footprint type
        fp_trial_data = fp_trial_data.dropna(axis=1, how='all')

        # Remove everything from the diet model for this footprint type that doesn't have trial data
        fp_dm = dm[dm['fbs_item_code'].isin(list(fp_trial_data.columns))]

        # Apply quantile calculations over output groups and return centiles
        results_by_fp_type = fp_dm.groupby(['diet', 'output_group', 'country']). \
            apply(lambda x: summarize_footprint(x, fp_trial_data)).rename('centiles').reset_index()

        # Split centiles into individual columns
        # https: // www.statology.org / pandas - split - column - of - lists - into - columns /
        centiles = pd.DataFrame(results_by_fp_type['centiles'].to_list(), columns=['centile_25', 'centile_50', 'centile_75'])
        results_by_fp_type = pd.concat([results_by_fp_type, centiles], axis=1)

        # Set the footprint type to the current one being iterated over
        results_by_fp_type['footprint_type'] = fp_type

        results = pd.concat([results, results_by_fp_type], sort=False)

    # Reorder columns after concat statements
    results = results[results_cols]

    # Merge w/country codes
    coded_results = results.merge(dm[['country', 'country_code']].drop_duplicates(), how='left', on='country')

    # Reorder columns again so country code is first; write to file
    coded_results[['country_code'] + results_cols].to_csv(paths.interim/'diet_footprints_bootstrap.csv', index=False)

    print("Total runtime: ")
    print(datetime.now() - startTime)
