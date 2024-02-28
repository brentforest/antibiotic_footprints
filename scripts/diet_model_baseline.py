import pandas as pd
import numpy as np
import paths
from datetime import datetime
from utilities import snake_case_cols

pd.options.display.max_columns = 999
pd.options.mode.chained_assignment = None


def baseline_item_quants(dm, run_params):

    # Assign baseline kg, kcal, protein
    dm = dm.rename(columns={'supply_kg/cap/yr': 'baseline_kg/cap/yr',
                            'supply_kcal/cap/day': 'baseline_kcal/cap/day',
                            'supply_g_pro/cap/day': 'baseline_g_pro/cap/day'})
    dm['baseline_mcg_b12/cap/day'] = 0

    # Set negative values to zero, e.g., Japan oats
    results_cols = dm.columns[dm.columns.str.startswith('baseline_')].tolist()
    for col in results_cols:
        dm.loc[dm[col] < 0, col] = 0

    # Set null values to zero, e.g., quantities of custom items
    # This step may be repeated in diet_model_pipeine; no harm in repeating this step just in case
    dm[results_cols] = dm[results_cols].fillna(0)

    # Compute baseline loss-adjusted values; used in other scripts, for example, when scaling diets to target kcal
    dm['baseline_loss_adj_kg/cap/yr'] = dm['baseline_kg/cap/yr'] * dm['%_after_losses']
    dm['baseline_loss_adj_g_pro/cap/day'] = dm['baseline_g_pro/cap/day'] * dm['%_after_losses']
    dm['baseline_loss_adj_kcal/cap/day'] = dm['baseline_kcal/cap/day'] * dm['%_after_losses']
    dm['baseline_loss_adj_mcg_b12/cap/day'] = 0

    return dm


def filter_countries(fbs, tm_countries, countries_to_run, all_countries):
    # Filter out countries that are not in both the fbs and tm, and/or the country list run parameter

    countries_to_run['run'] = countries_to_run['run'].apply(str)
    countries_to_run = countries_to_run[countries_to_run['run'] == 'yes']['country_code'].tolist()

    if countries_to_run:

        fbs = fbs[fbs['country_code'].isin(countries_to_run)]
        print('Countries to run:', countries_to_run)

    else:

        # If there are no specific countries to run, run for all countries:
        # Generate list of countries to exclude
        print('Running for all countries with adequate data:')
        fbs_countries = fbs['country_code'].drop_duplicates().tolist()
        countries_included = list(set(fbs_countries) & set(tm_countries))
        print('# of countries in FBS:', len(fbs_countries))
        print('# of countries in trade matrix', len(tm_countries))
        print('# of countries in both FBS and trade matrix:', len(countries_included))

        # Filter
        fbs = fbs[fbs['country_code'].isin(countries_included)]
        print('# of countries in filtered FBS:', len(fbs['country_code'].drop_duplicates()))

        # Get list of excluded countries\

        all_countries['included_in_model'] = all_countries['country_code'].isin(countries_included)
        all_countries.to_csv(paths.diagnostic/'included_countries.csv', index=False)

    return fbs


def special_items(fbs, item_params, nutrient_comp):
    # Generate dataframe of "special" items(e.g., insects), for each fbs country, that are not in the diet model

    # Merge special items w/nutrient composition
    special_items = item_params[item_params['include_in_model'] == 'special'] \
        .merge(nutrient_comp, on=['fbs_item_code', 'fbs_item'], how='left')

    # Uses cartesian product of special items and fbs countries
    fbs_countries = fbs[['country_code', 'country']].drop_duplicates()
    special_items['key'] = 1
    fbs_countries['key'] = 1

    return special_items.merge(fbs_countries, on='key', how='outer').drop(columns='key')


def percent_after_losses(dm, series_name, include_consumption):

    # Postharvest losses only apply to the domestic share of the supply,
    # on the assumption that import quantities are recorded after postharvest losses
    dm['loss_%_postharvest_adj'] = dm['loss_%_postharvest'] * (1 - dm['%_imported'])

    # Set % consumption losses to zero if they are not included;
    # consumption losses are ignored, for example, when "reversing" food losses from the point of purchase
    # back through harvest, i.e., "home to harvest"
    dm['loss_%_cons_proc_adj'] = dm['loss_%_cons_proc'] * include_consumption
    dm['loss_%_cons_unproc_adj'] = dm['loss_%_cons_unproc'] * include_consumption

    # Tally % after losses of the processed share of food
    dm['%_after_losses_proc'] = ((1 - dm['loss_%_proc'])
                                 * (1 - dm['loss_%_dist_proc'])
                                 * (1 - dm['loss_%_cons_proc_adj']))

    # Tally % after losses of the unprocessed share of food
    dm['%_after_losses_unproc'] = ((1 - dm['loss_%_dist_unproc'])
                                  * (1 - dm['loss_%_cons_unproc_adj']))

    # Apply unprocessed and processed losses to the respective share of unprocessed/processed food
    dm['%_proc'] = 1 - dm['%_unproc']
    dm['%_after_losses_proc_unproc'] = ((dm['%_unproc'] * dm['%_after_losses_unproc'])
                                       + (dm['%_proc'] * dm['%_after_losses_proc']))

    # Tally total losses
    # Note that milling occurs before processing and applies to 100% of the starting quantity
    dm[series_name] = ((1 - dm['loss_%_postharvest_adj'])
                            * (1 - dm['loss_%_milling'])
                            * dm['%_after_losses_proc_unproc'])

    # Remove temporary cols
    dm.drop(columns=['loss_%_postharvest_adj', 'loss_%_cons_proc_adj',  'loss_%_cons_unproc_adj',
                    '%_after_losses_proc', '%_after_losses_unproc', '%_after_losses_proc_unproc'], inplace=True)
    return dm


