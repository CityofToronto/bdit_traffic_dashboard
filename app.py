import json
import logging
import os
from collections import OrderedDict
from datetime import datetime

import dash
import dash_core_components as dcc
import dash_html_components as html
import pandas as pd
import pandas.io.sql as pandasql
from numpy import nan
import plotly.graph_objs as go
from dash.dependencies import Input, Output, State
from dateutil.relativedelta import relativedelta
from flask import send_from_directory
from psycopg2 import connect


###################################################################################################
#                                                                                                 #
#                                       Data Fetching                                             #
#                                                                                                 #
###################################################################################################

database_url = os.getenv("DATABASE_URL")
if database_url is not None:
    con = connect(database_url)
else:
    import configparser
    CONFIG = configparser.ConfigParser()
    CONFIG.read('db.cfg')
    dbset = CONFIG['DBSETTINGS']
    con = connect(**dbset)

DATA = pandasql.read_sql('''
                         SELECT street, direction, dt AS date, day_type, category, period, round(tt,1) tt, 
                         CASE WHEN dt = first_value(dt) OVER (PARTITION BY direction, day_type, period ORDER BY dt DESC)
                         THEN 1 ELSE 0 END AS most_recent,
                         week_number, month_number 
                         FROM king_pilot.dash_daily
                         LEFT OUTER JOIN king_pilot.pilot_weeks weeks ON dt >= week AND dt < week + INTERVAL '1 week'
                         LEFT OUTER JOIN king_pilot.pilot_months months ON dt >= month AND dt < month + INTERVAL '1 month'
                         ''', con)
BASELINE = pandasql.read_sql('''SELECT street, direction, from_intersection, to_intersection, 
                             day_type, period, period_range, round(tt,1) tt 
                             FROM king_pilot.dash_baseline ''',
                             con)

# Numbering Weeks and Months for Dropdown Selectors
WEEKS = pandasql.read_sql('''SELECT * FROM king_pilot.pilot_weeks 
                         ''', con)
MONTHS = pandasql.read_sql('''SELECT * FROM king_pilot.pilot_months
                         ''', con, parse_dates=['month'])
WEEKS['label'] = 'Week ' + WEEKS['week_number'].astype(str) + ': ' + WEEKS['week'].astype(str)
WEEKS.sort_values(by='week_number', inplace=True)
MONTHS['label'] = 'Month ' + MONTHS['month_number'].astype(str) + ': ' + MONTHS['month'].dt.strftime("%b '%y")

#Range types: Latest Day, Select Date, WEEKS, MONTHS
RANGES = [pd.DataFrame(), pd.DataFrame(), WEEKS, MONTHS]
con.close()

###################################################################################################
#                                                                                                 #
#                                        Constants                                                #
#                                                                                                 #
###################################################################################################

TITLE = 'King Street Transit Pilot: Vehicular Travel Time Monitoring'

# Data management constants

# Hard coded ordering of street names for displaying in the data table for each 
# tab by the "orientation" of those streets. E.g. 'ew' for East-West
STREETS = OrderedDict(ew=['Dundas', 'Queen', 'Richmond', 'Adelaide', 'Wellington', 'Front'],
                      ns=['Bathurst', 'Spadina', 'University', 'Yonge', 'Jarvis'])
# Directions assigned to each tab
DIRECTIONS = OrderedDict(ew=['Eastbound', 'Westbound'],
                         ns=['Northbound', 'Southbound'])

DATERANGE = [DATA['date'].min(), DATA['date'].max()]

#Time periods for each day type, derived from the baseline dataframe
TIMEPERIODS = BASELINE[['day_type','period','period_range']].drop_duplicates().sort_values(['day_type', 'period_range'])

# Threshold for changing the colour of cells in the table based on difference 
# from the baseline in minutes
THRESHOLD = 1

#Max travel time to fix y axis of graphs, based on the lowest of the max tt in the data or 20/30 for either tab
MAX_TIME = dict(ew=min(30, DATA[DATA['direction'].isin(DIRECTIONS['ew'])].tt.max()),
                ns=min(20, DATA[DATA['direction'].isin(DIRECTIONS['ns'])].tt.max())) 

# Plot appearance
BASELINE_LINE = {'color': 'rgba(128, 128, 128, 0.7)',
                 'width': 4}
PLOT = dict(margin={'t':10, 'b': 40, 'r': 40, 'l': 40, 'pad': 8})
PLOT_COLORS = dict(pilot='rgba(22, 87, 136, 100)',
                   baseline='rgba(128, 128, 128, 1.0)',
                   selected='rgba(135, 71, 22, 1.0)')
