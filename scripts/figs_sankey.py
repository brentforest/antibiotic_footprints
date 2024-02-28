import numpy as np
import pandas as pd
import gc # Garbage collection module, to save memory
import math
import paths
import winsound
from datetime import datetime
from utilities import *
from utilities_figs import *

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.transforms as mtrans
import matplotlib.patches as mpatches
from pandas.api.types import CategoricalDtype
import plotly.graph_objects as go

pd.options.display.max_columns = 999
pd.options.mode.chained_assignment = None
pd.options.display.max_colwidth = 999

FILE_PATH = '../figures/sankey/'
SHOW_FIGS = False
INCOME_ORDER = ['High income', 'Upper middle income', 'Lower middle income',
                'Low income / unclassified']
MI_ORDER = ['Critically important', 'Highly important', 'Important', 'Others']
MI_COLORS = ['#ffa500', '#ffa500', '#ffa500', '#ffa500']
#MI_COLORS = ['#994f00', '#cc7700', '#ffa500', '#ffd27f']
FOOD_COLORS = ['#EA8F8F', '#C0504D', '#A47EA8', '#87ceeb', '#FFB176', '#B0D242']

LMIC_ORDER = ['Lower middle income', 'Low income / unclassified']
LMIC_FOOD_COLORS = ['#87ceeb', '#A47EA8', '#C0504D','#EA8F8F','#FFB176', '#B0D242']


def prep_abx_by_drug(abx, who_groups_mi):
    # By drug class and medical importance

    # Get medical importance
    abx_by_drug = s_filter(abx, col='footprint_type', excl_str='total') \
        .pipe(s_merge, who_groups_mi, on='footprint_type', how='left', validate='m:1')

    # Format
    abx_by_drug['drug'] = abx_by_drug['drug'].str.replace('_', ' ').str.capitalize().str.replace(' trim', ', Trim')
    abx_by_drug['mi'] = abx_by_drug['mi'].str.replace('_', ' ').str.capitalize()

    # If global total is below threshhold, put that drug in the "Others" category
    abx_by_drug['global_total'] = abx_by_drug.groupby(['drug'])['demand_side_total'].transform('sum')
    """
    conds = [(abx_by_drug['mi'] == 'Medically important') & (abx_by_drug['global_total'] < 0.01),
             (abx_by_drug['mi'] != 'Medically important') & (abx_by_drug['global_total'] < 0.01)]
    choices = ['Others MI', 'Other drugs']
    abx_by_drug['drug'] = np.select(conds, choices, default=abx_by_drug['drug'])
    """

    # Drop values where global total = 0; OIE aquaculture data, for example, includes a lot of zeroes
    abx_by_drug = abx_by_drug[abx_by_drug['global_total'] > 0] \
        .groupby(['drug', 'mi', 'food_group', 'global_total'])['demand_side_total'].sum().reset_index() \
        .sort_values(by='global_total', ascending=False)

    # Creat sorted list of drugs for plotting order
    drug_order = []
    for i in MI_ORDER:
        drug_order += abx_by_drug[abx_by_drug['mi'] == i]['drug'].drop_duplicates().to_list()

    print(drug_order)

    return (abx_by_drug, drug_order)


