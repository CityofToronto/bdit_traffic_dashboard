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
                         SELECT 
                            (CASE WHEN (start_crossstreet = 'Bayview Ramp' OR start_crossstreet = 'Don Mills') AND (end_crossstreet = 'Bayview Ramp' OR end_crossstreet = 'Don Mills')
                            THEN 'DVP between Bayview Ramp and Don Mills'
                            WHEN (start_crossstreet = 'Bayview Ramp' OR start_crossstreet = 'Dundas') AND (end_crossstreet = 'Bayview Ramp' OR end_crossstreet = 'Dundas')
                            THEN 'DVP between Bayview Ramp and Dundas'
                            WHEN (start_crossstreet = 'Wynford' OR start_crossstreet = 'Don Mills') AND (end_crossstreet = 'Wynford' OR end_crossstreet = 'Don Mills')
                            THEN 'DVP between Don Mills and Wynford'
                            WHEN (start_crossstreet = 'Wynford' OR start_crossstreet = 'Lawrence') AND (end_crossstreet = 'Wynford' OR end_crossstreet = 'Lawrence')
                            THEN 'DVP between Lawrence and Wynford'
                            WHEN (start_crossstreet = 'York Mills' OR start_crossstreet = 'Lawrence') AND (end_crossstreet = 'York Mills' OR end_crossstreet = 'Lawrence')
                            THEN 'DVP between Lawrence and York Mills'
                            END) As street, 
                         direction, dt AS date, day_type, 'DVP Lane Restrictions' AS category, period, round(tt/60,1) tt, 
                         CASE WHEN dt = first_value(dt) OVER (PARTITION BY direction, day_type, period ORDER BY dt DESC)
                         THEN 1 ELSE 0 END AS most_recent,
                         study_period, week_number, month_number, start_crossstreet, end_crossstreet
                         FROM data_analysis.dvp_blip_daily 
                         LEFT OUTER JOIN data_analysis.dvp_weeks weeks ON dt >= week AND dt < week + INTERVAL '1 week'
                         LEFT OUTER JOIN data_analysis.dvp_months months ON dt >= month AND dt < month + INTERVAL '1 month'
                         WHERE study_period = 'DVP Lane Restrictions 1' or study_period = 'DVP Lane Restrictions 2'
                         ''', con)

ALTERNATE_DATA = pandasql.read_sql('''
                                    SELECT name1 street, d.street main_street, d.direction, d.start_street, d.end_street,
                                     d.study_period, 'DVP Lane Restrictions' AS category, date_range, d.period, d.tt, d.day_type, 
                                     week_number, month_number, LOWER(date_range) as start_week, UPPER(date_range) AS end_week
                                    FROM 
                                    (SELECT DISTINCT ON (d1.street, d1.start_street, d1.end_street) d1.street, d1.start_street, d1.end_street, 
                                    d1.street || ' Between ' || d1.start_street || ' and ' || d1.end_street as name1
                                    FROM data_analysis.dvp_alt_routes_here_weekly d1, data_analysis.dvp_alt_routes_here_weekly d2 
                                    WHERE d1.street = d2.street and d1.start_street = d2.end_street and d1.direction in ('NB', 'EB')
                                    ORDER BY d1.street) n
                                    JOIN
                                    (SELECT * FROM data_analysis.dvp_alt_routes_here_weekly) d
                                    ON n.street = d.street AND ( (n.start_street = d.start_street AND n.end_street = d.end_street) OR (n.start_street = d.end_street AND n.end_street = d.start_street)) 
                                    LEFT OUTER JOIN data_analysis.dvp_weeks weeks ON  date_range @> week 
                                    LEFT OUTER JOIN data_analysis.dvp_months months ON (LOWER(date_range) >= month AND LOWER(date_range) <= month + INTERVAL '1 month')
                                    ''', con)

BASELINE = pandasql.read_sql('''SELECT (CASE WHEN (start_crossstreet = 'Bayview Ramp' OR start_crossstreet = 'Don Mills') AND (end_crossstreet = 'Bayview Ramp' OR end_crossstreet = 'Don Mills')
                           THEN 'DVP between Bayview Ramp and Don Mills'
                           WHEN (start_crossstreet = 'Bayview Ramp' OR start_crossstreet = 'Dundas') AND (end_crossstreet = 'Bayview Ramp' OR end_crossstreet = 'Dundas')
                           THEN 'DVP between Bayview Ramp and Dundas'
                           WHEN (start_crossstreet = 'Wynford' OR start_crossstreet = 'Don Mills') AND (end_crossstreet = 'Wynford' OR end_crossstreet = 'Don Mills')
                           THEN 'DVP between Don Mills and Wynford'
                           WHEN (start_crossstreet = 'Wynford' OR start_crossstreet = 'Lawrence') AND (end_crossstreet = 'Wynford' OR end_crossstreet = 'Lawrence')
                           THEN 'DVP between Lawrence and Wynford'
                           WHEN (start_crossstreet = 'York Mills' OR start_crossstreet = 'Lawrence') AND (end_crossstreet = 'York Mills' OR end_crossstreet = 'Lawrence')
                           THEN 'DVP between Lawrence and York Mills'
                           END) As street,
                            direction, start_crossstreet from_intersection, end_crossstreet to_intersection,
                            b.day_type, b.period, time_range as period_range, round(tt,1) tt
                            FROM data_analysis.dvp_blip_summary b
                            JOIN data_analysis.dvp_periods p ON b.period = p.period and b.day_type = p.day_type
                            WHERE study_period = 'Baseline 1: Jul-Aug 2018' ''',
                            con)

ALTERNATE_BASELINE = pandasql.read_sql(''' 
                                    SELECT name1 street, d.street main_street, d.direction, d.start_street from_intersection, d.end_street to_intersection, d.study_period AS category, d.period, d.tt, d.day_type
                                        FROM 
                                        (SELECT DISTINCT ON (d1.street, d1.start_street, d1.end_street) d1.street, d1.start_street, d1.end_street, 
                                        d1.street || ' Between ' || d1.start_street || ' and ' || d1.end_street as name1
                                        FROM data_analysis.dvp_here_summaryb_conf30 d1, data_analysis.dvp_here_summaryb_conf30 d2 
                                        WHERE d1.street = d2.street and d1.start_street = d2.end_street and d1.direction in ('NB', 'EB')
                                        ORDER BY d1.street) n
                                        JOIN 
                                        (SELECT * FROM data_analysis.dvp_here_summaryb_conf30) d
                                        ON n.street = d.street AND ( (n.start_street = d.start_street AND n.end_street = d.end_street) OR (n.start_street = d.end_street AND n.end_street = d.start_street)) 
                                        WHERE d.study_period = 'Baseline 2: May-Jun 2019'
                                        ''',
                                        con)

WEEKS = pandasql.read_sql('''SELECT * FROM data_analysis.dvp_weeks
                        WHERE CURRENT_DATE > (week + INTERVAL '7 days') 
                         ''', con)
						 
MONTHS = pandasql.read_sql('''SELECT * FROM data_analysis.dvp_months
                         ''', con, parse_dates=['month'])
WEEKS['label'] = 'Week ' + WEEKS['week_number'].astype(str) + ': ' + WEEKS['week'].astype(str)
WEEKS.sort_values(by='week_number', inplace=True)
MONTHS['label'] = 'Month ' + MONTHS['month_number'].astype(str) + ': ' + MONTHS['month'].dt.strftime("%b '%y")
RANGES = [pd.DataFrame(), pd.DataFrame(), WEEKS, MONTHS]
CATEGORY_NAME_PILOT = 'DVP Lane Restrictions'

con.close()

###################################################################################################
#                                                                                                 #
#                                        Constants                                                #
#                                                                                                 #
###################################################################################################

# Data management constants

STREETS = OrderedDict(ns=['DVP between Bayview Ramp and Don Mills', 'DVP between Bayview Ramp and Dundas', 'DVP between Don Mills and Wynford', 
                    'DVP between Lawrence and Wynford', 'DVP between Lawrence and York Mills'], 
                    alternate=[
                            "Bayview Between DVP and Eglinton",
                            "Bayview Between Eglinton and Lawrence",
                            "Bayview Between Lawrence and York Mills",
                            "Bayview Between York Mills and 401",
                            "Don Mills Between DVP and Eglinton",
                            "Don Mills Between Eglinton and Lawrence",
                            "Don Mills Between Lawrence and York Mills",
                            "Don Mills Between York Mills and Sheppard",
                            "Leslie Between Eglinton and Lawrence",
                            "Leslie Between Lawrence and York Mills",
                            "Leslie Between York Mills and 401",
                            "Victoria Park Ave Between Eglinton and Lawrence",
                            "Victoria Park Ave Between Ellesmere and 401",
                            "Victoria Park Ave Between Lawrence and Ellesmere",
                            "Victoria Park Ave Between St Clair and Eglinton",
                            "Woodbine Between Danforth and OConnor",
                            "Woodbine Between Queen and Danforth"
                    ], 
                    alternate_ew = [ 
                            "Lawrence Between Don Mills and DVP",
                            "Lawrence Between DVP and Victoria Park Ave",
                            "Lawrence Between Leslie and Don Mills",
                            "OConnor Between Broadview and Don Mills",
                            "OConnor Between Don Mills and Woodbine",
                            "OConnor Between Woodbine and Eglinton",
                            "York Mills Between Bayview and Leslie",
                            "York Mills Between Don Mills and DVP",
                            "York Mills Between DVP and Victoria Park Ave",
                            "York Mills Between Leslie and Don Mills"
                    ])

DROPDOWN_MAIN_STREETS = OrderedDict(
    alternate=['Bayview', 'Don Mills', 'Leslie', 'Victoria Park Ave', 'Woodbine'], 
    alternate_ew=['Lawrence', 'OConnor', 'York Mills']
)
                    
DIRECTIONS = OrderedDict(ns=['NB', 'SB'], alternate=['NB', 'SB'], alternate_ew=['EB', 'WB'])
DATERANGE = [DATA['date'].min(), DATA['date'].max()]

DATERANGE_ALTERNATE = [ALTERNATE_DATA['start_week'].min(), ALTERNATE_DATA['end_week'].max()]

TIMEPERIODS = BASELINE[['day_type','period', 'period_range']].drop_duplicates().sort_values(['day_type', 'period_range'])
THRESHOLD = 1

#Max travel time to fix y axis of graphs, based on the lowest of the max tt in the data or 20/30 for either graph
MAX_TIME = dict(ns=min(25, DATA[DATA['direction'].isin(DIRECTIONS['ns'])].tt.max()), 
                alternate=min(25, ALTERNATE_DATA[ALTERNATE_DATA['direction'].isin(DIRECTIONS['alternate'])].tt.max()), 
                alternate_ew=min(25, ALTERNATE_DATA[ALTERNATE_DATA['direction'].isin(DIRECTIONS['alternate_ew'])].tt.max())) 

# Plot appearance
TITLE = 'Don Valley Parkway Lane Closures: Vehicular Travel Time Monitoring'
BASELINE_LINE = {'color': 'rgba(128, 128, 128, 0.7)',
                 'width': 4}
PLOT = dict(margin={'t':10, 'b': 40, 'r': 40, 'l': 40, 'pad': 8})
PLOT_COLORS = dict(pilot='rgb(102,1,89)',
                   baseline='rgba(128, 128, 128, 1.0)',
                   selected='rgb(13,159,115)')
FONT_FAMILY = '"Libre Franklin", sans-serif'

# IDs for divs
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
                date_picker_span='date-picker-span', 
                main_street='main-streets')
DATERANGE_TYPES = ['Last Day', 'Select Date', 'Select Week', 'Select Month']
GRAPHS = ['nb_eb_graph', 'sb_wb_graph']
GRAPHDIVS = ['nb_sb_graph_div', 'sb_wb_graph_div']

LAYOUTS = dict(streets='streets-div', alternate_ns='alternate-ns', alternate_ew='alternate-ew')

INITIAL_STATE = {orientation:STREETS[orientation][0] for orientation in STREETS}

###################################################################################################
#                                                                                                 #
#                                   App Configuration                                             #
#                                                                                                 #
###################################################################################################
metas = [{'name':"viewport",
         'content':"width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no"}]

app = dash.Dash(__name__, meta_tags=metas)
app.config['suppress_callback_exceptions'] = True
app.title=TITLE
server = app.server

app.config.update({
        'requests_pathname_prefix': '/dvp-dashboard/',
})

server.secret_key = os.environ.get('SECRET_KEY', 'my-secret-key')

FORMAT = '%(asctime)s %(name)-2s %(levelname)-2s %(message)s'
logging.basicConfig(level=logging.DEBUG, format=FORMAT)

LOGGER = logging.getLogger(__name__)

###################################################################################################
#                                                                                                 #
#                                   Data Manipulation                                             #
#                                                                                                 #
###################################################################################################

def deserialise_state(clicks_json):
    '''Turn the state stored in hidden div into python dict
    '''
    return json.loads(clicks_json, object_pairs_hook=OrderedDict)

def serialise_state(clicks_dict):
    '''Turn python dict of the clicks state of the table into json
    to store in hidden div
    '''
    return json.dumps(clicks_dict)

def pivot_order(df, orientation = 'ns', date_range_type=1):
    '''Pivot the dataframe around street directions and order by STREETS global var
    '''
    if DATERANGE_TYPES[date_range_type] in ['Last Day', 'Select Date'] and 'date' in df.columns:
        pivoted = df.pivot_table(index=['street', 'date'],
                                columns='direction',
                                values='tt').reset_index()
    else:
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


def selected_data_alternate(data, daterange_type=2, date_range_id=1):
    '''Returns a boolean column indicating whether the provided data was selected or not
    '''
    LOGGER.debug("in selected data alternate, daterange_type: {}".format(daterange_type))
    if DATERANGE_TYPES[daterange_type] == 'Select Week':
        date_filter = data['week_number'] == date_range_id
    elif DATERANGE_TYPES[daterange_type] == 'Select Month':
        date_filter = data['month_number'] == date_range_id
    return date_filter

def filter_table_data(period, day_type, orientation='ns', daterange_type=0, date_range_id=1, main_street_id=None):
    '''Return data aggregated and filtered by period
    '''

    if orientation == 'ns':

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

    else: 
        # weekly data - alternate route data
        date_filter = selected_data_alternate(ALTERNATE_DATA, daterange_type, date_range_id)
        #current data
        filtered = ALTERNATE_DATA[(ALTERNATE_DATA['period'] == period) &
                        (ALTERNATE_DATA['day_type'] == day_type) &
                        (ALTERNATE_DATA['direction'].isin(DIRECTIONS[orientation])) &
                        (ALTERNATE_DATA['category'] != 'Excluded') &
                        (ALTERNATE_DATA['main_street'] == DROPDOWN_MAIN_STREETS[orientation][main_street_id]) &
                        (date_filter)]
        pivoted = pivot_order(filtered, orientation, daterange_type)

        #baseline data
        filtered_base = ALTERNATE_BASELINE[(ALTERNATE_BASELINE['period'] == period) &
                                (ALTERNATE_BASELINE['day_type'] == day_type) &
                                (ALTERNATE_BASELINE['main_street'] == DROPDOWN_MAIN_STREETS[orientation][main_street_id]) &
                                (ALTERNATE_BASELINE['direction'].isin(DIRECTIONS[orientation]))]
        pivoted_baseline = pivot_order(filtered_base, orientation)

    return (pivoted, pivoted_baseline)


def graph_bounds_for_date_range(daterange_type, date_range_id):
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


def graph_bounds_for_date_range_alternate(daterange_type, date_range_id):
    if DATERANGE_TYPES[daterange_type] == 'Last Day':
        end_range = DATERANGE_ALTERNATE[1] + relativedelta(days=1)
        start_range = DATERANGE_ALTERNATE[1] - relativedelta(weeks=2)
        date_picked = date_range_id
    elif DATERANGE_TYPES[daterange_type] in ['Select Date', 'Select Week']:
        if DATERANGE_TYPES[daterange_type] == 'Select Date':
            date_picked = date_range_id
        else:
            date_picked = WEEKS[WEEKS['week_number'] == date_range_id]['week'].iloc[0]
        start_of_week = date_picked - relativedelta(days=date_picked.weekday())
        start_range = max(start_of_week - relativedelta(weeks=1), DATERANGE_ALTERNATE[0])
        end_range = min(start_of_week + relativedelta(weeks=2), DATERANGE_ALTERNATE[1] + relativedelta(days=1))
    elif DATERANGE_TYPES[daterange_type] == 'Select Month':
        date_picked = MONTHS[MONTHS['month_number'] == date_range_id]['month'].iloc[0].date()
        if date_picked == DATERANGE_ALTERNATE[1].replace(day=1):
            #End of data within month picked, display last month of data
            start_range = max(DATERANGE_ALTERNATE[1] - relativedelta(months=1), DATERANGE_ALTERNATE[0])
        else:
            start_range = max(date_picked - relativedelta(days=date_picked.day - 1), DATERANGE_ALTERNATE[0])
        end_range = min(date_picked - relativedelta(days=date_picked.day - 1) + relativedelta(months=1),
                        DATERANGE_ALTERNATE[1] + relativedelta(days=1))
    else:
        raise ValueError('Wrong daterange_type provided: {}'.format(daterange_type))
    LOGGER.debug('Filtering (for alternate) for %s. Date picked: %s, Start Range: %s, End Range: %s',
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


    if filtered_daily.empty:
        LOGGER.debug("filtered_daily dataframe in filter_graph_data function is empty")
        return (pd.DataFrame(), pd.DataFrame(), pd.DataFrame)
        # raise ValueError("filtered_daily dataframe in filter_graph_data function is empty")

    base_line = BASELINE[(BASELINE['street'] == street) &
                         (BASELINE['period'] == period) &
                         (BASELINE['day_type'] == day_type) &
                         (BASELINE['direction'] == direction)]

    if base_line.empty:
        LOGGER.debug("base_line dataframe in filter_graph_data function is empty")
        return (pd.DataFrame(), pd.DataFrame(), pd.DataFrame)
        #raise ValueError("base_line dataframe in filter_graph_data function is empty")

    base_line_data = filtered_daily[filtered_daily['category'] == 'Baseline']

    selected_filter = selected_data(filtered_daily, daterange_type, date_range_id)

    pilot_data = filtered_daily[(filtered_daily['category'] == CATEGORY_NAME_PILOT) &
                                ~(selected_filter)]

    pilot_data_selected = filtered_daily[(filtered_daily['category'] == CATEGORY_NAME_PILOT) &
                                         (selected_filter)]
    return (base_line, pilot_data, pilot_data_selected)




def filter_graph_data_weekly(street, direction, orientation, day_type='Weekday', period='AMPK',
                      daterange_type=2, date_range_id=1):
    '''Filter dataframes by street, direction, day_type, and period
    Returns a filtered baseline, and a filtered current dataframe
    '''

    daterange = graph_bounds_for_date_range_alternate(daterange_type, date_range_id)

    filtered_weekly = ALTERNATE_DATA[(ALTERNATE_DATA['street'] == street) &
                          (ALTERNATE_DATA['period'] == period) &
                          (ALTERNATE_DATA['day_type'] == day_type) &
                          (ALTERNATE_DATA['direction'] == direction) & 
                          (ALTERNATE_DATA['direction'].isin(DIRECTIONS[orientation])) &
                          (ALTERNATE_DATA['start_week'] >= daterange[0]) &
                          (ALTERNATE_DATA['end_week'] < daterange[1]) 
                          ]

    if filtered_weekly.empty:
        LOGGER.debug("filtered_weekly dataframe in filter_graph_data weekly function is empty")
        return (pd.DataFrame(), pd.DataFrame(), pd.DataFrame)
        #raise ValueError("filtered_daily dataframe in filter_graph_data weekly function is empty")


    base_line = ALTERNATE_BASELINE[(ALTERNATE_BASELINE['street'] == street) &
                         (ALTERNATE_BASELINE['period'] == period) &
                         (ALTERNATE_BASELINE['day_type'] == day_type) &
                         (ALTERNATE_BASELINE['direction'].isin(DIRECTIONS[orientation])) &
                         (ALTERNATE_BASELINE['direction'] == direction)]

    if base_line.empty:
        LOGGER.debug("baseline dataframe in filter_graph_data weekly function is empty")
        return (pd.DataFrame(), pd.DataFrame(), pd.DataFrame)
        #raise ValueError("base_line dataframe in filter_graph_data weekly function is empty")

    base_line_data = filtered_weekly[filtered_weekly['category'] == 'Baseline']


    if DATERANGE_TYPES[daterange_type] == 'Last Day' or DATERANGE_TYPES[daterange_type] == 'Select Date':
        # since we're only doing weekly or monthly times, these should return nothing
        pilot_data = pd.DataFrame()
        pilot_data_selected = pd.DataFrame()   

    else: 

        date_filter = selected_data_alternate(ALTERNATE_DATA, daterange_type, date_range_id)

        selected_filter = selected_data_alternate(filtered_weekly, daterange_type, date_range_id)

        pilot_data = filtered_weekly[(filtered_weekly['category'] == CATEGORY_NAME_PILOT) &
                                    ~(selected_filter)]

        pilot_data_selected = filtered_weekly[(filtered_weekly['category'] == CATEGORY_NAME_PILOT) &
                                            (selected_filter)]
    return (base_line, pilot_data, pilot_data_selected)





def get_orientation_from_dir(direction):
    '''Get the orientation of the street based on its direction'''
    for orientation, direction_list in DIRECTIONS.items():
        if direction in direction_list:
            return orientation

def get_timeperiods_for_date(selected_date):
    '''Get available timeperiods for the selected_data'''
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

def generate_row(df_row, baseline_row, selected, orientation='ns'):
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

def generate_table(selected_street, day_type, period, orientation='ns', daterange_type=0, date_range_id=1, main_street_id=0):
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
    
    if daterange_type < 2 and orientation in ['alternate', 'alternate_ew']:
        daterange_type = 2
        date_range_id = 1

    LOGGER.debug('Generate table: daterange_type:' + str(daterange_type) 
                 + ', period: ' + str(period)
                 + ', day_type: ' + str(day_type) 
                 + ', date_range_id: ' + str(date_range_id) 
                 + ', orientation: ' + str(orientation) 
                 + ', selected_street: ' + str(selected_street)
                 + ', main_street_id ' + str(main_street_id))
    filtered_data, baseline = filter_table_data(period, day_type, orientation, daterange_type, date_range_id, main_street_id)
    #Current date for the data, to replace "After" header
    if DATERANGE_TYPES[daterange_type] in ['Last Day', 'Select Date']:
        day = filtered_data['date'].iloc[0].strftime('%a %b %d')
    elif DATERANGE_TYPES[daterange_type] == 'Select Week':
        day = 'Week ' + str(date_range_id)
    elif DATERANGE_TYPES[daterange_type] == 'Select Month':
        day = 'Month ' + str(date_range_id)

    rows = []
    for baseline_row, street in zip(baseline.iterrows(), baseline['street'].values):
    # Generate a row for each street, keeping in mind the selected_street (which row is clicked)
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


def generate_graph_data_weekly(data, **kwargs):
    #for val in data['start_week'].
    return dict(x=pd.to_datetime(data['start_week']).dt.strftime("%b %d %Y") + " to " + pd.to_datetime(data['end_week']).dt.strftime("%b %d %Y"),
                y=data['tt'],
                text=data['tt'].round(),
                #text= "Week of " + pd.to_datetime(data['start_week']).dt.strftime("%b %d %Y") + " to " + pd.to_datetime(data['end_week']).dt.strftime("%b %d %Y"),
                hoverinfo='x+y',
                textposition='inside',
                type='bar',
                #category_orders=data['start_week'],
                insidetextfont=dict(color='rgba(255,255,255,1)',
                                    size=12),
                **kwargs)


def generate_figure(street, direction, tab, day_type='Weekday', period='AMPK',
                    daterange_type=0, date_range_id=1):
    '''Generate a Dash bar chart of average travel times by day
    '''

    if tab == 'ns':
        base_line, after_df, selected_df = filter_graph_data(street,
                                                                  direction,
                                                                  day_type,
                                                                  period,
                                                                  daterange_type,
                                                                  date_range_id, 
                                                                  )
        x_axes_name = 'Date'

    else:
        # weekly data
        base_line, after_df, selected_df = filter_graph_data_weekly(street,
                                                                  direction,
                                                                  tab,
                                                                  day_type,
                                                                  period,
                                                                  daterange_type,
                                                                  date_range_id, 
                                                                  )
        x_axes_name = 'Week'

    orientation = get_orientation_from_dir(direction)
    data = []
    if after_df.empty:
        if selected_df.empty:
            return None
    else:
        if tab == 'ns':
            pilot_data = generate_graph_data(after_df,
                                     marker=dict(color=PLOT_COLORS['pilot']),
                                     name='Lane Closure')
        else:
            pilot_data = generate_graph_data_weekly(after_df,
                                     marker=dict(color=PLOT_COLORS['pilot']),
                                     name='Lane Closure')

        data.append(pilot_data)

    if tab == 'ns':
        pilot_data_selected = generate_graph_data(selected_df,
                                                marker=dict(color=PLOT_COLORS['selected']),
                                                name='Selected')
        
    else:
        pilot_data_selected = generate_graph_data_weekly(selected_df,
                                                marker=dict(color=PLOT_COLORS['selected']),
                                                name='Selected')

    data.append(pilot_data_selected)

    '''
    if not base_df.empty:
        baseline_data = generate_graph_data(base_df,
                                            marker=dict(color=PLOT_COLORS['baseline']),
                                            name='Baseline')
        data.append(baseline_data)
    '''
    
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
                  height=350,
                  barmode='relative',
                  xaxis=dict(title=x_axes_name,
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
             children=[
                 dcc.RadioItems(id=CONTROLS['timeperiods'],
                                      value=TIMEPERIODS.iloc[0]['period'],
                                      className='radio-toolbar'),
                       dcc.RadioItems(id=CONTROLS['day_types'],
                                      options=[{'label': day_type,
                                                'value': day_type,
                                                'id': day_type}
                                               for day_type in TIMEPERIODS['day_type'].unique()],
                                      value=TIMEPERIODS.iloc[0]['day_type'],
                                      className='radio-toolbar'),
                       html.Span(children=[
                           html.Span(dcc.Dropdown(id=CONTROLS['main_street'], value=0), style={'display':'none'}),
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
    html.Div(id=TABLE_DIV_ID, children=generate_table(INITIAL_STATE['ns'], 'Weekday', 'AM Peak')),
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




STREETS_LAYOUT_ALTERNATE_NS = html.Div(children=[html.Div(children=[
    html.H2(id=TIMEPERIOD_DIV, children='Weekday AM Peak'),
    html.Button(id=CONTROLS['toggle'], children='Show Filters'),
    html.Div(id=CONTROLS['div_id'],
             children=[dcc.RadioItems(id=CONTROLS['timeperiods'],
                                      value=TIMEPERIODS.iloc[0]['period'],
                                      className='radio-toolbar'),
                       dcc.RadioItems(id=CONTROLS['day_types'],
                                      options=[{'label': day_type,
                                                'value': day_type,
                                                'id': day_type}
                                               for day_type in TIMEPERIODS['day_type'].unique()],
                                      value=TIMEPERIODS.iloc[0]['day_type'],
                                      className='radio-toolbar'),
                       html.Span(children=[
                        html.Span(dcc.Dropdown(id=CONTROLS['main_street'],
                           options=[{'label': label,
                                              'value': value}
                                             for value, label in enumerate(DROPDOWN_MAIN_STREETS['alternate'])],
                                             value=0,
                                             clearable=False),
                                             title='Select a street to filter table data'),
                           html.Span(dcc.Dropdown(id=CONTROLS['date_range_type'],
                                    options=[{'label': 'Select Week',
                                              'value': 2}, 
                                              {'label': 'Select Month',
                                              'value': 3
                                              }],
                                    value=2,
                                    clearable=False),
                                    title='Select a date range type to filter table data'),
                           html.Span(dcc.Dropdown(id=CONTROLS['date_range'],
                                                  options=generate_date_ranges(daterange_type=2),
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
    html.Div(id=TABLE_DIV_ID, children=generate_table(INITIAL_STATE['alternate'], 'Weekday', 'AM Peak', orientation='alternate',daterange_type=2)),
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
               ], id=LAYOUTS['alternate_ns'])




STREETS_LAYOUT_ALTERNATE_EW = html.Div(children=[html.Div(children=[
    html.H2(id=TIMEPERIOD_DIV, children='Weekday AM Peak'),
    html.Button(id=CONTROLS['toggle'], children='Show Filters'),
    html.Div(id=CONTROLS['div_id'],
             children=[dcc.RadioItems(id=CONTROLS['timeperiods'],
                                      value=TIMEPERIODS.iloc[0]['period'],
                                      className='radio-toolbar'),
                       dcc.RadioItems(id=CONTROLS['day_types'],
                                      options=[{'label': day_type,
                                                'value': day_type,
                                                'id': day_type}
                                               for day_type in TIMEPERIODS['day_type'].unique()],
                                      value=TIMEPERIODS.iloc[0]['day_type'],
                                      className='radio-toolbar'),
                       html.Span(children=[
                            html.Span(dcc.Dropdown(id=CONTROLS['main_street'],
                                options=[{'label': label,
                                              'value': value}
                                             for value, label in enumerate(DROPDOWN_MAIN_STREETS['alternate_ew'])],
                                             value=0,
                                             clearable=False),
                                             title='Select a street to filter table data'),
                           html.Span(dcc.Dropdown(id=CONTROLS['date_range_type'],
                                    options=[{'label': 'Select Week',
                                              'value': 2}, 
                                              {'label': 'Select Month',
                                              'value': 3
                                              }],
                                    value=2,
                                    clearable=False),
                                    title='Select a date range type to filter table data'),
                           html.Span(dcc.Dropdown(id=CONTROLS['date_range'],
                                                  options=generate_date_ranges(daterange_type=2),
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
    html.Div(id=TABLE_DIV_ID, children=generate_table(INITIAL_STATE['alternate_ew'], 'Weekday', 'AM Peak', orientation='alternate_ew',daterange_type=2)),
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
               ], id=LAYOUTS['alternate_ew'])




app.layout = html.Div([
                       html.Div(children=[html.H1(children=TITLE, id='title')],
                                className='row twelve columns'),
                       html.Div(dcc.Tabs(children=[dcc.Tab(label='DVP', value='ns'),
                                      dcc.Tab(label='Alternate Routes (NB/SB)', value='alternate'), 
                                      dcc.Tab(label='Alternate Routes (EB/WB)', value='alternate_ew')],
                                value='ns',
                                id='tabs'), className='row twelve columns'),
                       html.Div(id=MAIN_DIV, className='row', children=[STREETS_LAYOUT]),
                       html.Div(children=html.H3(['Created by the ',
                                                  html.A('Big Data Innovation Team',
                                                         href="https://www1.toronto.ca/wps/portal/contentonly?vgnextoid=f98b551ed95ff410VgnVCM10000071d60f89RCRD")],
                                                         style={'text-align':'right',
                                                                'padding-right':'1em'}),
                                className='row'),
                       *[html.Div(id=div_id,
                                  style={'display': 'none'},
                                  children=[STREETS[orientation][0]])
                         for orientation, div_id in SELECTED_STREET_DIVS.items()]
                      ])


###################################################################################################
#                                                                                                 #
#                                         Controllers                                             #
#                                                                                                 #
###################################################################################################

'''
@app.callback(Output('date_range_type', 'value'), 
            [Input('tabs', 'value')],
            [State(CONTROLS['date_range_type'], 'value')]
            )