FONT_FAMILY = '"Open Sans", "HelveticaNeue", "Helvetica Neue", Helvetica, Arial, sans-serif'

# IDs for divs
# These are defined as variables to make it easier to debug since a static 
# linter will scream if a variable isn't defined
MAIN_DIV = 'main-page'
STREETNAME_DIV = ['street-name-'+str(i) for i in [0, 1]]
SELECTED_STREET_DIVS = OrderedDict([(orientation, 'selected-street' + orientation) for orientation in STREETS])
TABLE_DIV_ID = 'div-table'
TIMEPERIOD_DIV = 'timeperiod'
CONTROLS = dict(div_id='controls-div',
                toggle='toggle-controls-button',
                timeperiods='timeperiod-radio',
                day_types='day-type-radio',
                date_range_type='date-range-types',
                date_range='date-range-dropbown',
                date_range_span='date-range-span',
                date_picker='date-picker-div',
                date_picker_span='date-picker-span')
DATERANGE_TYPES = ['Last Day', 'Select Date', 'Select Week', 'Select Month']
GRAPHS = ['eb_graph', 'wb_graph']
GRAPHDIVS = ['eb_graph_div', 'wb_graph_div']

LAYOUTS = dict(streets='streets-div')

# Default selected streets for each tab
INITIAL_STATE = {orientation:STREETS[orientation][0] for orientation in STREETS}


###################################################################################################
#                                                                                                 #
#                                   App Configuration                                             #
#                                                                                                 #
###################################################################################################
#Makes the app mobile responsive, so people can load it on their phones/tablets
metas = [{'name':"viewport",
         'content':"width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no"}]

app = dash.Dash(__name__, meta_tags=metas)
# Necessary because callbacks are registered for objects that aren't displayed 
# on any given tab
app.config['suppress_callback_exceptions'] = True
app.title=TITLE
server = app.server

# TODO: change this to the path where this will live on the EC2, this also 
# needs to detect if it's operated in Heroku
app.config.update({
        'requests_pathname_prefix': '/bdit_traffic_dashboard/',
})

# Something for heroku
server.secret_key = os.environ.get('SECRET_KEY', 'my-secret-key')

# Logging format & Setting up logging
FORMAT = '%(asctime)s %(name)-2s %(levelname)-2s %(message)s'
logging.basicConfig(level=logging.DEBUG, format=FORMAT)

LOGGER = logging.getLogger(__name__)

###################################################################################################
#                                                                                                 #
#                                   Data Manipulation                                             #
#                                                                                                 #
###################################################################################################

def pivot_order(df, orientation = 'ew', date_range_type=1):
    '''Pivot the dataframe around street directions and order by STREETS global var
    '''
    if DATERANGE_TYPES[date_range_type] in ['Last Day', 'Select Date'] and     'date' in df.columns:
        # Don't aggregate by date
        pivoted = df.pivot_table(index=['street', 'date'],
                                 columns='direction',
                                 values='tt').reset_index()
    else:
        # Do aggregate by date
        pivoted = df.pivot_table(index='street', columns='direction', values='tt').reset_index()
    pivoted.street = pivoted.street.astype("category")
    pivoted.street.cat.set_categories(STREETS[orientation], inplace=True)
    return pivoted.sort_values(['street']).round(1)

def selected_data(data, daterange_type=0, date_range_id=1):
    '''Returns a boolean column indicating whether the provided data was selected or not
    '''
    if DATERANGE_TYPES[daterange_type] == 'Last Day':
        date_filter = data['most_recent'] == 1
    elif DATERANGE_TYPES[daterange_type] == 'Select Date':
        date_filter = data['date'] == date_range_id
    elif DATERANGE_TYPES[daterange_type] == 'Select Week':
        date_filter = data['week_number'] == date_range_id
    elif DATERANGE_TYPES[daterange_type] == 'Select Month':
        date_filter = data['month_number'] == date_range_id
    return date_filter

def filter_table_data(period, day_type, orientation='ew', daterange_type=0, date_range_id=1):
    '''Return data aggregated and filtered by period, day type, tab, date range
    '''

    date_filter = selected_data(DATA, daterange_type, date_range_id)

    #current data
    filtered = DATA[(DATA['period'] == period) &
                    (DATA['day_type'] == day_type) &
                    (DATA['direction'].isin(DIRECTIONS[orientation])) &
                    (DATA['category'] != 'Excluded') &
                    (date_filter)]
    pivoted = pivot_order(filtered, orientation, daterange_type)

    #baseline data
    filtered_base = BASELINE[(BASELINE['period'] == period) &
                             (BASELINE['day_type'] == day_type) &
                             (BASELINE['direction'].isin(DIRECTIONS[orientation]))]
    pivoted_baseline = pivot_order(filtered_base, orientation)

    return (pivoted, pivoted_baseline)

