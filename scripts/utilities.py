import numpy as np
import pandas as pd
import winsound
pd.options.display.width = 250

def snake_case(s):
    return s.lower().replace(' ', '_').replace(',', '').replace('(', '').replace(')', '')


def undo_snake_case(s):
    return s.replace('_', ' ').capitalize()


def snake_case_cols(df):
    df.columns = [snake_case(col) for col in df.columns]
    return df


def snake_case_series(ser):
    #TODO: fix issue where this causes problems with dataframe indices
    print('warning: call to snake case series; may cause bug w/indexing')
    return pd.Series([snake_case(str(s)) for s in ser])


def undo_snake_case_series(ser):
    # TODO: fix issue where this causes problems with dataframe indices
    print('warning: call to undo snake case series; may cause bug w/indexing')
    return pd.Series([undo_snake_case(str(s)) for s in ser])


def check_duplicate_indices(df, index_cols):
    # Check for duplicate indices

    df_check = df.copy().set_index(index_cols)
    dupes = df_check[df_check.index.duplicated(keep=False)]

    if len(dupes) > 0:
        winsound.Beep(400, 400)
        print('ERROR: DUPLICATE INDICES FOUND:', dupes)
        return True
    else:
        return False


def check_nan_values(df, cols):
    # Check for NAN values in columns - important, for example, before grouping by those columns
    for col in cols:
        if df[col].isna().any():
            winsound.Beep(400, 700)
            print('ERROR: NAN VALUE IN COLUMN:', df[df[col].isna()][cols])

"""
def check_nan_values(df, cols):
    # Check for NAN values in columns - important, for example, before grouping by those columns
    nan_found = df[cols].isnull().values.any()
    print('\nChecking for NAN values in columns (should be false):', nan_found)
    if (nan_found):
        print('NAN VALUE FOUND')
"""


def choose_first_notna(df, default_value):
    # Given a df, return a series w/the first values from each row, from L-R, that is not NAN.
    # If all columns are NAN in a given row, use the default value.
    # Used, for example, when choosing the country-specific extraction rate when one is available,
    # otherwise use the global extr rate.
    # TODO: Shannon's simpler method: (row[notnan(row)][0] for row in df), possibly using iterrows

    conds = list()
    choices = list()

    for col in df.columns:
        conds.append(df[col].notna())
        choices.append(df[col])

    return (np.select(conds, choices, default=default_value))


def compare_dfs(df_left, df_right, index_cols, threshold=0.000000001, drop_mismatch=True, name_left='left_df', name_right='right_df'):
# Compare values between df_old and df_new
# TODO: REPLACE VERSION IN DIET-CLIMATE MODEL WITH THIS NEWER VERSION

    print('Comparing', name_left, 'with', name_right)

    # Unpivot dataframes to compare so there is only values column
    df_left = df_left.melt(id_vars = index_cols)
    df_right = df_right.melt(id_vars = index_cols)
    index_cols = index_cols + ['variable']

    # Merge dataframes
    # Validate ensures there is at most one set of values per index
    compare = df_left.merge(df_right, on=index_cols, how='outer', suffixes=('_left', '_right'), indicator=True, validate='1:1')

    # Check for missing matches
    if compare['_merge'].str.contains('left_only').any():
        print('INDEX IN',name_left,'NOT FOUND IN',name_right)
    if compare['_merge'].str.contains('right_only').any():
        print('INDEX IN',name_right,'NOT FOUND IN',name_left)
    if compare['_merge'].str.contains('both').all():
        print('All indices match')
    comp_missing = compare[compare['_merge'] != 'both'] # To concat later

    # For string and numeric comparisons, ignore missing matches
    compare = compare[compare['_merge'] == 'both']

    # Compare if one or both values are strings
    # TODO: Tested this and it DOES catch instances where one value is NAN and the other is a string
    comp_str = compare[[isinstance(x, str) or isinstance(y, str) for x, y in zip(compare['value_left'], compare['value_right'])]]
    if len(comp_str) > 0:
        comp_str['string_diff'] = np.where(comp_str['value_left'] == comp_str['value_right'], '', 'yes')
        if comp_str['string_diff'].str.contains('yes').any():
            print('STRING MISMATCH FOUND')
        else:
            print('All string values match')

    # Compare if both values are int or float
    comp_num = compare[[isinstance(x, (float, int)) and isinstance(y, (float, int)) for x, y in zip(compare['value_left'], compare['value_right'])]]
    # TODO: for reasons I don't fully understand, this is needed to prevent a divide by zero error;
    # TODO: this ignores edge cases where one value is zero and the other is NAN
    comp_num[['value_left', 'value_right']] = comp_num[['value_left', 'value_right']].fillna(0)
    comp_num['diff'] = comp_num['value_right'] - comp_num['value_left']
    comp_num['abs_diff'] = abs(comp_num['value_right'] - comp_num['value_left'])
    comp_num['%_diff'] = comp_num['diff'] / comp_num['value_left']
    comp_num['abs_%_diff'] = abs(comp_num['%_diff'])
    comp_num['threshold'] = threshold
    comp_num['diff_>_threshold'] = np.where(comp_num['abs_diff'] > threshold, 'yes', 'no')
    comp_num = comp_num.sort_values(by='abs_diff', ascending=False)
    if comp_num['diff_>_threshold'].str.contains('yes').any():
        print('VALUE ABOVE PRECISION THRESHOLD FOUND')
    else:
        print('All numeric values below precision threshold')

    # Drop mismatched strings and numeric values below threshold
    if drop_mismatch:
        comp_str = comp_str[comp_str['string_diff'] == 'yes']
        comp_num = comp_num[comp_num['abs_diff'] > comp_num['threshold']]

    # Combine missing, string, and numeric comparisons
    compare = pd.concat([comp_num, comp_str, comp_missing], sort=False)

    return(compare)


