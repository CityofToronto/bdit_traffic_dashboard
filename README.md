# Traffic Internal Dashboard

Dashboard for travel times for internal management. This dashboard displays average travel times by timeperiod for streets.

## App Organization

The layout of the code is inspired by the Model-View-Controller paradigm, specifically from [this Dash tutorial](https://dev.to/alysivji/interactive-web-based-dashboards-in-python-5hf). In addition, parameters and constants that someone would want to change when forking this are frontloaded in ALL_CAPS variables, in order to make modification easier. The names of DIVs used in callbacks are also stored in variables in order to reduce the risk of bugs since variable names are linted to see if they exist.

In addition to some of the plot styling being in these variables, [two css stylesheets](https://github.com/CityofToronto/bdit_traffic_dashboard/tree/master/assets) are loaded from local files.

### Detecting row clicks

This is handled by the `row_click` function, which is fired when the number of
clicks changes for any row (a Dash input). Which street was clicked can be
determined by the `dash.callback_context` (see ["**Q**: _How do I determine which Input has changed?_
"](https://dash.plot.ly/faqs)). The selected street for each tab is stored
in a hidden div, because [modifying global variables
is **bad news** in Dash](https://plot.ly/dash/sharing-data-between-callbacks).

When a row is clicked:

1. the `row_click` function determines the clicked street row from
   `dash.callback_context` and updates the `SELECTED_STREET_DIV` for that tab
2. which triggers updating the selected rows classes to add or remove the
   "selected" class.
3. which also triggers updating the graph.

### Creating multiple similar callbacks

Yes, you can put callback/function creation in a loop to iterate over, for example, every street. You just have to define an outer function that creates these callbacks, for example:

```python
def create_row_click_function(streetname):
    
    @app.callback(Output(streetname, 'className'),
                  [Input(SELECTED_STREET_DIV, 'children')])
    def update_clicked_row(street):
        if street:
            return generate_row_class(streetname == street[0])
        else:
            return generate_row_class(False)
    update_clicked_row.__name__ = 'update_row_'+streetname
    return update_clicked_row

#and then call the outer function in a loop
[create_row_click_function(key) for key in INITIAL_STATE.keys()]
```

## Data

Data from downtown Bluetooth detectors arrives in our database after initial filtering by bliptrack.

There it is grouped into five-minute-bins using the median to reduce the impact of extreme outliers.

The five-minute bins are grouped again into 30-minute bins using weighted average by the number of observations per five-minute-bin and separated by working day and nonworking day.

The 30-minute data collected before the pilot was plotted as scatterplots and quality checked. Major outliers were noted and removed from the baseline if deemed necessary.

The 30-minute data was then aggregated by time period, and pre-pilot data were averaged to get a baseline for a given period during the weekend or week.
This visualization depends on two tables, which are views in the data warehouse:

 - Baseline travel times for each (street, direction, day type, timeperiod)  ([source](https://github.com/CityofToronto/bdit_king_pilot_dashboard/blob/data_pipeline/bluetooth/sql/create-view-dash_baseline.sql))
 - Daily travel times for each (street, direction, day type, timeperiod) ([source](https://github.com/CityofToronto/bdit_king_pilot_dashboard/blob/data_pipeline/bluetooth/sql/create-view-dash_daily.sql))

Where day type is one of [Weekday, Weekend], and the time periods depend on the day type.

This code automatically connects to the database: either our local data warehouse or the heroku postgresql database. 

```python
database_url = os.getenv("DATABASE_URL")
if database_url is not None:
    con = connect(database_url)
else:
    import configparser
    CONFIG = configparser.ConfigParser()
    CONFIG.read('db.cfg')
    dbset = CONFIG['DBSETTINGS']
    con = connect(**dbset)
```

## Branching to monitor a new set of streets

The following steps must be followed:

1. Change the `'requests_pathname_prefix'` to something meaningful for the
   dashboard if deploying on the EC2, this is the breadcrumb to access the
   dashboard, e.g.: `/my_awesome_dashboard/`

## Deployment

### To Heroku

The app is currently deployed on Heroku by detecting updates to this branch and
automatically rebuilding the app.

### On the EC2

1. Clone the app with `git clone
   git@github.com:CityofToronto/bdit_traffic_dashboard.git`
2. Create a Python3 [virtual environment](https://docs.pipenv.org/en/latest/)
   and install necessary packages with `pipenv --three install`
3. Because we won't be able to access the running app on a specified port
   through the corporate firewall, you
   need to run it using a combination of `gunicorn` and `nginx`. Determine an
   available port and fire up the app with
   ```bash
   GUNICORN_CMD_ARGS="--bind=0.0.0.0:PORT --log-level debug --timeout 90" gunicorn  app:server
   ```
4. Pass the `PORT` you selected to one of the `nginx` admins and they will
   create a `location` for this app. 

### Data Syncing

Data is synced after every timeperiod by the following shell script

```bash
curl -n -X DELETE https://api.heroku.com/apps/APP-ID/dynos -H "Content-Type: application/json" -H "Accept: application/vnd.heroku+json; version=3"
psql -h rds.ip -d bigdata -c "\COPY (SELECT * FROM king_pilot.dash_daily) TO STDOUT WITH (HEADER FALSE);" | psql     postgres://username:password@heroku.database.uri:5432/database -c "TRUNCATE king_pilot.dash_daily; COPY king_pilot.dash_daily FROM STDIN;"
```

The first line forces the heroku app to restart, thus killing all connections to the heroku PostgreSQL database, enabling the `TRUNCATE` and `COPY` operation to happen in the second line, which syncs the `dash_daily` table in heroku, with the `dash_daily` VIEW in our data warehouse.

## Contribution

This branch, now that it is in production, is **protected**. Develop instead on a branch and, when an issue is complete, submit a pull request for staff to review.