def graph_bounds_for_date_range(daterange_type, date_range_id):
    '''Determine bounds for the x-axis of the graphs based on the type of 
    daterange and the selected date range
    '''
    if DATERANGE_TYPES[daterange_type] == 'Last Day':
        end_range = DATERANGE[1] + relativedelta(days=1)
        start_range = DATERANGE[1] - relativedelta(weeks=2)
        date_picked = date_range_id
    elif DATERANGE_TYPES[daterange_type] in ['Select Date', 'Select Week']:
        if DATERANGE_TYPES[daterange_type] == 'Select Date':
            date_picked = date_range_id
        else:
            date_picked = WEEKS[WEEKS['week_number'] == date_range_id]['week'].iloc[0]
        start_of_week = date_picked - relativedelta(days=date_picked.weekday())
        start_range = max(start_of_week - relativedelta(weeks=1), DATERANGE[0])
        end_range = min(start_of_week + relativedelta(weeks=2), DATERANGE[1] + relativedelta(days=1))
    elif DATERANGE_TYPES[daterange_type] == 'Select Month':
        date_picked = MONTHS[MONTHS['month_number'] == date_range_id]['month'].iloc[0].date()
        if date_picked == DATERANGE[1].replace(day=1):
            #End of data within month picked, display last month of data
            start_range = max(DATERANGE[1] - relativedelta(months=1), DATERANGE[0])
        else:
            start_range = max(date_picked - relativedelta(days=date_picked.day - 1), DATERANGE[0])
        end_range = min(date_picked - relativedelta(days=date_picked.day - 1) + relativedelta(months=1),
                        DATERANGE[1] + relativedelta(days=1))
    else:
        raise ValueError('Wrong daterange_type provided: {}'.format(daterange_type))
    LOGGER.debug('Filtering for %s. Date picked: %s, Start Range: %s, End Range: %s',
                 DATERANGE_TYPES[daterange_type], date_picked, start_range, end_range)
    return [start_range, end_range]

def filter_graph_data(street, direction, day_type='Weekday', period='AMPK',
                      daterange_type=0, date_range_id=1):
    '''Filter dataframes by street, direction, day_type, and period
    Returns a filtered baseline, and a filtered current dataframe
    '''

    daterange = graph_bounds_for_date_range(daterange_type, date_range_id)
    filtered_daily = DATA[(DATA['street'] == street) &
                          (DATA['period'] == period) &
                          (DATA['day_type'] == day_type) &
                          (DATA['direction'] == direction) & 
                          (DATA['date'] >= daterange[0]) & 
                          (DATA['date'] < daterange[1])
                          ]

    base_line = BASELINE[(BASELINE['street'] == street) &
                         (BASELINE['period'] == period) &
                         (BASELINE['day_type'] == day_type) &
                         (BASELINE['direction'] == direction)]

    base_line_data = filtered_daily[filtered_daily['category'] == 'Baseline']

    selected_filter = selected_data(filtered_daily, daterange_type, date_range_id)

    pilot_data = filtered_daily[(filtered_daily['category'] == 'Pilot') &
                                ~(selected_filter)]

    pilot_data_selected = filtered_daily[(filtered_daily['category'] == 'Pilot') &
                                         (selected_filter)]
    return (base_line, base_line_data, pilot_data, pilot_data_selected)

def get_orientation_from_dir(direction):
    '''Get the orientation of the street based on its direction'''
    for orientation, direction_list in DIRECTIONS.items():
        if direction in direction_list:
            return orientation

def get_timeperiods_for_date(selected_date):
    '''Get available timeperiods for the selected date'''
    timeperiods = DATA[DATA['date']==selected_date]['period'].unique()
    if selected_date.weekday() > 4: #Weekend
        return TIMEPERIODS[(TIMEPERIODS['day_type']=='Weekend')&
                           (TIMEPERIODS['period'].isin(timeperiods))]['period'].values
    else:
        return TIMEPERIODS[(TIMEPERIODS['day_type']=='Weekday')&
                           (TIMEPERIODS['period'].isin(timeperiods))]['period'].values

###################################################################################################
#                                                                                                 #
#                                         App Layout                                              #
#                                                                                                 #
###################################################################################################