def prep_abx(abx, results_cols, food_groups, income_classes, who_groups_mi):

    # Filter; pivot footprints so domestic/imported are separate columns
    index_cols = ['country_code', 'country', 'income_class', 'region', 'output_group', 'fbs_item_code', 'fbs_item', 'footprint_type']
    abx = s_filter(abx, col='diet', list=['baseline']) \
        .pipe(s_filter, col='footprint_type', substring='mg_abx') \
        .pipe(s_pivot, idx=index_cols, cols=['origin'], vals=['diet_footprint_whole_pop'])

    # There may be null values after the pivot, e.g., if a country has imported footprints but no domestic footprints or vice versa;
    # important to assign these to 0, otherwise when later compute the sum of both, any value + null = null
    abx[['domestic', 'imported']] = abx[['domestic', 'imported']].fillna(0)

    # Total demand-side
    abx['demand_side_total'] = abx['domestic'] + abx['imported']

    abx.rename(columns={'domestic': 'demand_side_domestic', 'imported': 'demand_side_imported'}, inplace=True)

    # Convert mg AMR to 1000 mt
    for col in results_cols:
        abx[col] /= 1000000000000  # Convert to 1000 mt (abx)

    # Avoids Sankey error if "Russian federation' (region) flows to 'Russian federation' (country)
    abx['region'] = abx['region'].replace({
        'Russian Federation': 'Russia',
        'East Asia and Southeast Asia': 'East & Southeast Asia',
        'Latin America and the Caribbean': 'Latin America & Caribbean'})

    # Filter/merge w/food groups, income groups,
    # then groupby region, food group, fp type since we don't need resolution at the level of individual items or countries -
    # this would be too much detail for sankey diagrams
    index_cols = ['region', 'income_class', 'food_group', 'footprint_type']
    abx = s_merge(abx, food_groups, on='output_group', how='left', validate='m:1') \
        .pipe(s_merge_rename, col='income_class', new_names=income_classes) \
        .groupby(index_cols)[results_cols].sum().reset_index()

    abx_lmic = s_filter(abx, col='income_class', list=['Low income / unclassified', 'Lower middle income'])

    # by drug class
    (abx_by_drug, drug_order) = prep_abx_by_drug(abx, who_groups_mi)
    (abx_by_drug_lmic, drug_order_lmic) = prep_abx_by_drug(abx_lmic, who_groups_mi)

    abx = s_filter(abx, col='footprint_type', list=['mg_abx_total'])
    abx_lmic = s_filter(abx_lmic, col='footprint_type', list=['mg_abx_total'])

    return (abx, abx_by_drug, drug_order, abx_lmic, abx_by_drug_lmic, drug_order_lmic)


def prep_supply(supply, income_classes):

    supply = s_filter(supply, col='footprint_type', list=['mg_abx_total'])

    # Combine low income w/unclassified
    supply = s_merge_rename(supply, col='income_class', new_names=income_classes)

    # Groupby by income class; we're not interested individual items or countries
    results_cols = ['supply_side_domestic', 'supply_side_exports']
    supply = supply.groupby(['income_class'])[results_cols].sum().reset_index() \
        .melt(id_vars='income_class', value_vars=results_cols, var_name='origin', value_name='footprint')\
        .replace({'supply_side_domestic': 'Domestic', 'supply_side_exports': 'Exported'})

    # Convert to 1,000 metric tons
    supply['footprint'] /= 1000000000000

    supply.to_csv(FILE_PATH + 'supply.csv', index=False)

    return(supply)


def prep_ghg(ghg, food_groups_ghg, income_classes):

    # Convert kg CO2e to GT
    ghg['value_total'] /= 1000000000000 # Convert to GT

    ghg = s_filter(ghg, col='attribute', list=['kg_co2e_total'])\
        .pipe(s_filter, col='diet', list=['baseline'])\
        .pipe(s_merge, food_groups_ghg, on='output_group', how='left', validate='m:1', left_name='ghg')\
        .pipe(s_merge_rename, col='income_class', new_names=income_classes) \
        .groupby(['region', 'income_class', 'food_group'])['value_total'].sum().reset_index()

    return ghg


def hex_to_rgba(hex):

    hex = hex.replace('#','')

    rgba = []
    for i in (0, 2, 4):
        decimal = int(hex[i:i + 2], 16)
        rgba.append(decimal)

    rgba.append(1.0)
    return tuple(rgba)


