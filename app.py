import json
import logging
import os
import numpy as np
from collections import OrderedDict
from datetime import datetime, date
import dash
import dash_core_components as dcc
import dash_html_components as html
import dash_bootstrap_components as dbc
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
                          SELECT case when d.street in ('Adelaide', 'Richmond', 'Queen', 'Front', 'Wellington') then d.street||' Street' 
                            when d.street in ('Eastern') then d.street||' Avenue'
                            when d.street = 'DVP' then 'Don Valley Parkway'
                            when d.street = 'Gardiner' then 'Gardiner Expressway'
                            when d.street = 'Lakeshore' then 'Lake Shore Boulevard' end
                            as street_short, case when direction = 'EB' then 'Eastbound'
                            when direction = 'WB' then 'Westbound'
                            when direction = 'NB' then 'Northbound'
                            when direction ='SB' then 'Southbound' 
                            else direction end as direction,  COALESCE(name2, d.start_crossstreet || ' to ' || d.end_crossstreet) as street1,
							COALESCE(name1, d.street || ': ' || d.start_crossstreet || ' and ' || d.end_crossstreet) as street, 
                            date, day_type, category, period, round(tt/60,2) as tt, most_recent, week_number, month_number 
                            FROM data_analysis.gardiner_dash_daily_mat d
							join data_analysis.gardiner_periods using (period, day_type)
                            left join (SELECT DISTINCT ON (d1.street, d1.start_cross, d1.end_cross) d1.street, d1.start_cross, d1.end_cross, 
                                        d1.street || ': ' || d1.start_cross || ' and ' || d1.end_cross as name1,
									   d1.start_cross || ' to ' || d1.end_cross as name2
                                        FROM data_analysis.gardiner_segments d1, data_analysis.gardiner_segments d2 
                                        WHERE d1.street = d2.street and d1.start_cross = d2.end_cross and d1.direction in ('NB', 'EB')
                                        ORDER BY d1.street) n	
                            ON n.street = d.street AND ( (n.start_cross = d.start_crossstreet AND n.end_cross = d.end_crossstreet) OR (n.start_cross = d.end_crossstreet AND n.end_cross = d.start_crossstreet)) 									
                            order by d.street, d.direction, start_crossstreet,time_range''', con)


BASELINE = pandasql.read_sql('''SELECT COALESCE(name1, d.street || ': ' || d.from_intersection || ' and ' || d.to_intersection) as street,
	                            COALESCE(name2, d.from_intersection || ' to ' || d.to_intersection) as street1, d.street as street_short,
                                d.direction, from_intersection, to_intersection,day_type, period, to_char(lower(period_range::TIMERANGE), 'FMHH AM')||' to '||to_char(upper(period_range::TIMERANGE), 'FMHH AM') as period_range , tt
                                FROM data_analysis.gardiner_dash_baseline_mat d 
								join data_analysis.gardiner_periods using (period, day_type)
                                left join (SELECT DISTINCT ON (d1.street, d1.start_cross, d1.end_cross) d1.street, d1.start_cross, d1.end_cross, 
                                                            d1.street || ': ' || d1.start_cross || ' and ' || d1.end_cross as name1,
										  					d1.start_cross || ' to ' || d1.end_cross as name2
                                                            FROM data_analysis.gardiner_segments d1, data_analysis.gardiner_segments d2 
                                                            WHERE d1.street = d2.street and d1.start_cross = d2.end_cross and d1.direction in ('NB', 'EB')
                                                            ORDER BY d1.street) n																																   
                                ON n.street = d.street AND ( (n.start_cross = d.from_intersection AND n.end_cross = d.to_intersection) 
                                OR (n.start_cross = d.to_intersection AND n.end_cross = d.from_intersection))
								order by time_range									
                            ''',con)

HOLIDAY = pandasql.read_sql(''' SELECT dt FROM ref.holiday WHERE dt >= '2019-08-01' ''', con, parse_dates=['dt',])

# Numbering Weeks and Months for Dropdown Selectors
WEEKS = pandasql.read_sql('''SELECT * FROM data_analysis.gardiner_weeks ''', con)
MONTHS = pandasql.read_sql('''SELECT * FROM data_analysis.gardiner_months''', con, parse_dates=['month'])

WEEKS['label'] = 'Week ' + WEEKS['week_number'].astype(str) + ': ' + WEEKS['week'].astype(str)

MONTHS['label'] = MONTHS['month'].dt.strftime("%b '%y")

#Range types: Latest Day, Select Date, WEEKS, MONTHS
RANGES = [pd.DataFrame(), pd.DataFrame(), WEEKS, MONTHS]
con.close()

###################################################################################################
#                                                                                                 #
#                                        Constants                                                #
#                                                                                                 #
###################################################################################################

TITLE = 'Gardiner Expressway Rehabilitation - Travel Time Monitoring'

# Data management constants

# Hard coded ordering of street names for displaying in the data table for each 
# tab by the "orientation" of those streets. E.g. 'ew' for East-West
STREETS = OrderedDict(dvp=['DVP: Dundas and Bayview Ramp',
                            'DVP: Bayview Ramp and Don Mills',
                            'DVP: Don Mills and Wynford',
                            'DVP: Wynford and Lawrence',],
                      gardiner=['Gardiner: Wickman and Grand',
                                'Gardiner: Grand and Roncesvalles',
                                'Gardiner: Roncesvalles and Dufferin',
                                'Gardiner: Dufferin and Spadina',
                                'Gardiner: Spadina and Dundas',],
                      lakeshore=[
                                 'Lakeshore: Ellis and Dufferin',
                                 'Lakeshore: Dufferin and Strachan',
                                 'Lakeshore: Yonge and Strachan',
                                 'Lakeshore: Yonge and Spadina',
                                 'Lakeshore: Strachan and Bay',
                                 'Lakeshore: Parliament and Yonge',
                                 'Lakeshore: Parliament and Don Roadway',
                                 'Lakeshore: Don Roadway and Leslie',
                                 'Lakeshore: Leslie and Coxwell',
                                 ],
                      adelaide=['Adelaide: Bathurst and Spadina',
                                'Adelaide: Spadina and University',
                                'Adelaide: University and Yonge',
                                'Adelaide: Yonge and Jarvis',],
                      richmond=['Richmond: Spadina and Bathurst',
                                'Richmond: University and Spadina',
                                'Richmond: Yonge and University',
                                'Richmond: Jarvis and Yonge',],
                      eastern=['Eastern: Broadview and Leslie',
                                'Eastern: Leslie and Coxwell',
                                'Eastern: Coxwell and Woodbine',],     
                      queen=['Queen: Strachan and Bathurst',
                             'Queen: Bathurst and Spadina',
                             'Queen: Spadina and University',
                             'Queen: University and Yonge',
                             'Queen: Yonge and Jarvis',
                             'Queen: Jarvis and Parliament',
                             'Queen: Parliament and Broadview',
                             'Queen: Broadview and Greenwood',
                             'Queen: Greenwood and Woodbine',],
                      front=['Front: Bathurst and Spadina',
                             'Front: Spadina and University',
                             'Front: University and Yonge',
                             'Front: Yonge and Jarvis'],
                      wellington=['Wellington: Yonge and University','Wellington: University and Blue Jays'])
# Directions assigned to each tab
DIRECTIONS = OrderedDict(dvp=['Northbound', 'Southbound'],
                         gardiner=['Eastbound', 'Westbound'],
                         queen=['Eastbound', 'Westbound'],
                         adelaide=['Eastbound',],
                         richmond=['Westbound'],
                         eastern=['Eastbound', 'Westbound'],
                         lakeshore=['Eastbound', 'Westbound'],
                         front=['Eastbound', 'Westbound'],
                         wellington=['Westbound'],)

#Time periods for each day type, derived from the baseline dataframe
TIMEPERIODS = BASELINE[['day_type','period','period_range']].drop_duplicates()

#Find the most recent weekday as default value for select date
DATA.date = pd.to_datetime(DATA.date)
MOST_RECENT_WEEKDAY = DATA[DATA['date'].dt.weekday <5]['date'].max()
DATERANGE = [DATA['date'].min(), DATA['date'].max()]
# Threshold for changing the colour of cells in the table based on difference 
# from the baseline in minutes
THRESHOLD = 1

#Max travel time to fix y axis of graphs, based on the highest of the max tt in the data or 20/30 for either tab
MAX_TIME = dict(dvp=max(5,DATA[DATA['street'].isin(STREETS['dvp'])].tt.max()),
                gardiner=max(5,DATA[DATA['street'].isin(STREETS['gardiner'])].tt.max()),
                queen=max(5,DATA[DATA['street'].isin(STREETS['queen'])].tt.max()),
                adelaide=max(5,DATA[DATA['street'].isin(STREETS['adelaide'])].tt.max()),
                richmond=max(5,DATA[DATA['street'].isin(STREETS['richmond'])].tt.max()),
                eastern=max(5,DATA[DATA['street'].isin(STREETS['eastern'])].tt.max()),
                lakeshore=max(5,DATA[DATA['street'].isin(STREETS['lakeshore'])].tt.max()),
                front=max(5,DATA[DATA['street'].isin(STREETS['front'])].tt.max()),
                wellington=max(5,DATA[DATA['street'].isin(STREETS['wellington'])].tt.max())) 

# Plot appearance
BASELINE_LINE = {'color': 'rgba(128, 128, 128, 0.7)',
                 'width': 4}
PLOT = dict(margin={'t':10, 'b': 40, 'r': 40, 'l': 40, 'pad': 8})
PLOT_COLORS = dict(pilot='#165788',
                   baseline='#7f7e7e',
                   selected='#ec9f09'
                   )
FONT_FAMILY = '"Libre Franklin", sans-serif'

# IDs for divs
# These are defined as variables to make it easier to debug since a static 
# linter will scream if a variable isn't defined
MAIN_DIV = 'main-page'
STREETNAME_DIV = ['street-name-'+str(i) for i in [0, 1]]
SELECTED_STREET_DIVS = OrderedDict([(orientation, 'selected-street' + orientation) for orientation in STREETS])
TABLE_DIV_ID = 'div-table'
TIMEPERIOD_DIV = 'timeperiod'
STEP2 = 'step2'
BASELINE_DESC = 'baseline_desc'
STREET_TITLE = 'street-title'
TABLE_TITLE = 'table-title'
TIME_TITLE = 'time-title'
CONTROLS = dict(div_id='controls-div',
                toggle='toggle-controls-button',
                baseline_toggle='baseline-toggle',
                timeperiods='timeperiod-radio',
                day_types='day-type-radio',
                date_range_type='date-range-types',
                date_range='date-range-dropbown',
                date_range_span='date-range-span',
                date_picker='date-picker-div',
                date_picker_span='date-picker-span')
DATERANGE_TYPES = ['Select Date', 'Select Week', 'Select Month']
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

app = dash.Dash(__name__, meta_tags=metas, external_stylesheets=[dbc.themes.BOOTSTRAP])
# Necessary because callbacks are registered for objects that aren't displayed 
# on any given tab
app.config['suppress_callback_exceptions'] = True
app.title=TITLE
server = app.server

# TODO: change this to the path where this will live on the EC2, this also 
# needs to detect if it's operated in Heroku
app.config.update({
         'requests_pathname_prefix': '/richmond-watermain/',
 })

# Something for heroku
server.secret_key = os.environ.get('SECRET_KEY', 'my-secret-key')

# Logging format & Setting up logging
FORMAT = '%(asctime)s %(name)-2s %(levelname)-2s %(message)s'
logging.basicConfig(level=logging.WARNING, format=FORMAT)

LOGGER = logging.getLogger(__name__)

###################################################################################################
#                                                                                                 #
#                                   Data Manipulation                                             #
#                                                                                                 #
###################################################################################################

def pivot_order(df, orientation = 'gardiner', date_range_type=1):
    '''Pivot the dataframe around street directions and order by STREETS global var
    '''
    if DATERANGE_TYPES[date_range_type] == 'Select Date' and     'date' in df.columns:
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

def selected_data(data, daterange_type=0, date_range_id=MOST_RECENT_WEEKDAY):
    '''Returns a boolean column indicating whether the provided data was selected or not
    '''
    if DATERANGE_TYPES[daterange_type] == 'Select Date':
        date_filter = data['date'] == date_range_id
    elif DATERANGE_TYPES[daterange_type] == 'Select Week':
        date_filter = data['week_number'] == date_range_id
    elif DATERANGE_TYPES[daterange_type] == 'Select Month':
        date_filter = data['month_number'] == date_range_id
    return date_filter

def filter_table_data(period, day_type, orientation='gardiner', daterange_type=0, date_range_id=MOST_RECENT_WEEKDAY):
    '''Return data aggregated and filtered by period, day type, tab, date range
    '''

    date_filter = selected_data(DATA, daterange_type, date_range_id)

    #current data
    filtered = DATA[(DATA['period'] == period) &
                    (DATA['day_type'] == day_type) &
                    (DATA['street'].isin(STREETS[orientation])) &
                    (DATA['category'] != 'Excluded') &
                    (date_filter)]              
    pivoted = pivot_order(filtered, orientation, daterange_type)
        
    #baseline data
    filtered_base = BASELINE[(BASELINE['period'] == period) &
                             (BASELINE['day_type'] == day_type) &
                             (BASELINE['street'].isin(STREETS[orientation]))]
    pivoted_baseline = pivot_order(filtered_base, orientation)

    return (pivoted, pivoted_baseline)
    
def graph_bounds_for_date_range(daterange_type, date_range_id):
    '''Determine bounds for the x-axis of the graphs based on the type of 
    daterange and the selected date range
    '''
    if DATERANGE_TYPES[daterange_type] in ['Select Date', 'Select Week']:
        if DATERANGE_TYPES[daterange_type] == 'Select Date':
            date_picked = date_range_id
        else:
            date_picked = WEEKS[WEEKS['week_number'] == date_range_id]['week'].iloc[0]
        start_of_week = pd.to_datetime(date_picked - relativedelta(days=date_picked.weekday()))
        start_range = max(start_of_week - relativedelta(weeks=1), DATERANGE[0])
        date_picked = pd.to_datetime(date_picked)

        if date_picked < pd.to_datetime('2019-07-07'):
            end_range = min(start_of_week + relativedelta(weeks=2), DATERANGE[1] + relativedelta(days=1))
        else:    
            end_range = min(start_of_week + relativedelta(weeks=1), DATERANGE[1] + relativedelta(days=1))
    elif DATERANGE_TYPES[daterange_type] == 'Select Month':
        date_picked = MONTHS[MONTHS['month_number'] == date_range_id]['month'].iloc[0]
        date_picked = pd.to_datetime(date_picked)
        # End of data within month picked and have less than 14 days of data, display 14 days of data of last month
        if date_picked == DATERANGE[1].replace(day=1) and DATERANGE[1].day < 14:
            start_range = max(date_picked - relativedelta(days=date_picked.day - 1) - relativedelta(days=14), DATERANGE[0])
            end_range = min(date_picked - relativedelta(days=date_picked.day - 1) + relativedelta(months=1), DATERANGE[1] + relativedelta(days=1))

        else:
            # check if start_range starts on a weekend or is a holiday
            start_range = max(date_picked - relativedelta(days=date_picked.day - 1) - relativedelta(days=1), DATERANGE[0])
            while start_range.weekday() not in (1,2,3,4,5) or (HOLIDAY['dt'] == start_range).sum() > 0:
               start_range = start_range - relativedelta(days=1)

            # do the same for end_range
            end_range = min(date_picked - relativedelta(days=date_picked.day - 1) + relativedelta(months=1), DATERANGE[1] + relativedelta(days=1)) 
            while end_range.weekday() not in (1,2,3,4,5) or (HOLIDAY['dt'] == start_range).sum() > 0:
                end_range = end_range + relativedelta(days=1)
            end_range = end_range + relativedelta(days=1)    
            
    else:
        raise ValueError('Wrong daterange_type provided: {}'.format(daterange_type))
    LOGGER.warning('Filtering for %s. Date picked: %s, Start Range: %s, End Range: %s',
                 DATERANGE_TYPES[daterange_type], date_picked, start_range, end_range)
    return [start_range, end_range]

def filter_graph_data(street, direction, day_type='Weekday', period='AMPK',
                      daterange_type=0, date_range_id=MOST_RECENT_WEEKDAY):
    '''Filter dataframes by street, direction, day_type, and period
    Returns a filtered baseline, and a filtered current dataframe
    '''

    daterange = graph_bounds_for_date_range(daterange_type, date_range_id)
    filtered_daily = DATA[(DATA['street'] == street) &
                          (DATA['period'] == period) &
                          (DATA['day_type'] == day_type) &
                          (DATA['direction'] == direction) & 
                          (DATA['date'] >= daterange[0]) & 
                          (DATA['date'] < daterange[1])]
    
    base_line = BASELINE[(BASELINE['street'] == street) &
                         (BASELINE['period'] == period) &
                         (BASELINE['day_type'] == day_type) &
                         (BASELINE['direction'] == direction)]

    max_tt = max(10, DATA[(DATA['street'] == street) &
                          (DATA['period'] == period) &
                          (DATA['day_type'] == day_type) & 
                          (DATA['date'] >= daterange[0]) & 
                          (DATA['date'] < daterange[1])
                          ]['tt'].max()) 

    selected_filter = selected_data(filtered_daily, daterange_type, date_range_id)

    base_line_data = filtered_daily[(filtered_daily['category'] == 'Baseline')&
                                    ~(selected_filter)]

    data_selected = filtered_daily[(selected_filter)]

    pilot_data = filtered_daily[(filtered_daily['category'] == 'Closure')&
                                ~(selected_filter)]

    return (base_line, base_line_data, pilot_data, data_selected, max_tt)

def get_timeperiods_for_date(selected_date):
    '''Get available timeperiods for the selected date'''
    if selected_date.weekday() > 4: #Weekend
        return TIMEPERIODS[(TIMEPERIODS['day_type']=='Weekend')]['period'].unique()
    else:
        return TIMEPERIODS[(TIMEPERIODS['day_type']=='Weekday')]['period'].unique()

###################################################################################################
#                                                                                                 #
#                                         App Layout                                              #
#                                                                                                 #
###################################################################################################


def generate_date_ranges(daterange_type=DATERANGE_TYPES.index('Select Week')):
    '''Generate an array of dropdown menu options depending on the date range type
    '''

    if DATERANGE_TYPES[daterange_type] == 'Select Week':
        # Weeks
        LOGGER.debug(WEEKS.itertuples())
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

def generate_direction_cells(before, after, baseline_state):
    '''Generate before/after cells for each street direction
    '''
    if baseline_state ==1:
        return [html.Td(intstr(after), className=after_cell_class(before, after)),
                html.Td(intstr(before), className='baseline')]
    elif baseline_state ==2:
        return [html.Td(intstr(after), className='same')]                

def after_cell_class(before, after):
    '''Colour the after cell based on its difference with the before
    '''
    if after - before > THRESHOLD:
        return 'worse'
    elif after - before < -THRESHOLD:
        return 'better'
    else:
        return 'same'

def generate_row(df_row, baseline_row, selected, orientation='gardiner', baseline_state=1):
    """Create an HTML row from a database row (each street)

        :param df_row:
            Daily data dataframe row
        :param baseline_row:
            Baseline row for that street
        :param selected:
            Whether this street is currently clicked
    """

    data_cells = []
    table_street = DATA[DATA['street'] == df_row['street']]['street1'].iloc[0]

    for i in range(len(DIRECTIONS[orientation])):
        try:
            baseline_val = baseline_row[DIRECTIONS[orientation][i]]
        except KeyError:
            baseline_val = nan
        try:
            after_val =  df_row[DIRECTIONS[orientation][i]]
        except (KeyError, TypeError):
            after_val = nan 
        data_cells.extend(generate_direction_cells(baseline_val, after_val, baseline_state))
    
    if baseline_state ==1:
        return html.Tr([html.Td(table_street, className='segname'), 
                    *data_cells],
                    id=df_row['street'],
                    className=generate_row_class(selected))
    elif baseline_state ==2:
        return html.Tr([html.Td(table_street, className='segname'), 
                    *data_cells],
                    id=df_row['street'],
                    className=generate_row_class(selected))                

def generate_table(selected_street, day_type, period, orientation='gardiner', daterange_type=0, date_range_id=MOST_RECENT_WEEKDAY, baseline_state=1):
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

        :param baseline_state:
            While baseline has been selected or not
            
    """
    LOGGER.debug('Generate table: daterange_type:' + str(daterange_type) 
                 + ', period: ' + str(period)
                 + ', day_type: ' + str(day_type) 
                 + ', date_range_id: ' + str(date_range_id) 
                 + ', orientation: ' + str(orientation)
                 + ', selected_street: ' + str(selected_street)
                 + ', baseline_state: ' + str(baseline_state))
    filtered_data, baseline = filter_table_data(period, day_type, orientation, daterange_type, date_range_id)
    #Current date for the data, to replace "After" header
    if DATERANGE_TYPES[daterange_type] == 'Select Date':
        try:
            day = filtered_data['date'].iloc[0].strftime('%a %b %d')
        except IndexError:
            day = date_range_id.strftime('%a %b %d')
    elif DATERANGE_TYPES[daterange_type] == 'Select Week':
        day = 'Week ' + str(date_range_id)
    elif DATERANGE_TYPES[daterange_type] == 'Select Month':
        LOGGER.debug(date_range_id)
        date_picked = MONTHS[MONTHS['month_number'] == date_range_id]['month'].iloc[0]

        day = date_picked.strftime("%b '%y")

    rows = []
    for baseline_row, street in zip(baseline.iterrows(), baseline['street'].values):
    # Generate a row for each street, keeping in mind the selected street (which row is clicked)
        try:
            pilot_data = filtered_data[filtered_data['street']==street].iloc[0]
        except IndexError:
            #No data for street
            pilot_data = {direction : nan for direction  in DIRECTIONS[orientation]}
            pilot_data['street'] = street
        if baseline_state ==1:
            row = generate_row(pilot_data,
                            baseline_row[1], 
                            selected_street == str(street),
                            orientation,
                            baseline_state)
        elif baseline_state ==2:
            row = generate_row(pilot_data,
                            baseline_row[1],
                            selected_street == str(street),
                            orientation,
                            baseline_state)                                   
        rows.append(row) 
    if len(DIRECTIONS[orientation]) == 1:
        if baseline_state ==1:
            return html.Table(
                            [html.Tr([html.Td(""), html.Td(DIRECTIONS[orientation][0], className='direction-title', colSpan=2)])] +
                            [html.Tr([html.Td(""), html.Td(day, className='date-title'), html.Td(" Baseline ", className='baseline_title')])] +
                            rows, id='data_table')
        elif baseline_state ==2:
            return html.Table(
                            [html.Tr([html.Td(""), html.Td(DIRECTIONS[orientation][0], className='direction-title', colSpan=1)])] +
                            [html.Tr([html.Td(""), html.Td(day, className='date-title')])] +
                            rows, id='data_table')    
    else:                            
        if baseline_state ==1:
            return html.Table(
                            [html.Tr([html.Td(""), html.Td(DIRECTIONS[orientation][0], className='direction-title', colSpan=2), html.Td(DIRECTIONS[orientation][1], className='direction-title', colSpan=2)])] +
                            [html.Tr([html.Td(""), html.Td(day, className='date-title'), html.Td(" Baseline ", className='baseline_title'), html.Td(day, className='date-title'), html.Td(" Baseline ", className='baseline_title')])] +
                            rows, id='data_table')
        elif baseline_state ==2:
            return html.Table(
                            [html.Tr([html.Td(""), html.Td(DIRECTIONS[orientation][0], className='direction-title', colSpan=1), html.Td(DIRECTIONS[orientation][1], className='direction-title', colSpan=1)])] +
                            [html.Tr([html.Td(""), html.Td(day, className='date-title'), html.Td(day, className='date-title')])] +
                            rows, id='data_table')                  

def generate_graph_data(data, **kwargs):
    return dict(x=data['date'],
                y=data['tt'],
                text=data['tt'].round(),
                hoverinfo='x+y',
                textposition='inside',
                type='bar',
                insidetextfont=dict(color='rgba(255,255,255,1)',
                                    size=14),
                **kwargs)

def generate_figure(street, direction, day_type='Weekday', period='AMPK',
                    daterange_type=0, date_range_id=MOST_RECENT_WEEKDAY, baseline_state=1):
    '''Generate a Dash bar chart of average travel times by day
    '''
    base_line, base_df, after_df, selected_df, max_tt = filter_graph_data(street,
                                                                          direction,
                                                                          day_type,
                                                                          period,
                                                                          daterange_type,
                                                                          date_range_id)
    data = []
    if DATERANGE_TYPES[daterange_type] == 'Select Date' or DATERANGE_TYPES[daterange_type] == 'Select Week':
        tick_number = 13
    elif DATERANGE_TYPES[daterange_type] == 'Select Month':
        tick_number = 15

    if after_df.empty:
        if selected_df.empty and base_df.empty:
            LOGGER.debug('No data to display on graph')
            return None
    else:
        pilot_data = generate_graph_data(after_df,
                                     marker=dict(color=PLOT_COLORS['pilot']),
                                     name='Closure',showlegend=False)
                                         
        data.append(pilot_data)

    if not base_df.empty:
        baseline_data = generate_graph_data(base_df,
                                            marker=dict(color=PLOT_COLORS['baseline']),
                                            name='Baseline',showlegend=False)
        data.append(baseline_data)

    # Add style for selected data and append to data
    selected_pilot = generate_graph_data(selected_df.loc[selected_df['category']=='Closure'],
                                             marker=dict(color =PLOT_COLORS['pilot'], line=dict(width=3.5, color=PLOT_COLORS['selected'])), 
                                             name='Selected Closure',showlegend=False)    
    data.append(selected_pilot)

    if DATERANGE_TYPES[daterange_type] == 'Select Date' or DATERANGE_TYPES[daterange_type] == 'Select Week':
        selected_baseline = generate_graph_data(selected_df.loc[selected_df['category']=='Baseline'],
                                                marker=dict(color = PLOT_COLORS['baseline'], line=dict(width=3.5, color=PLOT_COLORS['selected'])), 
                                                name='Selected Baseline',showlegend=False)
    elif DATERANGE_TYPES[daterange_type] == 'Select Month':
        selected_baseline = generate_graph_data(selected_df.loc[selected_df['category']=='Baseline'],
                                                marker=dict(color = PLOT_COLORS['baseline']), 
                                                name='Baseline',showlegend=False)                                                                                    
    data.append(selected_baseline)
    annotations = [dict(x=0,
                        y=base_line.iloc[0]['tt'] + 1,
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

    if baseline_state == 1: 
        layout = dict(font={'family': FONT_FAMILY, 'size':14},
                    autosize=True,
                    height=235,
                    barmode='relative',
                    xaxis=dict(title='Date',
                                tickformat = '%b %d',
                                nticks = tick_number,
                                showgrid = False,
                                fixedrange=True, #Prevents zoom
                                automargin=True), #Prevents axis title from overlapping axis
                    yaxis=dict(title='Travel Time (min)',
                                range=[0, max_tt],
                                tickmode = 'linear',
                                showgrid = False,
                                dtick =5,
                                fixedrange=True),
                    shapes= [line],
                    margin=PLOT['margin'],
                    annotations=annotations,
                    showlegend=False,
                    )
    elif baseline_state == 2:
        layout = dict(font={'family': FONT_FAMILY, 'size':14},
                    autosize=True,
                    height=235,
                    barmode='relative',
                    xaxis=dict(title='Date',
                                tickformat = '%b %d',
                                nticks = tick_number,
                                fixedrange=True, #Prevents zoom
                                automargin=True), #Prevents axis title from overlapping axis
                    yaxis=dict(title='Travel Time (min)',
                                range=[0, max_tt],
                                tickmode = 'linear',
                                dtick =5,
                                showgrid = False,
                                fixedrange=True),
                    margin=PLOT['margin'],
                    showlegend=False,
                    )       
    return {'layout': layout, 'data': data}
                                       
#Elements to include in the "main-"
LEGEND = html.Div(children = [html.Div(className="box_baseline", style={'display':'inline-block', 'margin-left':"30px"}),
         html.Span("Baseline  ", style={'display':'inline-block', 'margin-left':"10px"}),
         html.Div(className="box_closure", style={'display':'inline-block', 'margin-left':"20px"}),
         html.Span("Construction  ", style={'display':'inline-block', 'margin-left':"10px"}), 
         html.Div(className="box_selected", style={'display':'inline-block', 'margin-left':"20px"}),
         html.Span("Selected  ", style={'display':'inline-block', 'margin-left':"10px"})])

STREETS_LAYOUT = html.Div(children=[
        html.Div(children=[
                    html.Button(id=CONTROLS['toggle'], children='Show Filters', style = {'margin-right':'5px'}),
                    html.Button("Generate PDF", id='print-button')]
                , className="hide-on-print", style={'margin-top':'5px'}),  
        html.Div(
            id=CONTROLS['div_id'],
                children=[
                    html.H3('Follow these steps to visualize and compare travel time:',style={'fontSize':18, 'fontWeight':'bold'}, className="hide-on-print"),
                    html.Div(
                        children=[
                                html.H3('Step 1: Select the type of time period', style={'fontSize':16, 'marginTop': 10} ),
                                html.Div(dcc.Dropdown(id=CONTROLS['date_range_type'],
                                        options=[{'label': label,
                                                'value': value}
                                                for value, label in enumerate(DATERANGE_TYPES)],
                                        value=0,
                                        clearable=False, 
                                        style={'width': '200px'}),
                                        title='Select a date range type to filter table data')], className="hide-on-print"
                                        ),
                    html.Div(
                        children=[
                                html.H3(id=STEP2, style={'fontSize':16, 'marginTop': 10} ),             
                                html.Div(dcc.Dropdown(id=CONTROLS['date_range'],
                                                    options= generate_date_ranges(daterange_type=DATERANGE_TYPES.index('Select Week')),
                                                    value = 1,
                                                    clearable=False),
                                        id=CONTROLS['date_range_span'],
                                        style={'display':'none'}),
                                html.Span(dcc.DatePickerSingle(id=CONTROLS['date_picker'],
                                                            clearable=False,
                                                            min_date_allowed=DATERANGE[0],
                                                            max_date_allowed=DATERANGE[1],
                                                            date=MOST_RECENT_WEEKDAY,
                                                            display_format='MMM DD',
                                                            month_format='MMM',
                                                            show_outside_days=True),
                                        id=CONTROLS['date_picker_span'],
                                        style={'display':'none'}),
                                html.H3('Step 3: Select a time of day period', style={'fontSize':16, 'marginTop': 10} ),         
                                        ], className="hide-on-print"),
                    html.Div(                                                    
                            [dbc.RadioItems(id=CONTROLS['day_types'],
                                                options=[{'label': day_type,
                                                            'value': day_type}
                                                        for day_type in TIMEPERIODS['day_type'].unique()],
                                                value=TIMEPERIODS.iloc[0]['day_type'],
                                                labelClassName="date-group-labels",
                                                labelCheckedClassName="date-group-labels-checked",
                                                className="date-group-items", inline=True),   
                            dbc.RadioItems(id=CONTROLS['timeperiods'],
                                                value=TIMEPERIODS.iloc[0]['period'],
                                                labelClassName="date-group-labels",
                                            labelCheckedClassName="date-group-labels-checked",
                                            className="date-group-items hide-on-print", inline=True),   
                                        ] , className="hide-on-print",
                            ),
                    html.Div([html.H3('Step 4: Select to display the Baseline', style={'fontSize':16}),
                            dbc.RadioItems(id="baseline-toggle",
                                            value=1,
                                            labelClassName="date-group-labels",
                                            labelCheckedClassName="date-group-labels-checked",
                                            className="date-group-items", inline=True, 
                                            options=[
                                                    {"label": "Baseline", "value": 1},
                                                    {"label": "No Baseline", "value": 2}])], className="hide-on-print"
                                                    ),                    
                            html.H3('Step 5: Select streets in the table to display trends', style={'fontSize':16}, className="hide-on-print" ),                                                                             
                        ]
                        ),
                    html.Div([    
                            html.Div(id=TABLE_TITLE, className="table-title"),
                            html.Div(id=TABLE_DIV_ID, children=generate_table(INITIAL_STATE['gardiner'], 'Weekday', 'AM Peak'), className="data-table"),
                            html.Div(id='tt-long', children=[html.B('Travel Time', style={'background-color':'#E9A3C9'}),' 1+ min', html.B(' longer'), ' than baseline'], className="tt-long"),
                            html.Div(id='tt-short', children=[html.B('Travel Time', style={'background-color':'#A1D76A'}),' 1+ min', html.B(' shorter'), ' than baseline'], className="tt-short"), 
                            html.H3(id = 'baseline-description', 
                                children='Baseline: Sep 1 - Oct 14 2019, and Aug 1 - Sep 7 2019 for routes affected by TTC Trackwork at Kingston/Woodbine and Queen',
                                className="baseline-description"
                                    )                               
                    ])
        ])                    

app.layout = html.Div([
            dbc.Row(
                html.Div(
                    dbc.Col([html.H1(children=TITLE, id='title', className='title-style')], width=12)
                                , className='title-style-background')
                    ),
            dbc.Row(
                dbc.Col([html.Div(
                        dcc.Tabs(children=[
                                    dcc.Tab(label='Gardiner', value='gardiner',className='custom-tab',selected_className='custom-tab--selected'),
                                    dcc.Tab(label='DVP', value='dvp',className='custom-tab',selected_className='custom-tab--selected'),
                                    dcc.Tab(label='Lakeshore', value='lakeshore',className='custom-tab',selected_className='custom-tab--selected'),
                                    dcc.Tab(label='Queen', value='queen',className='custom-tab',selected_className='custom-tab--selected'),
                                    dcc.Tab(label='Richmond', value='richmond',className='custom-tab',selected_className='custom-tab--selected'),
                                    dcc.Tab(label='Adelaide', value='adelaide',className='custom-tab',selected_className='custom-tab--selected'),
                                    dcc.Tab(label='Wellington', value='wellington',className='custom-tab',selected_className='custom-tab--selected'),
                                    dcc.Tab(label='Front', value='front',className='custom-tab',selected_className='custom-tab--selected'),
                                    dcc.Tab(label='Eastern', value='eastern',className='custom-tab',selected_className='custom-tab--selected'),
                                    ],
                                    value='gardiner',
                                    id='tabs',
                                    ),className="hide-on-print")], width=12)
                    ),
            dbc.Container(
                [dbc.Row([
                    dbc.Col((                    
                            html.Div(id=MAIN_DIV, children=[STREETS_LAYOUT])), width={"size":4, "order":1}, sm=12, xs=12, md=12, lg=4),
                    dbc.Col(html.Div(children=[
                                                html.H2(id=STREET_TITLE, style={'fontSize':30, 'fontWeight':'bold', 'fontColor':'black'}),
                                                html.H2(id=TIME_TITLE, className="graph-period-title"),                  
                                                html.H2(id=STREETNAME_DIV[0],className="graph-title"),
                                                html.Div(id = GRAPHDIVS[0], children=dcc.Graph(id=GRAPHS[0])),
                                                html.H2(id=STREETNAME_DIV[1], className="graph-title"),
                                                html.Div(id = GRAPHDIVS[1],children=dcc.Graph(id=GRAPHS[1])),
                                                html.Div(children=[LEGEND]),
                                                 ]), width={"size":8, "order":2}, sm=12, xs=12, md=12, lg=8),
       
                        ]),  
                dbc.Row(        
                     [dbc.Col(
                            (html.Footer(children=html.H3(['Created by the ',
                                                  html.A('Big Data Innovation Team',
                                                         href="https://www.toronto.ca/services-payments/streets-parking-transportation/road-safety/big-data-innovation-team/")],
                                                         style={'text-align':'right',
                                                                'padding-right':'1em'},className="hide-on-print"),
                               ),
                       *[html.Div(id=div_id,
                                  style={'display': 'none'},
                                  children=STREETS[orientation][0])
                         for orientation, div_id in SELECTED_STREET_DIVS.items()]), width=12)
                     ])
                
                     ], fluid=True) 
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
    if value in ('dvp','gardiner','lakeshore','are','queen','front','wellington'):
        return {'display':'inline'}
    else:
        return {'display':'none'}

@app.callback([Output('baseline-description', 'style'),
               Output('tt-long', 'style'),
               Output('tt-short', 'style')],
              [Input("baseline-toggle", 'value')],)
def display_baseline(value):
    '''If baseline is clicked then display baseline description'''
    if value == 1:
        return {'display':'inline'}, {'display':'block'}, {'display':'block'}
    else:
        return {'display':'none'}, {'display':'none'}, {'display':'none'}                      


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
        selected_date = pd.to_datetime(selected_date).normalize()
        return [{'label': period, 'value': period}
                for period
                in get_timeperiods_for_date(selected_date)]
    else:
        return [{'label': period, 'value': period}
                for period
                in TIMEPERIODS[TIMEPERIODS['day_type'] == day_type]['period']]


@app.callback([Output(STEP2, 'children'),
                Output(TABLE_TITLE, 'children')],
              [Input(CONTROLS['date_picker'], 'date'),
               Input(CONTROLS['day_types'], 'value'),
               Input(CONTROLS['date_range_type'], 'value'),
               Input('tabs', 'value')]) 
def generate_step_two(selected_date, day_type, daterange_type, tabs):
    tabs_name = DATA[DATA['street'] == STREETS[tabs][0]]['street_short'].iloc[0]

    if DATERANGE_TYPES[daterange_type] == 'Select Date': 
        step2 =  'Step 2: Select the date'
        table_title = str(tabs_name) + ' - Average Daily Travel Time (mins)'
    elif DATERANGE_TYPES[daterange_type] == 'Select Week':
        step2 = 'Step 2: Select the week'
        table_title = str(tabs_name) + ' - Average Weekly Travel Time (mins)' 
    elif DATERANGE_TYPES[daterange_type] == 'Select Month':
        step2 = 'Step 2: Select the month'
        table_title = str(tabs_name) + ' - Average Monthly Travel Time (mins)'

    return step2, table_title



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
        selected_date = pd.to_datetime(selected_date).normalize()
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
        dt = pd.to_datetime(date_picked).normalize()
        if dt.weekday() > 4:
            return 'Weekend'
        else: 
            return 'Weekday'
    else:
        return day_type 
# add an input here
@app.callback(Output(TABLE_DIV_ID, 'children'),
              [Input(CONTROLS['timeperiods'], 'value'),
               Input(CONTROLS['day_types'], 'value'),
               Input(CONTROLS['date_range_type'], 'value'),
               Input(CONTROLS['date_range'], 'value'),
               Input(CONTROLS['date_picker'], 'date'),
               Input('tabs', 'value'),
               Input("baseline-toggle", 'value')],
              [State(div_id, 'children') for div_id in SELECTED_STREET_DIVS.values()])
def update_table(period, day_type, daterange_type, date_range_id, date_picked=MOST_RECENT_WEEKDAY, orientation='gardiner', baseline_state=1, *state_data):
    '''Generate HTML table of before-after travel times based on selected
    day type, time period, and remember which row was previously selected
    '''
    LOGGER.debug('Update table: daterange_type:' + str(daterange_type) 
                 + ', period ' + str(period)
                 + ', day_type ' + str(day_type) 
                 + ', date_range_id ' + str(date_range_id) 
                 + ', orientation  ' + str(orientation)     )
    if DATERANGE_TYPES[daterange_type] == 'Select Date':
       date_range_id = pd.to_datetime(date_picked).normalize()
    state_index = list(STREETS.keys()).index(orientation)
    selected_street = state_data[state_index]

    table = generate_table(selected_street, day_type, period,
                           orientation=orientation,
                           daterange_type=daterange_type,
                           date_range_id=date_range_id,
                           baseline_state=baseline_state)
    if DATERANGE_TYPES[daterange_type] == 'Select Date':
        LOGGER.debug('Table returned for Selected Date: %s', date_range_id.strftime('%a %b %d'))
    elif DATERANGE_TYPES[daterange_type] == 'Select Week':
        LOGGER.debug('Table returned for Week')
    elif DATERANGE_TYPES[daterange_type] == 'Select Month':
        LOGGER.debug('Table returned for Month')

    return table

@app.callback(Output(CONTROLS['date_range_span'], 'style'),
              [Input(CONTROLS['date_range_type'], 'value')])
def hide_reveal_date_range(daterange_type):
    if DATERANGE_TYPES[daterange_type] != 'Select Date':
        return {'display':'inline'}
    else:
        return {'display':'none'}

@app.callback(Output(CONTROLS['day_types'], 'style'),
              [Input(CONTROLS['date_range_type'], 'value')])
def hide_reveal_day_types(daterange_type):
    if DATERANGE_TYPES[daterange_type] != 'Select Date':
        return {'display':'inline'}
    else:
        return {'display':'none'}

@app.callback(Output(CONTROLS['date_picker_span'], 'style'),
              [Input(CONTROLS['date_range_type'], 'value')])
def hide_reveal_date_picker(daterange_type):
    LOGGER.debug('Hide reveal date picker, daterange_type: ' + str(daterange_type))
    if DATERANGE_TYPES[daterange_type] == 'Select Date':
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
    if DATERANGE_TYPES[daterange_type] == 'Select Date':
        date_range_id        
    #if not RANGES[daterange_type].empty and date_range_id <= len(RANGES[daterange_type]):
    #    return date_range_id
    elif  DATERANGE_TYPES[daterange_type] == 'Select Week':
        return WEEKS['week_number'].iloc[0]    
    elif  DATERANGE_TYPES[daterange_type] == 'Select Month':
        return MONTHS['month_number'].iloc[0] 


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
            return [html.B(DIRECTIONS[orientation][dir_id] + ': '),
                    'from ' + from_to['from_intersection'] + ' to ' + from_to['to_intersection']]

[create_update_street_name(i) for i in [0,1]]

@app.callback([Output(STREET_TITLE, 'children'),
                Output(TIME_TITLE, 'children')], 
                  [*[Input(div_id, 'children') for div_id in SELECTED_STREET_DIVS.values()],
                   Input('tabs', 'value'),
                   Input(CONTROLS['timeperiods'], 'value'),
                   Input(CONTROLS['day_types'], 'value')])
def update_street_name(*args):
        #Use the input for the selected street from the orientation of the current tab
    *selected_streets, orientation, timeperiod, day_type = args
    street = selected_streets[list(SELECTED_STREET_DIVS.keys()).index(orientation)]
    table_street = DATA[DATA['street'] == street]['street1'].iloc[0]
    main_street = DATA[DATA['street'] == STREETS[orientation][0]]['street_short'].iloc[0]
    main_name = main_street + ': '+ table_street
    time_range = TIMEPERIODS[(TIMEPERIODS['period'] == timeperiod) & (TIMEPERIODS['day_type'] == day_type)].iloc[0]['period_range']
    time_range_title = day_type + ' ' + timeperiod + ' (' + time_range + ')'
    return main_name, time_range_title

def create_update_graph_div(graph_number):
    '''Dynamically create callback functions to update graphs based on a graph number
    '''
    @app.callback(Output(GRAPHDIVS[graph_number], 'children'),
                  [Input(CONTROLS['timeperiods'], 'value'),
                   Input(CONTROLS['day_types'], 'value'),
                   Input('tabs', 'value'),
                   *[Input(div_id, 'children') for div_id in SELECTED_STREET_DIVS.values()],
                   Input(CONTROLS['date_range_type'], 'value'),
                   Input(CONTROLS['date_range'], 'value'),
                   Input("baseline-toggle", 'value'),],
                  [State(CONTROLS['date_picker'], 'date')])
    def update_graph(period, day_type, orientation, *args):
        '''Update the graph for a street direction based on the selected:
         - street
         - time period
         - day type
        '''
        *selected_streets, daterange_type, date_range, baseline_state, date_picked = args
        #Use the input for the selected street from the orientation of the current tab
        try:
            if DATERANGE_TYPES[daterange_type] == 'Select Date':
                date_range = pd.to_datetime(date_picked).normalize()
            
            street = selected_streets[list(SELECTED_STREET_DIVS.keys()).index(orientation)]
            LOGGER.debug('Updating graph %s, for street: %s, period: %s, day_type: %s, daterange_type: %s, date_range: %s',
                        GRAPHS[graph_number], street, period, day_type, daterange_type, date_range)
            figure = generate_figure(street,
                                    DIRECTIONS[orientation][graph_number],
                                    period=period,
                                    day_type=day_type,
                                    daterange_type=daterange_type,
                                    date_range_id=date_range,
                                    baseline_state=baseline_state)
                                    
            if figure: 
                return html.Div(dcc.Graph(id = GRAPHS[graph_number],
                                        figure = figure,
                                        config={'displayModeBar': False}
                                                                            ))
            else:
                return html.Div(className = 'nodata')
        except IndexError:
            return html.Div(className = 'nodata')

    update_graph.__name__ = 'update_graph_' + GRAPHS[graph_number]
    return update_graph

[create_update_graph_div(i) for i in range(len(GRAPHS))]

if __name__ == '__main__':
    app.run_server(debug=True)