def update_date_range_type(tab, daterange_type):
    if tab in ['alternate', 'alternate_ew'] and daterange_type < 2:
        return 2
    else:
        return daterange_type
'''

@app.callback(Output(MAIN_DIV, 'children'),
              [Input('tabs', 'value')])
def render_content(tab):
    '''Change layout when you switch tabs'''
    if tab == 'ns':
        return STREETS_LAYOUT
    elif tab == 'alternate': 
        return STREETS_LAYOUT_ALTERNATE_NS
    else:
        return STREETS_LAYOUT_ALTERNATE_EW
	

@app.callback(Output(LAYOUTS['streets'], 'style'),
              [Input('tabs', 'value')])
def display_streets(value):
    '''Switch tabs display while retaining frontend client-side'''
    # if value in ['alternate', 'alternate_ew', 'ns']:
    if value in ['ns']:
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
               Input(CONTROLS['main_street'], 'value'),
               Input(CONTROLS['date_picker'], 'date'),
               Input('tabs', 'value')
               ],
              [State(div_id, 'children') for div_id in SELECTED_STREET_DIVS.values()])
def update_table(period, day_type, daterange_type, date_range_id, main_street_id=0, date_picked=datetime.today().date(), orientation='ns', *state_data):
    '''Generate HTML table of before-after travel times based on selected
    day type, time period, and remember which row was previously selected
    '''
    if orientation not in ['alternate', 'alternate_ew']:
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
        elif daterange_type == 3:
            LOGGER.debug('Table returned for Month')
        return table
    else:
        
        if daterange_type < 2: 
            daterange_type = 2
            date_range_id = 1
            

        # routes that only have weekly data
        state_index = list(STREETS.keys()).index(orientation)
        selected_street = state_data[state_index]
        LOGGER.debug('Update table: daterange_type:' + str(daterange_type) 
                        + ', period ' + str(period)
                        + ', day_type ' + str(day_type) 
                        + ', daterange_type ' + str(daterange_type)
                        + ', date_range_id ' + str(date_range_id) 
                        + ', orientation  ' + str(orientation)
                        + ', main street value/index' + str(main_street_id)
                        )
             
        table = generate_table(selected_street, day_type, period,
                                orientation=orientation,
                                daterange_type=daterange_type,
                                date_range_id=date_range_id,
                                main_street_id=main_street_id)
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

        Clicks are detected by comparing the previous number of clicks for that street with
        the previous state of that street. Previous state is stored in a json in a hidden 
        div for each street. This function is triggered by any click on any street in that
        tab (orientation) but we only check the street for this function.
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
        street = selected_streets[list(SELECTED_STREET_DIVS.keys()).index(orientation)]
        try:
            from_to = BASELINE[(BASELINE['street'] == street[0]) &
                               (BASELINE['direction'] == DIRECTIONS[orientation][dir_id])][['from_intersection',
                                                                               'to_intersection']].iloc[0]
        except IndexError:
            return html.Div(className = 'nodata')
        else:
            return [html.B(street[0] + ' ' + DIRECTIONS[orientation][dir_id] + ': '),
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

        if daterange_type < 2 and orientation in ['alternate', 'alternate_ew']:
            daterange_type = 2
            date_range_id = 1

        if daterange_type == 1:
            date_range = datetime.strptime(date_picked, '%Y-%m-%d').date()

        street = selected_streets[list(SELECTED_STREET_DIVS.keys()).index(orientation)]
        LOGGER.debug('Updating graph %s, for street: %s, period: %s, day_type: %s, daterange_type: %s, date_range: %s',
                        GRAPHS[graph_number], street, period, day_type, daterange_type, date_range)
        figure = generate_figure(street[0],
                                    DIRECTIONS[orientation][graph_number],
                                    orientation,
                                    period=period,
                                    day_type=day_type,
                                    daterange_type=daterange_type,
                                    date_range_id=date_range, 
                                    )
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
