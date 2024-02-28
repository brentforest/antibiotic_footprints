import pandas as pd
import paths
import winsound
import math
from utilities import *

# Check the version
print('Running on Pandas v',pd.__version__)

pd.options.display.width = 250


def clean_group_output_diet_model(dm, results_cols, run_params):

    print('Running clean_group_output_diet_model')

    # Clear unneeded cols and check for missing cols
    index_cols = ['country_code', 'country', 'fbs_item_code', 'fbs_item', 'output_group', 'type', '%_imported', 'diet']
    check_nan_values(dm, index_cols)
    dm = dm[index_cols + ['scaling_method'] + results_cols]

    # Filter countries where any value in results cols < 0
    # e.g., in a prior build, Vanuatu had items w/ <0 kcal because it had to reduce staples to reach the protein floor
    conds = dm[results_cols].min(axis=1) < 0
    excl_countries = dm.loc[conds, ['country', 'diet', 'fbs_item']]
    print('\nExcluding countries w/negative values: ', excl_countries)
    dm = dm[~dm['country'].isin(excl_countries['country'].tolist())]

    # Fill NAN baseline and results cols with zeroes
    dm[results_cols] = dm[results_cols].fillna(0)

    # For some papers we might not want B12 data included in the output files
    #if 'include_b12' not in run_params:
    if run_params.loc['include_b12', 'value'] != 'yes':
        print('\nExcluding vitamin B12 columns from diet model')
        b12_cols = ['loss_adj_mcg_b12/cap/day', 'mcg_b12/cap/day']
        dm.drop(columns=b12_cols, inplace=True)
        results_cols = [i for i in results_cols if i not in b12_cols]

    # Note: we decided to keep items w/0 values in case it is ever helpful to have %_imported values for those items
    # Only keep rows with at least one baseline OR results value > 0
    # Note: we could only keep rows w/at least one results value > 0, but removing the zero baseline values
    # changes the sums when grouping diet_model_by_country_diet_items
    # dm = dm[dm[baseline_cols + results_cols].max(axis=1) > 0]

    # Check indices and output diet model
    check_duplicate_indices(dm, ['country_code', 'diet', 'fbs_item'])
    dm.to_csv(paths.output / 'diet_model_by_country_diet_item.csv', index=False)

    # Group by output group, unpivot, filter, and output
    index_cols = ['country_code', 'country', 'diet', 'output_group', 'type']
    check_nan_values(dm, index_cols)
    dm_by_group = dm.groupby(index_cols)[results_cols].sum().reset_index()
    dm_by_group = dm_by_group.melt(id_vars=index_cols, value_vars=results_cols,
                                   var_name='attribute', value_name='value')
    dm_by_group = dm_by_group[(dm_by_group['value'].notna()) & (dm_by_group['value'] != 0)]
    check_duplicate_indices(dm_by_group, index_cols + ['attribute'])
    dm_by_group.to_csv(paths.output / 'diet_model_by_country_diet_output_group.csv', index=False)

    # Group by country diet and output
    index_cols = ['country_code', 'country', 'diet']
    dm_by_diet = dm.groupby(index_cols)[results_cols].sum().reset_index()
    check_duplicate_indices(dm_by_diet, index_cols)
    dm_by_diet.to_csv(paths.output / 'diet_model_by_country_diet.csv', index=False)


def import_run(script_args):

    script = script_args[0]
    args = script_args[1]
    print('\n*****************************************************************************************************')
    print('Running:', script, args, '\n')
    exec('from ' + script + ' import ' + script)
    exec(script + args)


def scale_diets_to_target_kcal(dm, scaling_targets, results_cols):
    # TODO: write description
    print('scaling diets to target kcal')
    dms = dm.copy()
    dms = dms[dms['diet'].isin(scaling_targets['diet_to_scale'])]
    dms = dms.merge(scaling_targets, left_on='diet', right_on='diet_to_scale', how='left')
    dms['diet'] = dms['scaled_diet']
    dms['total_loss_adj_kcal/cap/day'] = dms.groupby(['country_code', 'diet'])['loss_adj_kcal/cap/day'].transform('sum')
    dms['scaling_factor'] = dms['target_loss_adj_kcal/cap/day_by_diet'] / dms['total_loss_adj_kcal/cap/day']
    for col in results_cols:
        dms[col] = dms[col] * dms['scaling_factor']

    return dms


# INPUT ****************************************************************************************************************

run_params = pd.read_excel(paths.params, sheet_name='parameters', skiprows=1)
run_params.set_index('parameter', inplace=True)
#run_params = run_params[run_params['value'] == 'yes']['parameter'].tolist()

# pipe_a: scripts to run before diet_model
# pipe_b: diet model functions
# pipe_c: scripts to run after diet_model
script_pipe = pd.read_excel(paths.params, sheet_name='pipeline', skiprows=1)
script_pipe = script_pipe[script_pipe['run'] == 'yes']
script_pipe_a = script_pipe[script_pipe['sequence'] == 'a']
script_pipe_b = script_pipe[script_pipe['sequence'] == 'b']['script'].tolist()
script_pipe_c = script_pipe[script_pipe['sequence'] == 'c']

dm_pipe = pd.read_excel(paths.params, sheet_name='dm_pipeline', skiprows=1)
dm_pipe = dm_pipe[dm_pipe['run'] == 'yes']

# pipe_a ***************************************************************************************************************

for index, row in script_pipe_a.iterrows():
    import_run(row[['script', 'args']].to_list())

# pipe_b: diet model functions *****************************************************************************************

if 'diet_model' in script_pipe_b:

    dm = pd.DataFrame()

    # Prepare the baseline diet as a reference point modeling all the other diets.
    # It has columns for "baseline_kg/cap/yr," etc., but it's not technically recognized as a diet yet by the model
    # because it doesn't have a "diet" column or "kg/cap/yr", etc.
    import_run(['diet_model_baseline', '()'])

    for index, row in dm_pipe.iterrows():
        import_run(row[['diet_model', 'args']].to_list())
        exec('dm = pd.concat([dm, pd.read_csv(' + row['file'] + ')], sort=False)')

    # Append the baseline diet as an actual diet (as opposed to just a reference point)
    dm_baseline = pd.read_csv(paths.interim / 'diet_model_baseline.csv')
    dm_baseline['diet'] = 'baseline'
    baseline_cols = dm_baseline.columns[dm_baseline.columns.str.startswith('baseline')].tolist()
    results_cols = [col.replace('baseline_', '') for col in baseline_cols]
    dm_baseline[results_cols] = dm_baseline[baseline_cols]
    dm = pd.concat([dm, dm_baseline], sort=False)


    # Define cols
    baseline_cols = dm.columns[dm.columns.str.startswith('baseline')].tolist()
    results_cols = [col.replace('baseline_', '') for col in baseline_cols]
    #results_cols = ['kg/cap/yr','kcal/cap/day','g_pro/cap/day','mcg_b12/cap/day'] + \
    #               dm.columns[dm.columns.str.startswith('loss_adj')].tolist()

    clean_group_output_diet_model(dm, results_cols, run_params)

    # Output list of unique FBS items in the diet model
    dm_unique = dm[['fbs_item_code', 'fbs_item']].drop_duplicates()
    dm_unique.to_csv(paths.diagnostic / 'diet_model_unique_fbs_items.csv', index=False)

# pipe_c ***************************************************************************************************************

for index, row in script_pipe_c.iterrows():
    import_run(row[['script', 'args']].to_list())