def generate_date_ranges(daterange_type=2):
    '''Generate an array of dropdown menu options depending on the date range type
    '''

    if DATERANGE_TYPES[daterange_type] == 'Select Week':
        # Weeks
        return [{'label': row.label,
                 'value': row.week_number}
                for row in WEEKS.itertuples()]
    elif DATERANGE_TYPES[daterange_type] == 'Select Month':
        return [{'label': row.label,
                 'value': row.month_number}
                for row in MONTHS.itertuples()]
    else:
        return [{'label':'No daterange value', 'value':1}]

def generate_row_class(clicked):
    '''Assigns class to clicked row'''
    if clicked:
        return 'selected'
    else:
        return 'notselected'
    
def intstr(integer):
    if integer > 0: #ignores nan
        return str(integer)
    else:
        return integer

def generate_direction_cells(before, after):
    '''Generate before/after cells for each street direction
    '''
    return [html.Td(intstr(after), className=after_cell_class(before, after)),
            html.Td(intstr(before), className='baseline')]

def after_cell_class(before, after):
    '''Colour the after cell based on its difference with the before
    '''
    if after - before > THRESHOLD:
        return 'worse'
    elif after - before < -THRESHOLD:
        return 'better'
    else:
        return 'same'

def generate_row(df_row, baseline_row, selected, orientation='ew'):
    """Create an HTML row from a database row (each street)

        :param df_row:
            Daily data dataframe row
        :param baseline_row:
            Baseline row for that street
        :param selected:
            Whether this street is currently clicked
    """

    data_cells = []

    for i in range(2):
        baseline_val = baseline_row[DIRECTIONS[orientation][i]]
        try:
            after_val =  df_row[DIRECTIONS[orientation][i]]
        except TypeError:
            after_val = nan 
        data_cells.extend(generate_direction_cells(baseline_val, after_val))

    return html.Tr([html.Td(df_row['street'], className='segname'), 
                   *data_cells],
                   id=df_row['street'],
                   className=generate_row_class(selected))

def generate_table(selected_street, day_type, period, orientation='ew', daterange_type=0, date_range_id=1):
    """Generate HTML table of streets and before-after values

        :param selected_street:
            The street in the table that is selected
        :param day_type:
            Type of day
        :param period:
            Timeperiod name
        :param orientation:
            Filter of street orientations: East-West or...
        :param daterange_type:

        :param daterange:
            
    """
    LOGGER.debug('Generate table: daterange_type:' + str(daterange_type) 
                 + ', period: ' + str(period)
                 + ', day_type: ' + str(day_type) 
                 + ', date_range_id: ' + str(date_range_id) 
                 + ', orientation: ' + str(orientation)
                 + ', selected_street: ' + str(selected_street))
    filtered_data, baseline = filter_table_data(period, day_type, orientation, daterange_type, date_range_id)
    #Current date for the data, to replace "After" header
    if DATERANGE_TYPES[daterange_type] in ['Last Day', 'Select Date']:
        day = filtered_data['date'].iloc[0].strftime('%a %b %d')
    elif DATERANGE_TYPES[daterange_type] == 'Select Week':
        day = 'Week ' + str(date_range_id)
    elif DATERANGE_TYPES[daterange_type] == 'Select Month':
        day = 'Month ' + str(date_range_id)

    rows = []
    for baseline_row, street in zip(baseline.iterrows(), baseline['street'].values):
    # Generate a row for each street, keeping in mind the selected street (which row is clicked)
        try:
            pilot_data = filtered_data[filtered_data['street']==street].iloc[0]
        except IndexError:
            #No data for street
            pilot_data = {direction : nan for direction  in DIRECTIONS[orientation]}
            pilot_data['street'] = street
        row = generate_row(pilot_data,
                           baseline_row[1], 
                           selected_street == str(street),
                           orientation)
        rows.append(row) 

    return html.Table([html.Tr([html.Td(""), html.Td(DIRECTIONS[orientation][0], colSpan=2), html.Td(DIRECTIONS[orientation][1], colSpan=2)])] +
                      [html.Tr([html.Td(""), html.Td(day), html.Td("Baseline"), html.Td(day), html.Td("Baseline")])] +
                      rows, id='data_table')

def generate_graph_data(data, **kwargs):
    return dict(x=data['date'],
                y=data['tt'],
                text=data['tt'].round(),
                hoverinfo='x+y',
                textposition='inside',
                type='bar',
                insidetextfont=dict(color='rgba(255,255,255,1)',
                                    size=12),
                **kwargs)

