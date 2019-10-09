from airflow import DAG
from airflow.operators.bash_operator import BashOperator
from airflow.hooks.base_hook import BaseHook
from airflow.hooks.postgres_hook import PostgresHook
from datetime import datetime, timedelta

heroku_conn = BaseHook.get_connection("heroku_token")
heroku_token = heroku_conn.password

heroku_postgres = PostgresHook("heroku_postgres")
heroku_con = heroku_postgres.get_uri()

heroku_bot = PostgresHook("heroku_bot_rds")
rds_con = heroku_bot.get_uri()

default_args = {'owner':'rdumas',
                'depends_on_past':False,
                'start_date': datetime(2019, 9, 16),
                'email_on_failure': False,
                'email_on_success': False,
                'retries': 0,
                'retry_delay': timedelta(minutes=5),
                'env':{'HEROKU_TOKEN':heroku_token,
                      'heroku_string':heroku_con,
                      'heroku_rds':rds_con}
                }

with DAG('richmond_watermain_heroku',default_args=default_args, schedule_interval='0 7 * * *') as dag:

    restart_app = BashOperator(
                task_id = 'restart_app',
                bash_command = 'curl -n -X DELETE https://api.heroku.com/apps/6c97ad38-d833-4db3-a9d9-24c223ff8d07/dynos -H "Content-Type: application/json" -H "Accept: application/vnd.heroku+json; version=3" -H "Authorization: Bearer $HEROKU_TOKEN"', 
                retries = 0)

    sync_daily = BashOperator(
                task_id = 'sync_daily',
                bash_command = '''set -o pipefail; psql $heroku_rds -v "ON_ERROR_STOP=1" -c "\COPY (SELECT street, direction, date, day_type, category, period, tt, most_recent, week_number, month_number FROM data_analysis.richmond_dash_daily) TO STDOUT WITH (HEADER FALSE);" | psql $heroku_string -v "ON_ERROR_STOP=1" -c "TRUNCATE data_analysis.richmond_dash_daily; COPY data_analysis.richmond_dash_daily(street, direction, date, day_type, category, period, tt, most_recent, week_number, month_number) FROM STDIN;"''',
                retries = 0)

    sync_baseline = BashOperator(
                task_id = 'sync_baseline',
                bash_command = '''set -o pipefail; psql $heroku_rds -v "ON_ERROR_STOP=1" -c "\COPY (SELECT street, street_suffix, direction, from_intersection, to_intersection, day_type, period, period_range, tt FROM data_analysis.richmond_dash_baseline) TO STDOUT WITH (HEADER FALSE);" | psql $heroku_string -v "ON_ERROR_STOP=1" -c "TRUNCATE data_analysis.richmond_dash_baseline; COPY data_analysis.richmond_dash_baseline(street, street_suffix, direction, from_intersection, to_intersection, day_type, period, period_range, tt) FROM STDIN;"''',
                retries = 0)
    sync_weeks = BashOperator(
                task_id = 'sync_weeks',
                bash_command = '''set -o pipefail; psql $heroku_rds -v "ON_ERROR_STOP=1" -c "\COPY (SELECT week, week_number FROM data_analysis.richmond_closure_weeks) TO STDOUT;" | psql $heroku_string -v "ON_ERROR_STOP=1" -c "TRUNCATE data_analysis.richmond_closure_weeks; COPY data_analysis.richmond_closure_weeks(week, week_number) FROM STDIN;"''',
                retries = 0)
    sync_months = BashOperator(
                task_id = 'sync_months',
                bash_command = '''set -o pipefail; psql $heroku_rds -v "ON_ERROR_STOP=1" -c "\COPY (SELECT month, month_number FROM data_analysis.richmond_closure_months) TO STDOUT;" | psql $heroku_string -v "ON_ERROR_STOP=1" -c "TRUNCATE data_analysis.richmond_closure_months; COPY data_analysis.richmond_closure_months(month, month_number) FROM STDIN;"''',
                retries = 0)

    restart_app >> [sync_daily, sync_baseline, sync_weeks, sync_months]