def merge_sort(df, sort_order, merge_on, sort_by='sort_order'):
    df = s_merge(df, sort_order[[merge_on, sort_by]], on=merge_on, how='left')
    df = df.sort_values(by=sort_by)
    df = df.drop(columns=sort_by)
    return df


def s_categorical_sort(df, col, sort_order, dtype='str'):
# Sorts column based on sort order,
# reverts data type after sorting since categorical can cause errors

    # DIAGNOSTIC CHECK: check if any values in column are not in sort list are in column
    for c in df[col].drop_duplicates():
        if (c not in sort_order):
            print('ALERT: value in column not found in sort list:', c, 'not found in', sort_order)
            winsound.Beep(400, 400)

    # DIAGNOSTIC CHECK: make sure values in sort list are in column
    for l in sort_order:
        if (l not in df[col].values):
            print('ALERT: value in sort list not found in column:', l, 'not found in', col)
            winsound.Beep(400, 400)

    # Sort
    df[col] = pd.Categorical(df[col], sort_order)
    df.sort_values(col, inplace=True)

    # Revert datatype, default is string
    df[col] = df[col].astype(dtype)

    return(df)


def s_filter(df, col, list=[], substring='', excl_list=[], excl_str='', alert=True):
# The "s" is short for "smart"
# Filters dataframe column using a list or substring;
# Returns error if a list item or the substring not found in column

    if not isinstance(col, str):
        print('ALERT: columns passed to s_filter not as a string, may result in unexpected results:', col)
        winsound.Beep(400,400)

    # Filter using list of values
    if len(list) > 0:
        df = df[df[col].isin(list)]

        # DIAGNOSTIC CHECK: make sure filtered values in column
        if alert:
            for l in list:
                if (l not in df[col].values):
                    print('ALERT: value to filter on not found in column:', l, 'not found in', col)
                    winsound.Beep(400, 400)

    # Filter using substring
    if substring != '':
        df = df[df[col].str.contains(substring)]

        if ~(df[col].str.contains(substring).any()):
            print('ALERT: substring to filter on not found in column:', substring, 'not found in', col)
            winsound.Beep(400, 400)

    # Exclude vales with exclusion list
    if len(excl_list) > 0:
        df = df[~df[col].isin(excl_list)]

    # Exclude vales with exclusion substring
    if excl_str != '':
        df = df[~df[col].str.contains(excl_str)]

    return df


def s_filter_percentile(df, col, pct):
# Remove values in col below percenttile pct

    df['pct_rank'] = df[col].rank(pct=True)
    df = df[df['pct_rank'] > pct]
    df = df.drop(columns=['pct_rank'])

    return(df)


def s_merge(df1, df2, how, on='', left_on='', right_on='', alert=True, beep=True, validate='m:m',
            left_name='left_df', right_name='right_df', exit_on_alert=False, keep_merge_col=False,
            drop_duplicate_cols=True, filename=''):
# "Smart merge" two dataframes.
# Drops duplicate columns created during merge (if indicated in parameters).
# Raises an alert if indices are missing in either dataframe.
# Note that validate='m:m' does not perform any checks on merge,
# just as 'm:1' does not check the left side and '1:m' does not check the right.

    # If left_on/right_on are not provided, use "on" value for both left and right
    if left_on=='':
        left_on=on
        right_on=on

    df = df1.merge(df2, left_on=left_on, right_on=right_on, how=how, suffixes=('', '_x'),
                   indicator=True, validate=validate)

    # Beep and print missing matches
    if alert:

        if df['_merge'].str.contains('left_only').any():
            print('MERGE ALERT: Index in', left_name,'(left) not found in', right_name, '(right)')
            missing_left = df[df['_merge'] == 'left_only'][left_on].drop_duplicates()
            print(missing_left)
            if filename != '':
                missing_left.to_csv(filename + '_left.csv')
            if beep:
                winsound.Beep(400, 700)
            if exit_on_alert:
                quit()

        if df['_merge'].str.contains('right_only').any():
            print('MERGE ALERT: Index in', right_name, '(right) not found in', left_name, '(left)')
            missing_right = df[df['_merge'] == 'right_only'][right_on].drop_duplicates()
            print(missing_right)
            if filename != '':
                missing_right.to_csv(filename + '_left.csv')
            if beep:
                winsound.Beep(400, 700)
            if exit_on_alert:
                quit()

    # Drop merge col unless indicated otherwise;
    # Sometimes it can be helpful to see whether _merge = left, right, or both
    if keep_merge_col==False:
        df.drop(columns=['_merge'], inplace=True)

    # Drop duplicate cols created during merge
    if drop_duplicate_cols:
        df.drop(columns=list(df.filter(regex='_x')), inplace=True)

    return df