def generate_figure(street, direction, day_type='Weekday', period='AMPK',
                    daterange_type=0, date_range_id=1):
    '''Generate a Dash bar chart of average travel times by day
    '''
    base_line, base_df, after_df, selected_df = filter_graph_data(street,
                                                                  direction,
                                                                  day_type,
                                                                  period,
                                                                  daterange_type,
                                                                  date_range_id)

    orientation = get_orientation_from_dir(direction)
    data = []
    if after_df.empty:
        if selected_df.empty:
            return None
    else:
        pilot_data = generate_graph_data(after_df,
                                     marker=dict(color=PLOT_COLORS['pilot']),
                                     name='Pilot')
        data.append(pilot_data)
    pilot_data_selected = generate_graph_data(selected_df,
                                              marker=dict(color=PLOT_COLORS['selected']),
                                              name='Selected')
    data.append(pilot_data_selected)

    if not base_df.empty:
        baseline_data = generate_graph_data(base_df,
                                            marker=dict(color=PLOT_COLORS['baseline']),
                                            name='Baseline')
        data.append(baseline_data)
    
    annotations = [dict(x=-0.008,
                        y=base_line.iloc[0]['tt'] + 2,
                        text='Baseline',
                        font={'color':BASELINE_LINE['color']},
                        xref='paper',
                        yref='yaxis',
                        showarrow=False
                        )]
    line = {'type':'line',
            'x0': 0,
            'x1': 1,
            'xref': 'paper',
            'y0': base_line.iloc[0]['tt'],
            'y1': base_line.iloc[0]['tt'],
            'line': BASELINE_LINE
            }
    layout = dict(font={'family': FONT_FAMILY},
                  autosize=True,
                  height=225,
                  barmode='relative',
                  xaxis=dict(title='Date',
                              fixedrange=True), #Prevents zoom
                  yaxis=dict(title='Travel Time (min)',
                              range=[0, MAX_TIME[orientation]],
                              fixedrange=True),
                  shapes=[line],
                  margin=PLOT['margin'],
                  annotations=annotations,
                  legend={'xanchor':'right'}
                  )
    return {'layout': layout, 'data': data}
                                          
#Elements to include in the "main-"
STREETS_LAYOUT = html.Div(children=[html.Div(children=[
    html.H2(id=TIMEPERIOD_DIV, children='Weekday AM Peak'),
    html.Button(id=CONTROLS['toggle'], children='Show Filters'),
    html.Div(id=CONTROLS['div_id'],
             children=[dcc.RadioItems(id=CONTROLS['timeperiods'],
                                      value=TIMEPERIODS.iloc[0]['period'],
                                      className='radio-toolbar'),
                       dcc.RadioItems(id=CONTROLS['day_types'],
                                      options=[{'label': day_type,
                                                'value': day_type}
                                               for day_type in TIMEPERIODS['day_type'].unique()],
                                      value=TIMEPERIODS.iloc[0]['day_type'],
                                      className='radio-toolbar'),
                       html.Span(children=[
                           html.Span(dcc.Dropdown(id=CONTROLS['date_range_type'],
                                    options=[{'label': label,
                                              'value': value}
                                             for value, label in enumerate(DATERANGE_TYPES)],
                                    value=0,
                                    clearable=False),
                                    title='Select a date range type to filter table data'),
                           html.Span(dcc.Dropdown(id=CONTROLS['date_range'],
                                                  options=generate_date_ranges(daterange_type=3),
                                                  value = 1,
                                                  clearable=False),
                                     id=CONTROLS['date_range_span'],
                                     style={'display':'none'}),
                           html.Span(dcc.DatePickerSingle(id=CONTROLS['date_picker'],
                                                          clearable=False,
                                                          min_date_allowed=DATERANGE[0],
                                                          max_date_allowed=DATERANGE[1],
                                                          date=DATERANGE[1],
                                                          display_format='MMM DD',
                                                          month_format='MMM',
                                                          show_outside_days=True),
                                     id=CONTROLS['date_picker_span'],
                                     style={'display':'none'})
                                     ])],
             style={'display':'none'}),
    html.Div(id=TABLE_DIV_ID, children=generate_table(INITIAL_STATE['ew'], 'Weekday', 'AM Peak')),
    html.Div([html.B('Travel Time', style={'background-color':'#E9A3C9'}),
              ' 1+ min', html.B(' longer'), ' than baseline']),
    html.Div([html.B('Travel Time', style={'background-color':'#A1D76A'}),
              ' 1+ min', html.B(' shorter'), ' than baseline']),
    ],
                           className='four columns'),
    html.H2(id=STREETNAME_DIV[0], children=[html.B('Dundas Eastbound:'),
                                                ' Bathurst - Jarvis']),
    html.Div(id = GRAPHDIVS[0], children=dcc.Graph(id=GRAPHS[0]), className='eight columns'),
    html.H2(id=STREETNAME_DIV[1], children=[html.B('Dundas Westbound:'),
                                                ' Jarvis - Bathurst']),
    html.Div(id = GRAPHDIVS[1], children=dcc.Graph(id=GRAPHS[1]), className='eight columns')
               ], id=LAYOUTS['streets'])