def diet_model_baseline():

    # Input
    run_params = pd.read_excel(paths.params, sheet_name='parameters', skiprows=1)
    run_params.set_index('parameter', inplace=True)

    countries_to_run = pd.read_excel(paths.params, sheet_name='countries_incl', skiprows=1)
    fbs = (pd.read_csv(paths.interim/'fao_fbs_avg_loss_unadj.csv')
        [['country_code', 'country', 'fbs_item_code', 'fbs_item', 'imports_1000_mt', 'domestic_supply_1000_mt',
          'supply_kg/cap/yr', 'supply_kcal/cap/day', 'supply_g_pro/cap/day']])
    item_params = pd.read_excel(paths.input/'item_parameters.xlsx', sheet_name='fbs_items').pipe(snake_case_cols)
    losses = pd.read_csv(paths.input / 'food_losses.csv')
    losses_regions = (pd.read_csv(paths.interim/'fao_countries.csv')[['country_code', 'food_loss_region']])
    nutrient_comp = pd.read_csv(paths.interim/'nutrient_comp.csv').pipe(snake_case_cols)
    tm_countries = (pd.read_csv(paths.interim/'fao_trade_matrix_avg_primary.csv')
        ['coo_code'].drop_duplicates().tolist())

    all_countries = pd.read_csv(paths.interim/'fao_countries.csv')

    # **************************************************************************************************************** #

    # Filter and clean FBS
    fbs = filter_countries(fbs, tm_countries, countries_to_run, all_countries) # Filter countries from fbs and trade matrix that are not in both
    fbs = fbs[fbs['fbs_item'] != 'Population'] # Filter population data
    cols = ['imports_1000_mt', 'domestic_supply_1000_mt',
            'supply_kg/cap/yr', 'supply_kcal/cap/day', 'supply_g_pro/cap/day']
    fbs[cols] = fbs[cols].fillna(0) # Replace NAN values with zeros

    # Item parameters has scaling instructions for each item in each diet, w/a column for each diet.
    # Create a separate dataframe (diet_params) and stack (normalize) these columns.
    # Diet parameters is output to a file and is later merged w/diet model to create every item-diet permutation.
    diet_cols = item_params.filter(regex='^diet_').columns.values.tolist()
    diet_params = item_params[['fbs_item_code'] + diet_cols]
    diet_params.columns = diet_params.columns.str.replace('diet_', '')
    diet_params = diet_params.melt(id_vars='fbs_item_code', var_name='diet', value_name='scaling_method')
    diet_params.to_csv(paths.interim/'diet_model_parameters.csv', index=False)

    # Strip diet columns from item_params
    item_params.drop(columns=diet_cols, inplace=True)

    # Merge fbs w/items; this becomes the baseline diet model,
    # Filter out items not in study
    # Append "special" items (e.g., insects) not included in the fbs; note that special item quants = NAN
    dm = fbs.merge(item_params, on='fbs_item_code', how='left', suffixes=('','_x'), indicator=True)
    dm.drop(columns=list(dm.filter(regex='_x')), inplace=True)
    if dm['_merge'].str.contains('left_only').any(): # Debug: make sure all fbs items have match in item params
        print('ITEM IN FBS NOT FOUND IN ITEM PARAMETERS')
        print(dm[dm['_merge'].str.contains('left_only')])
    dm = dm[dm['include_in_model'] == 'yes'].drop(columns='_merge')
    dm = pd.concat([dm, special_items(fbs, item_params, nutrient_comp)], sort=False) # TODO: Re-order column list to undo alphabetize

    # Compute % imported by item, used a) in computing postharvest losses and b) by diet_footprints_by_coo
    # Edge case: if imports > domestic supply (e.g.,due to stock variation and/or exports); cap % imported at 100%
    # Edge case: if domestic supply <= 0 (e.g., Luxembourg pulses), assume all of it (100%) is imported
    # Edge case: special items (e.g., insects, forage fish) have no FBS data; assume these are of domestic origin
    # Note: In the Nature version, in this case % imported was incorrectly set to zero
    # Domestic supply is after subtracting exports, so this assumes imports and exports are mutually exclusive,
    # i.e., imports are never exported and exports are never re-imported
    dm['%_imported'] = dm['imports_1000_mt'] / dm['domestic_supply_1000_mt']
    dm.loc[dm['%_imported'] > 1, '%_imported'] = 1
    dm.loc[dm['domestic_supply_1000_mt'] <= 0, '%_imported'] = 1
    dm['%_imported'] = dm['%_imported'].fillna(0)
    dm.drop(columns=['imports_1000_mt', 'domestic_supply_1000_mt'], inplace=True)

    # Merge w/FAO food loss region and losses; tally % after losses
    # Note: makes sure this occurs AFTER appending special items and computing imports
    # Note: losses are assumed to occur in the region of the consuming country, not the COO
    dm = (dm.merge(losses_regions, on='country_code', how='left')
            .merge(losses, on=['food_loss_region', 'food_loss_group'], how='left'))
    dm = percent_after_losses(dm, '%_after_losses', include_consumption=True)
    dm = percent_after_losses(dm, '%_after_losses_postharvest_to_home', include_consumption=False)

    # Compute quantities of FBS items in baseline diet
    dm = baseline_item_quants(dm, run_params)

    # Output
    dm.to_csv(paths.interim/'diet_model_baseline.csv', index=False)