def s_merge_rename(df, new_names, col='', left_col='', right_col='', new_name_col='new_name', alert=True):
# Merge w/dataframe on col, rename values in col to values in new_name_col

    # Sometimes we might want different column names when merging
    if left_col=='':
        left_col=col
    if right_col=='':
        right_col=col

    # Drop any extraneous columns in new_names
    new_names = new_names[[right_col, new_name_col]]

    # Merge w/new names
    # Right merge keys should always be unique, otherwise new rows will be created.
    # Note m:1 validation only checks for unique merge keys in the right df, which is the desired behavior.
    df = s_merge(df, new_names, left_on=left_col, right_on=right_col, how='left', validate='m:1', alert=alert)

    # Apply new name, but only where a new value exists
    df[left_col] = np.where(df[new_name_col].notna(), df[new_name_col], df[left_col])
    df = df.drop(columns=new_name_col)

    return df


def s_pivot(df, idx, cols, vals):
# "Smart pivot"
# Since unstack only works on dataframes with an index,
# this function sets the index based on parameters, unstacks, then resets the index

    # If any of the inputs are strings, convert to lists
    if isinstance(idx, str): idx = [idx]
    if isinstance(cols, str): cols = [cols]
    if isinstance(vals, str): vals = [vals]

    df = df[idx + cols + vals]\
        .set_index(idx + cols, verify_integrity=True)\
        .unstack(cols)
    df.columns = df.columns.droplevel()
    df = df.reset_index().rename_axis('', axis='columns')
    return df


def string_to_int_list(string, delimiter = ', '):
# Convert a string to a list of integers
    new_list = []
    new_list = list(string.split(delimiter))
    for i in range(0, len(new_list)):
        new_list[i] = int(new_list[i])
    return new_list


def wavg(group, avg_name, weight_name, alerts=True):
# adapted from http://stackoverflow.com/questions/10951341/pandas-dataframe-aggregate-function-using-multiple-columns
# If some weights are missing, unweighted values are effectively ignored (missing weights are treated as zero).
# If no weights are given, return the unweighted mean.
# This can be used as part of a groupby statement; if not, setting group to the dataframe will return a single value.

    d = group[avg_name]
    w = group[weight_name]

    if alerts:
        if d.isnull().values.any():
            print('Warning: weighted average utility function encountered null value(s) in data!')
            winsound.Beep(400, 400)

        if w.isnull().values.any():
            print('Warning: weighted average utility function encountered null value(s) in weights!')
            winsound.Beep(400, 400)

    try:
        return (d * w).sum() / w.sum()
    except ZeroDivisionError:
        return d.mean()


def wcentile(df, percentile, value_col, weight_col):
    # https://stackoverflow.com/a/32034085
    # TODO: Add documentation, move to utilities script?
    # Uses linear interpolation to...

    a = np.array(df[value_col])
    weights = np.array(df[weight_col])

    percentile = np.array(percentile)

    if weights is None:
        weights = np.ones(len(a))
    a_indsort = np.argsort(a)
    a_sort = a[a_indsort]
    weights_sort = weights[a_indsort]
    ecdf = np.cumsum(weights_sort)

    percentile_index_positions = percentile * (weights.sum() - 1) + 1
    # need the 1 offset at the end due to ecdf not starting at 0
    locations = np.searchsorted(ecdf, percentile_index_positions)

    out_percentiles = np.zeros(len(percentile_index_positions))

    for i, empiricalLocation in enumerate(locations):
        # iterate across the requested percentiles
        if ecdf[empiricalLocation - 1] == np.floor(percentile_index_positions[i]):
            # i.e. is the percentile in between 2 separate values
            uppWeight = percentile_index_positions[i] - ecdf[empiricalLocation - 1]
            lowWeight = 1 - uppWeight

            out_percentiles[i] = a_sort[empiricalLocation - 1] * lowWeight + \
                                 a_sort[empiricalLocation] * uppWeight
        else:
            # i.e. the percentile is entirely in one bin
            out_percentiles[i] = a_sort[empiricalLocation]

    return out_percentiles[0]