app.layout = html.Div([html.Div(children=[html.H1(children=TITLE, id='title')],
                                className='row twelve columns'),
                       html.Div(dcc.Tabs(children=[dcc.Tab(label='East-West Streets', value='ew'),
                                      dcc.Tab(label='North-South Streets', value='ns')],
                                value='ew',
                                id='tabs',
                                style={'font-weight':'bold'})
                                ,
                                className='row twelve columns'),
                       html.Div(id=MAIN_DIV, className='row', children=[STREETS_LAYOUT]),
                       html.Div(children=html.H3(['Created by the ',
                                                  html.A('Big Data Innovation Team',
                                                         href="https://www1.toronto.ca/wps/portal/contentonly?vgnextoid=f98b551ed95ff410VgnVCM10000071d60f89RCRD")],
                                                         style={'text-align':'right',
                                                                'padding-right':'1em'}),
                                className='row'),
                       *[html.Div(id=div_id,
                                  style={'display': 'none'},
                                  children=STREETS[orientation][0])
                         for orientation, div_id in SELECTED_STREET_DIVS.items()]
                      ])


###################################################################################################
#                                                                                                 #
#                                         Controllers                                             #
#                                                                                                 #
###################################################################################################

@app.callback(Output(LAYOUTS['streets'], 'style'),
              [Input('tabs', 'value')])
def display_streets(value):
    '''Switch tabs display while retaining frontend client-side'''
    if value == 'ew':
        return {'display':'inline'}
    elif value == 'ns':
        return {'display':'inline'}
    else:
        return {'display':'none'}

@app.callback(Output(CONTROLS['div_id'], 'style'),
              [Input(CONTROLS['toggle'], 'n_clicks')],
              state=[State(CONTROLS['toggle'], 'children')]
              )
def hide_reveal_filters(n_clicks, current_toggle):
    if current_toggle == 'Show Filters':
        return {'display':'inline'}
    else:
        return {'display':'none'}

@app.callback(Output(CONTROLS['toggle'], 'children'),
            [Input(CONTROLS['toggle'], 'n_clicks')],
            state=[State(CONTROLS['toggle'], 'children')]
            )
def change_button_text(n_clicks, current_toggle):
    if current_toggle=='Hide Filters':
        return 'Show Filters'
    else:
        return 'Hide Filters'

@app.callback(Output(CONTROLS['timeperiods'], 'options'),
              [Input(CONTROLS['date_picker'], 'date'),
               Input(CONTROLS['day_types'], 'value'),
               Input(CONTROLS['date_range_type'], 'value')]) 
def generate_radio_options(selected_date, day_type='Weekday', daterange_type=0):
    '''Assign time period radio button options based on select day type
    '''
    if DATERANGE_TYPES[daterange_type] == 'Select Date':
        selected_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
        return [{'label': period, 'value': period}
                for period
                in get_timeperiods_for_date(selected_date)]
    else:
        return [{'label': period, 'value': period}
                for period
                in TIMEPERIODS[TIMEPERIODS['day_type'] == day_type]['period']]

@app.callback(Output(CONTROLS['timeperiods'], 'value'),
              [Input(CONTROLS['date_picker'], 'date'),
               Input(CONTROLS['day_types'], 'value')],
              [State(CONTROLS['timeperiods'], 'value' ), 
               State(CONTROLS['date_range_type'], 'value')])
def assign_default_timperiod(selected_date, day_type='Weekday',
                             current_timeperiod='AM Peak', daterange_type=0):
    '''Assign the time period radio button selected option based on selected day type
    '''
    if DATERANGE_TYPES[daterange_type] == 'Select Date':
        selected_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
        available_timeperiods = get_timeperiods_for_date(selected_date)
        if current_timeperiod in available_timeperiods:
            return current_timeperiod
        else:
            return available_timeperiods[-1]
    return TIMEPERIODS[TIMEPERIODS['day_type'] == day_type].iloc[0]['period']


