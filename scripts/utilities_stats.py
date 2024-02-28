import numpy as np
import pandas as pd
import winsound
import scipy.stats as stats
import statistics
import statsmodels.api as sm
pd.options.display.width = 250

from utilities import *

def flag_sigificance(df, direction, sig_levels=[0.001, 0.01, 0.05]):
# Add column to df that describes level of significance

    conds = [df['p_value'] < sig_levels[0], df['p_value'] < sig_levels[1], df['p_value'] < sig_levels[2], df['p_value'] >= sig_levels[2]]
    choices = ['P<'+str(sig_levels[0]), 'P<'+str(sig_levels[1]), 'P<'+str(sig_levels[2]), '']
    df['significance'] = np.select(conds, choices, default='ERROR')

    # Add another col that signifies level of significance w/asterisks; useful shorthand for figures and tables
    choices = ['***', '**', '*', '']
    df['sig*'] = np.select(conds, choices, default='ERROR')

    # Add another shorthand col that uses + and - to indicate significance AND direction of relationship
    # Minus signs read better with spaces between them
    conds = [df[direction] > 0, df[direction] < 0, df[direction]==0]
    choices = [df['sig*'].str.replace('*','+'), df['sig*'].str.replace('*','- '), df['sig*']]
    df['sig+/-'] = np.select(conds, choices, default='ERROR')

    # Drop trailing space after last minus sign
    df['sig+/-'] = df['sig+/-'].str.strip()

    return(df)


def test_kruskal_wallace(df, y, groups, groupby=''):
# Statistical test w/null hypothesis: means from each group come from the same set
# Repeats the test and compiles results for each index
# df is a long-form dataframe
# Groups is a list of variable-value pairs

# Compared values against https://www.socscistatistics.com/tests/kruskal/default.aspx
# Slight differences, possibly due to rounding, but otherwise H-statistic (8.9298 vs. 8.8771) and P-value (0.0302 vs. 0.0309) matched expected results

    # Drop nan values from results column
    df = df[~df[y].isna()]

    # If not grouping, create a dummy variable
    if groupby=='':
        df['temp_dummy_var']='one_dummy_group_for_all_values'
        groupby='temp_dummy_var'

    # TODO: flag an error if any of the groups are not in the df. Right now doing so results in a blank P value.
    kw = df.groupby(groupby).apply(
        lambda t: stats.kruskal(*[t[t[pair[0]] == pair[1]][y] for pair in groups])
    ).rename('kruskal_wallace').reset_index()

    kw[['h_statistic', 'p_value']] = pd.DataFrame(
        kw['kruskal_wallace'].tolist())  # Statistical test outputs a tuple, this splits the tuple into separate cols

    # Add descriptive stats
    # https://data.library.virginia.edu/getting-started-with-the-kruskal-wallis-test/
    kw['group'] = groups[0][0]
    kw['y'] = y
    kw['medians_equal_across_groups'] = np.where(kw['p_value'] > 0.05, 'yes', 'no')
    kw = kw.drop(columns='kruskal_wallace')
    if 'temp_dummy_var' in kw.columns:
        kw = kw.drop(columns='temp_dummy_var')
    return(kw)