def plot_sankey(df, node_0_name, node_cols, value, filename, node_colors=[], default_color='#B0B0B0', node_order=[], decimals=1,  height=500, pad=20):
# Note: adjusting vertical height and padding between nodes can help maintain consistent sizing across plots

    # Prep vars
    num_nodes = len(node_cols)
    nodes_range = range(0, num_nodes) # If num_nodes = 3, nodes_range = 0,1,2
    nodes = [pd.DataFrame() for n in nodes_range]
    if node_order == []:
        node_order = [[] for n in nodes_range]

    # Create master node
    nodes[0] = df.copy().rename(columns={value: 'value'})
    nodes[0]['source'] = node_0_name
    node_cols[0] = 'source'

    links = pd.DataFrame()

    # Define links
    for n in range(1, num_nodes):
        index_cols = [node_cols[n-1], node_cols[n]]
        nodes[n] = nodes[0].copy().groupby(index_cols)['value'].sum().reset_index() \
            .sort_values(by='value', ascending=False) \
            .rename(columns={node_cols[n-1]: 'source', node_cols[n]: 'target'})
        links = pd.concat([links, nodes[n]], sort=False)

    # Define nodes:
    # compute subtotals (these will be later be added to node labels, that has to happen after assigning colors),
    # Sort nodes, this is the order they will appear in the figure;
    for n in nodes_range:
        if n==0:
            label_col = 'source'
        else:
            label_col = 'target'
        nodes[n] = nodes[n][[label_col, 'value']].rename(columns={label_col: 'label'}).groupby('label')['value'].sum().reset_index().sort_values(by='value', ascending=False)

        #  default is to sort on values, unless an order is provided:
        if node_order[n] != []:
            nodes[n] = s_categorical_sort(nodes[n], col='label', sort_order=node_order[n])
            print('sorted:', nodes[n])

        # Define x and y position of nodes, I think maybe these are supposed to range between 0 and 1?
        # Y position is determined based on sort order.
        # Hack: Y position doesn't seem to always apply if it set to 0? Tried add + 0.01 to all y positions except [0] and that seemed to help.
        nodes[n]['x'] = 1/(num_nodes-1) * n
        nodes[n]['y'] = nodes[n].reset_index().index / len(nodes[n]['label']) + 0.01
        #nodes[n]['y'].iloc[0] = 0

    # This is a weird hack that for some reason needs to be needed to make sure plant foods is always at the bottom
    if node_cols[2] == 'food_group':
        nodes[2].loc[nodes[2]['label'] == 'Plant foods', 'y'] = 0.9

    # Diagnostic check - make sure totals add up
    totals = [nodes[n]['value'].sum().round(6) for n in nodes_range]
    print('sankey totals, should match:', totals)
    if not all(t == totals[0] for t in totals):
        print('ERROR: Totals across node columns do not match')
        winsound.Beep(400, 400)

    # Concat nodes
    nodes = pd.concat([nodes[n] for n in nodes_range], sort=False)
    nodes['id'] = nodes.reset_index().index

    # Assign colors
    # We're using RGBA format so we can assign an alpha channel; plotly only accepts this in string format.
    # Matplotlib supposedly has functions that convert hex colors to rgba, but orange shows up as red, wtf,
    # so I just adapted someone's function to convert hex to rgba.
    # Note colors have to go from list into a dataframe so node colors can be merged into links

    if node_colors==[]:
        nodes['color'] = 'rgba' + str(hex_to_rgba(default_color))
    else:
        nodes['color'] = ['rgba' + str(hex_to_rgba(c)) for c in node_colors]

    # Rename sources and targets to numeric node IDs
    # Merging links with nodes assigns link colors
    links = s_merge(links, nodes[['id', 'label']], left_on='source', right_on='label', how='left')
    links['source'] = links['id']
    links = links.drop(columns=['label', 'id'])
    links = s_merge(links, nodes, left_on='target', right_on='label', how='left')
    links['target'] = links['id']
    links = links.drop(columns=['label', 'id'])

    # Adjust opacity for link colors
    links['color'] = links['color'].str.replace(', 1.0', ', 0.5')

    # Add rounded values to node labels,
    # note this step has to be after assigning colors,
    # because once we change the names of food groups the merge won't find matches in food_colors.
    nodes['label'] += ' ' + nodes['value'].round(decimals).astype(str)

    print(nodes)

    #print(nodes)
    #print(links)

    plt = go.Figure(data=[go.Sankey(
        arrangement='snap',
        node=dict(
            pad=pad,
            thickness=20,
            line=dict(width=0.0),
            label=nodes['label'].dropna(axis=0, how='any'),
            color=nodes['color'],
            x=nodes['x'],
            y=nodes['y']
        ),
        link=dict(
            source=links['source'].dropna(axis=0, how='any'),
            target=links['target'].dropna(axis=0, how='any'),
            value=links['value'].dropna(axis=0, how='any'),
            color=links['color']
        ),
        textfont=dict(
            color='black',
            family='arial',
            size=14
        )
    )])

    if SHOW_FIGS:
        plt.show()

    # More on writing plot.ly images: https://plotly.com/python/static-image-export/
    plt.write_image(FILE_PATH + filename + '.pdf', height=height)
    plt.write_image(FILE_PATH + filename + '.png', height=height)