@app.callback(Output(CONTROLS['day_types'], 'value'),
                     [Input(CONTROLS['date_picker'], 'date')],
                     [State(CONTROLS['date_range_type'], 'value'),
                      State(CONTROLS['day_types'], 'value')])
def update_day_type(date_picked, daterange_type, day_type):
    if DATERANGE_TYPES[daterange_type] == 'Select Date':
        dt = datetime.strptime(date_picked, '%Y-%m-%d').date()
        if dt.weekday() > 4:
            return 'Weekend'
        else: 
            return 'Weekday'
    else:
        return day_type 

@app.callback(Output(TABLE_DIV_ID, 'children'),
              [Input(CONTROLS['timeperiods'], 'value'),
               Input(CONTROLS['day_types'], 'value'),
               Input(CONTROLS['date_range_type'], 'value'),
               Input(CONTROLS['date_range'], 'value'),
               Input(CONTROLS['date_picker'], 'date'),
               Input('tabs', 'value')],
              [State(div_id, 'children') for div_id in SELECTED_STREET_DIVS.values()])
def update_table(period, day_type, daterange_type, date_range_id, date_picked=datetime.today().date(), orientation='ew',  *state_data):
    '''Generate HTML table of before-after travel times based on selected
    day type, time period, and remember which row was previously selected
    '''
    LOGGER.debug('Update table: daterange_type:' + str(daterange_type) 
                 + ', period ' + str(period)
                 + ', day_type ' + str(day_type) 
                 + ', date_range_id ' + str(date_range_id) 
                 + ', orientation  ' + str(orientation)     )
    if daterange_type == 1:
        date_range_id = datetime.strptime(date_picked, '%Y-%m-%d').date()
    state_index = list(STREETS.keys()).index(orientation)
    selected_street = state_data[state_index]

    table = generate_table(selected_street, day_type, period,
                           orientation=orientation,
                           daterange_type=daterange_type,
                           date_range_id=date_range_id)
    if daterange_type == 0:
        LOGGER.debug('Table returned for Last Day')
    elif  daterange_type == 1:
        LOGGER.debug('Table returned for Selected Date: %s', date_range_id.strftime('%a %b %d'))
    elif daterange_type == 2:
        LOGGER.debug('Table returned for Week')

    return table

@app.callback(Output(CONTROLS['date_range_span'], 'style'),
              [Input(CONTROLS['date_range_type'], 'value')])
def hide_reveal_date_range(daterange_type):
    if daterange_type > 1:
        return {'display':'inline'}
    else:
        return {'display':'none'}

@app.callback(Output(CONTROLS['day_types'], 'style'),
              [Input(CONTROLS['date_range_type'], 'value')])
def hide_reveal_day_types(daterange_type):
    if daterange_type != 1:
        return {'display':'inline'}
    else:
        return {'display':'none'}

@app.callback(Output(CONTROLS['date_picker_span'], 'style'),
              [Input(CONTROLS['date_range_type'], 'value')])
def hide_reveal_date_picker(daterange_type):
    LOGGER.debug('Hide reveal date picker, daterange_type: ' + str(daterange_type))
    if daterange_type == 1:
        LOGGER.debug('Reveal date picker')
        return {'display':'inline'}
    else:
        return {'display':'none'}

@app.callback(Output(CONTROLS['date_range'], 'options'),
              [Input(CONTROLS['date_range_type'], 'value')])
def generate_date_range_for_type(daterange_type):
    return generate_date_ranges(daterange_type=daterange_type)

@app.callback(Output(CONTROLS['date_range'], 'value'),
              [Input(CONTROLS['date_range_type'], 'value')],
              [State(CONTROLS['date_range'], 'value')])
def update_date_range_value(daterange_type, date_range_id):
    if daterange_type == 1:
        date_range_id
    if not RANGES[daterange_type].empty and date_range_id <= len(RANGES[daterange_type]):
        return date_range_id
    else:
        return 1



def create_row_update_function(streetname, orientation):
    '''Create a callback function for a given streetname
    streetname is the id for the row in the datatable

    '''
    @app.callback(Output(streetname, 'className'),
                  [Input(SELECTED_STREET_DIVS[orientation], 'children')])
    def update_clicked_row(street):
        '''Inner function to update row with id=streetname
        '''
        if street:
            return generate_row_class(streetname == street)
        else:
            return generate_row_class(False)
    update_clicked_row.__name__ = 'update_row_'+streetname+'_'+orientation
    return update_clicked_row