def test_mann_whitney(df, compare_by, x, y, values, hypothesis='two-sided', sig_levels=[0.001, 0.01, 0.05]):
# For a long-form dataframe, compare 'values' between two subsets of the dataframe defined by 'compare_by', 'x', and 'y'
# using a statistical test w/null hypothesis: medians from x and y come from the same set.
# Return single-row dataframe with results.
# A long form dataframe is used because x and y can be of different lengths.

    # Define x and y values
    x_vals = df[df[compare_by] == x][values].values
    y_vals = df[df[compare_by] == y][values].values

    # Error check: Mann Whitney test returns an error if all numbers are identical
    x_unique = set(x_vals)
    y_unique = set(y_vals)

    if x_unique == y_unique:
        print('All numbers are identical in mann whitney U test; skipping a test for', compare_by)
        print('x_vals:',x_vals,'y_vals:', y_vals)
        mw = pd.DataFrame()
        mw['p_value'] = [9999]
        mw['u_statistic'] = ['error: all values same']

    elif (len(x_vals)==0) | (len(y_vals)==0):
        print('Mann whitney U test with zero values in a group; skipping a test for', compare_by)
        mw = pd.DataFrame()
        mw['p_value'] = [9999]
        mw['u_statistic'] = ['error: zero values in a group']
        return mw

    else:
        # Mann Whitney U test
        mw = stats.mannwhitneyu(x_vals, y_vals, alternative=hypothesis)

        # Statistical test outputs a tuple; convert to dataframe
        mw = pd.DataFrame(mw).transpose().rename(columns={0: 'u_statistic', 1: 'p_value'})

    # Label inputs
    mw['n'] = len(x_vals) + len(y_vals)
    mw['compare_by'] = compare_by
    mw['x'] = x
    mw['y'] = y
    mw['hypothesis'] = hypothesis

    # Compute additional stats
    mw['x_median'] = statistics.median(x_vals)
    mw['y_median'] = statistics.median(y_vals)
    mw['median_diff'] = mw['x_median'] - mw['y_median']
    mw['%_median_diff'] = (mw['median_diff'] / mw['y_median']) * 100

    mw['x_mean'] = statistics.mean(x_vals)
    mw['y_mean'] = statistics.mean(y_vals)
    mw['mean_diff'] = mw['x_mean'] - mw['y_mean']
    mw['%_mean_diff'] = (mw['mean_diff'] / mw['y_mean']) * 100

    # Flag significant values
    mw = flag_sigificance(mw, direction='mean_diff', sig_levels=sig_levels)

    # Flag whether x is larger than y or vice versa
    conds = [mw['mean_diff'] > 0, mw['mean_diff'] < 0]
    choices = ['x>y', 'x<y']
    mw['direction'] = np.select(conds, choices, default='x=y')

    # Arrange cols
    mw = mw[['compare_by', 'x', 'y', 'n', 'hypothesis', 'x_median', 'y_median', 'median_diff', '%_median_diff',
             'x_mean', 'y_mean', 'mean_diff', '%_mean_diff',
             'u_statistic', 'p_value', 'significance', 'sig*', 'sig+/-', 'direction']]

    return mw


def group_mann_whitney(df, group_by, compare_by, x, y, values, hypothesis='two-sided', filepath='', show=False, sig_levels=[0.001, 0.01, 0.05]):
# Group a long-form dataframe by 'group_by'.
# Within each group, perform Mann-Whitney test.
# 'group_by' must either be a string referring to a single column in df, or a list of length > 1 if grouping over multiple columns.

    # Create empty dataframe to contain results
    results = pd.DataFrame()

    #TODO: There's probably a faster/better way to do this without using a loop.
    # Iterate over groups, compile results in a dataframe
    for g in df.groupby(group_by):

        # index 1 is the dataframe in a groupby object
        df = test_mann_whitney(g[1], compare_by, x, y, values, hypothesis, sig_levels=sig_levels)

        # If group_by is a single column, add the group name to a single column.
        if type(g[0]) == str:
            df[group_by] = g[0]

        # If grouping over multiple columns, add each column to results.
        elif type(g[0]) == tuple:
            for t in range(0, len(g[0])):
                df[group_by[t]] = g[0][t]

        results = pd.concat([results, df], sort=False)

    # Arrange columns
    if type(group_by) == str:
        group_by = [group_by]
    cols = [c for c in results.columns.tolist() if c not in group_by]
    results = results[group_by + cols]

    if show:
        print(results)
    if filepath != '':
        results.to_csv(filepath + '.csv', index=False)

    return(results)