# Main method
def figs_sankey():
    
      # Input ************************************************************************************************************

    # Since we're mapping FBS items to custom fig groups, inputs need to be at the item level
    abx = pd.read_csv(paths.output / 'by_coo_only/diet_footprints_by_origin_diet_item.csv')

    supply = pd.read_csv(paths.output / 'by_coo_only/supply_side_footprints_by_country_item.csv')

    food_groups = pd.read_csv(paths.input/'figures/food_groups.csv')
    income_classes = pd.read_csv(paths.input/'figures/income_reclassification.csv')
    who_groups_mi = pd.read_excel(paths.input / 'antibiotic_use/abu_classifications.xlsx', sheet_name='medical_importance', skiprows=3)[
        ['footprint_type', 'mi', 'drug']]

    #global food_colors
    #food_colors = pd.read_csv(paths.input / 'figures/abx/food_groups_all_order_colors.csv')[['food_group', 'color']]

    """
    # Supply-side footprints
    ss_fp = pd.read_csv(paths.output/'by_coo_only/supply_side_footprints_by_country_item.csv')
    
    # by_coo footprints include GHG footprints, but only for COO data,
    # so we have to use a separate file to get the full list of foods.
    # This means we can't show GHGe by domestic vs. imported without excluding certain foods.
    ghg = pd.read_csv(paths.output/'diet_footprints_population_total_by_country.csv')
    food_groups_ghg = pd.read_csv(paths.input / 'figures/abx/food_groups_ghg_sankey.csv')
    """

    # ******************************************************************************************************************

    # Prep inputs

    #results_cols = ['supply_side_total', 'demand_side_total_by_coo_only', 'demand_side_domestic_by_coo_only', 'demand_side_imported_by_coo_only']
    # TODO: We haven't been using supply-side sankey's so I commented out that option, will need updating if we add them back
    results_cols = ['demand_side_total', 'demand_side_domestic', 'demand_side_imported']

    # Prep abx
    (abx, abx_by_drug, drug_order, abx_lmic, abx_by_drug_lmic, drug_order_lmic) = \
        prep_abx(abx, results_cols, food_groups, income_classes, who_groups_mi)

    # Prep supply
    supply = prep_supply(supply, income_classes)

    # Prep ghg (unused)
    #ghg = prep_ghg(ghg, food_groups_ghg, income_classes)

    abx.to_csv(FILE_PATH + 'sankey.csv', index=False)
    abx_by_drug.to_csv(FILE_PATH + 'sankey_by_drug.csv', index=False)

    # By origin
    index_cols = ['region', 'income_class', 'food_group', 'footprint_type']
    abxo = abx.melt(id_vars=index_cols, value_vars=results_cols, var_name='origin', value_name='footprint') \
        .pipe(s_filter, col='origin', list=['demand_side_domestic', 'demand_side_imported']) \
        .replace({'demand_side_domestic': 'Domestic', 'demand_side_imported': 'Imported'})
    abxo.to_csv(FILE_PATH + 'sankey_by_origin.csv', index=False)

    abxo_lmic = s_filter(abxo, col='income_class', list=['Low income / unclassified', 'Lower middle income'])

    # Plot Sankeys *****************************************************************************************************
    plot_sankey(supply, node_0_name='Supply-side AMU', node_cols=['source', 'origin', 'income_class'],
                  value='footprint', node_order=[[], [], INCOME_ORDER], default_color='#ffa500',
                  filename='abx_sankey_supply_origin_income')

    # By drug class
    plot_sankey(abx_by_drug, node_0_name='All countries/territories', node_cols=['source', 'mi', 'drug'], value='demand_side_total',
                filename='abx_sankey_demand_importance_drug', default_color='#ffa500',
                node_order=[[], MI_ORDER,
                             drug_order], height=582, pad=15)

    # by origin (domestic v. imported)
    plot_sankey(abxo, node_0_name='All countries/territories', node_cols=['source', 'origin', 'food_group'], node_colors=['#ffa500', '#ffa500', '#ffa500'] + FOOD_COLORS, value='footprint',
                filename='abx_sankey_demand_origin_food')

    # by origin and income
    plot_sankey(abxo, node_0_name='All countries/territories', node_cols=['source', 'origin', 'income_class'], value='footprint',
                filename='abx_sankey_demand_origin_income', node_order=[[], [], INCOME_ORDER],  node_colors=['#ffa500', '#ffa500', '#ffa500'] + ['#ffa500', '#ffa500', '#ffa500', '#ffa500'],
                height=461, default_color='#ffa500')

    # by income
    plot_sankey(abx, node_0_name='All countries/territories', node_cols=['source', 'income_class', 'food_group'], value='demand_side_total',
                filename='abx_sankey_demand_income_food', node_order=[[], INCOME_ORDER, []], node_colors=['#ffa500'] + MI_COLORS+FOOD_COLORS)

    # by region
    plot_sankey(abx, node_0_name='All countries/territories', node_cols=['source', 'region', 'food_group'], value='demand_side_total',
                filename='abx_sankey_demand_region_food',  node_colors=['#ffa500', '#ffa500', '#ffa500', '#ffa500', '#ffa500', '#ffa500', '#ffa500', '#ffa500', '#ffa500', '#ffa500'] + FOOD_COLORS,
                height=575, pad=22)

    # Use WHO groups with just two categories
    #abx_by_mi = abx_by_drug.copy().groupby(['food_group', 'mi'])['demand_side_total'].sum().reset_index()
    plot_sankey(abx_by_drug, node_0_name='All countries/territories', node_cols=['source', 'mi', 'food_group'], value='demand_side_total',
                filename='abx_sankey_demand_mi_food', node_colors=['#ffa500'] + MI_COLORS+ FOOD_COLORS,
                node_order=[[], MI_ORDER,
                             ['Pig meat', 'Bovine meat', 'Sheep & goat', 'Aquatic animals', 'Poultry meat',  'Plant foods']]
                )

    """
    plot_sankey(abx_by_drug_lmic, node_0_name='LMICs', node_cols=['source', 'mi', 'drug'],
                  value='demand_side_total',
                  filename='abx_sankey_demand_importance_drug_lmic', default_color='#ffa500',
                  node_order=[[], MI_ORDER,
                              drug_order_lmic], height=582, pad=15)

    plot_sankey(abxo_lmic, node_0_name='LMICs', node_cols=['source', 'origin', 'food_group'],
                  node_colors=['#ffa500', '#ffa500', '#ffa500'] + LMIC_FOOD_COLORS, value='footprint',
                  filename='abx_sankey_demand_origin_food_lmic')

    # by income, LMICs only
    plot_sankey(abx_lmic, node_0_name='LMICs', node_cols=['source', 'income_class', 'food_group'],
                  value='demand_side_total',
                  filename='abx_sankey_demand_income_food_lmic', node_order=[[], LMIC_ORDER, []],
                  node_colors=['#ffa500', '#ffa500', '#ffa500'] + LMIC_FOOD_COLORS)

    plot_sankey(abx_lmic, node_0_name='LMICs', node_cols=['source', 'region', 'food_group'],
                  value='demand_side_total',
                  filename='abx_sankey_demand_region_food_lmic',
                  node_colors=['#ffa500', '#ffa500', '#ffa500', '#ffa500', '#ffa500', '#ffa500',
                               '#ffa500', '#ffa500'] + LMIC_FOOD_COLORS,
                  height=575, pad=22)
        
    plot_sankey(abx_by_drug_lmic, node_0_name='LMICs', node_cols=['source', 'mi', 'food_group'],
                value='demand_side_total',
                filename='abx_sankey_demand_mi_food_lmic', node_colors=['#ffa500'] + MI_COLORS + LMIC_FOOD_COLORS,
                node_order=[[], MI_ORDER,
                            ['Aquatic animals', 'Sheep & goat', 'Bovine meat',  'Pig meat',  'Poultry meat',
                             'Plant foods']]
                )
    """
    # GHGe
    """
    plot_sankey(ghg, node_0='Global demand', node_1='income_class', value='value_total', decimals=2,
                filename='ghg_sankey_demand_income_food')
    """