[create_row_update_function(street, orientation) for orientation in STREETS for street in STREETS[orientation]]

def create_row_click_function(orientation):
    @app.callback(Output(SELECTED_STREET_DIVS[orientation], 'children'),
                  [Input(street,'n_clicks') for street in STREETS[orientation]]
                  )
    def row_click(*args):
        '''Detect which row was clicked and update the graphs to be for the selected street

        Clicks are detected by comparing the previous number of clicks for each row with
        the current state. Previous state is stored in a json in a hidden div
        '''
        ctx = dash.callback_context
        selected_street = ctx.triggered[0]['prop_id'].split('.')[0]

        LOGGER.debug('This street was clicked: %s', selected_street)

        return selected_street

    row_click.__name__ = 'row_click_'+orientation
    return row_click

[create_row_click_function(orientation) for orientation in STREETS.keys()]

def create_update_street_name(dir_id):
    @app.callback(Output(STREETNAME_DIV[dir_id], 'children'),
                  [*[Input(div_id, 'children') for div_id in SELECTED_STREET_DIVS.values()],
                   Input('tabs', 'value')])
    def update_street_name(*args):
        #Use the input for the selected street from the orientation of the current tab
        *selected_streets, orientation = args
        LOGGER.debug('update_street_name() Selected streets: %s \n Selected tab: %s', selected_streets, orientation)
        street = selected_streets[list(SELECTED_STREET_DIVS.keys()).index(orientation)]
        try:
            from_to = BASELINE[(BASELINE['street'] == street) &
                               (BASELINE['direction'] == DIRECTIONS[orientation][dir_id])][['from_intersection',
                                                                               'to_intersection']].iloc[0]
        except IndexError:
            return html.Div(className = 'nodata')
        else:
            return [html.B(street + ' ' + DIRECTIONS[orientation][dir_id] + ': '),
                    from_to['from_intersection'] + ' - ' + from_to['to_intersection']]

[create_update_street_name(i) for i in [0,1]]

def create_update_graph_div(graph_number):
    '''Dynamically create callback functions to update graphs based on a graph number
    '''
    @app.callback(Output(GRAPHDIVS[graph_number], 'children'),
                  [Input(CONTROLS['timeperiods'], 'value'),
                   Input(CONTROLS['day_types'], 'value'),
                   Input('tabs', 'value'),
                   *[Input(div_id, 'children') for div_id in SELECTED_STREET_DIVS.values()]],
                  [State(CONTROLS['date_range_type'], 'value'),
                   State(CONTROLS['date_range'], 'value'),
                   State(CONTROLS['date_picker'], 'date')])
    def update_graph(period, day_type, orientation, *args):
        '''Update the graph for a street direction based on the selected:
         - street
         - time period
         - day type
        '''
        *selected_streets, daterange_type, date_range, date_picked = args
        #Use the input for the selected street from the orientation of the current tab
        if daterange_type == 1:
            date_range = datetime.strptime(date_picked, '%Y-%m-%d').date()
        
        street = selected_streets[list(SELECTED_STREET_DIVS.keys()).index(orientation)]
        LOGGER.debug('Updating graph %s, for street: %s, period: %s, day_type: %s, daterange_type: %s, date_range: %s',
                     GRAPHS[graph_number], street, period, day_type, daterange_type, date_range)
        figure = generate_figure(street,
                                 DIRECTIONS[orientation][graph_number],
                                 period=period,
                                 day_type=day_type,
                                 daterange_type=daterange_type,
                                 date_range_id=date_range)
        if figure: 
            return html.Div(dcc.Graph(id = GRAPHS[graph_number],
                                      figure = figure,
                                      config={'displayModeBar': False}))
        else:
            return html.Div(className = 'nodata')

    update_graph.__name__ = 'update_graph_' + GRAPHS[graph_number]
    return update_graph

[create_update_graph_div(i) for i in range(len(GRAPHS))]

@app.callback(Output(TIMEPERIOD_DIV, 'children'),
              [Input(CONTROLS['timeperiods'], 'value'),
               Input(CONTROLS['day_types'], 'value')])
def update_timeperiod(timeperiod, day_type):
    '''Update sub title text based on selected time period and day type
    '''
    time_range = TIMEPERIODS[(TIMEPERIODS['period'] == timeperiod) & (TIMEPERIODS['day_type'] == day_type)].iloc[0]['period_range']
    return day_type + ' ' + timeperiod + ' ' + time_range


if __name__ == '__main__':
    app.run_server(debug=True)