def test_normality(df, y, groupby='', log=True):

    # Drop NaN values
    df = df[~df[y].isna()]

    if log:
        # Convert to log scale
        if 0 in df[y].values:
            print('Dropping zero values before test for log normality. Variable:',y)
            df = df[df[y] != 0]

        df[y] = np.log10(df[y].astype(float))

    # If not grouping, create a dummy variable
    if groupby == '':
        df['temp_dummy_var'] = 'one_dummy_group_for_all_values'
        groupby = 'temp_dummy_var'

    # Shapiro-wilks test for normality, with grouping
    # Confirmed results with https://www.statskingdom.com/320ShapiroWilk.html
    # Off by a hundredth value but otherwise almost exactly the same,
    sw = df.groupby(groupby).apply(
        lambda t: stats.shapiro(t[y].values))\
        .rename('result').reset_index()

    # Statistical test outputs a tuple, this splits the tuple into separate cols
    sw[['statistic', 'p_value']] = pd.DataFrame(
        sw['result'].tolist())
    sw = sw.drop(columns='result')
    sw['y'] = y

    # Add N
    n = df.groupby(groupby)[y].count()\
        .rename('n').reset_index()

    # Merge
    sw = s_merge(sw, n, on=groupby, how='left', validate='1:1')

    sw['normal'] = np.where(sw['p_value'] > 0.05, 'yes', 'no')
    if log:
        sw = sw.rename(columns={'normal': 'log_normal'})
        sw['test'] = 'Shapiro-Wilk, log normality'
    else:
        sw['test'] = 'Shapiro-Wilk, normality'

    return sw


def test_corr(dff, x, y, test='pearson_r', print_log=False, error_beep=True):
# Run Pearson correlation test on wide-form dataframe df, comparing values in columns x and y.
# Return single-row dataframe with results.
# A wide form dataframe is used because both x and y must be the same length.
# When running multiple Pearson tests, returned results can be concatenated.
# 2022_08_24: Verified that I get the same results from using an online tool: https://www.socscistatistics.com/pvalues/pearsondistribution.aspx
# TODO: This may return div zero errors when checking for correlation between a variable and itself, not sure why

    df = dff.copy() # Just to make sure we don't somehow edit the original, not certain if that could happen

    # Error checks
    if len(df[x]) != len(df[y]):
        print('ERROR: Pearson test: length of x values != length of y values for',x,y)
        if error_beep:
            winsound.Beep(400, 700)

    if df[x].isnull().values.any():
        print('ERROR: Pearson test: nan value found in x_vals; dropping row(s) from dataframe for',x,y)
        df = df[df[x].notna()]
        if error_beep:
            winsound.Beep(400, 700)

    if df[y].isnull().values.any():
        print('ERROR: Pearson test: nan value found in y_vals; dropping row(s) from dataframe for',x,y)
        df = df[df[y].notna()]
        if error_beep:
            winsound.Beep(400, 700)

    x_vals = df[x]
    y_vals = df[y]

    if print_log:
        print('x: ', x, 'y: ', y)

    if test=='pearson_r':
        s,p = stats.pearsonr(x_vals, y_vals)
    elif test=='kendall_tau':
        # Kendall rank correlation coefficient, from -1 to 1
        # Used for checking rank correlation between ordinal vars, or between continuous and ordinal
        # https://docs.scipy.org/doc/scipy-0.15.1/reference/generated/scipy.stats.kendalltau.html
        s,p = stats.kendalltau(x_vals, y_vals)

    # Create dataframe to contain results
    data = {'x':[x], 'y':[y], 'n':[len(x_vals)],
            'statistic':[s], 'p_value':[p]}
    results = pd.DataFrame(data)
    results['test'] = test

    # Flag significant values
    results = flag_sigificance(results, direction='statistic')

    # Flag direction
    conds = [results['statistic'] > 0, results['statistic'] < 0]
    choices = ['positive', 'negative']
    results['direction'] = np.select(conds, choices, default='na')

    return results


def test_linear_regression(df, x, y):
    # If x is a dummy variable (i.e., representing a categorical value), make sure they are floats, not integers
    # https://stackoverflow.com/questions/33833832/building-multi-regression-model-throws-error-pandas-data-cast-to-numpy-dtype-o

    x_vals = df[x]
    y_vals = df[y]

    # apparently
    regression = sm.OLS(y_vals, sm.add_constant(x_vals)).fit()

    return regression.summary()

    #write_file.write('\n\n\n')
    #write_file.write(x + ' -> ' + y)
    #write_file.write(regression.summary().as_text())
