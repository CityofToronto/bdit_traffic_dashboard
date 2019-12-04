--SQL for generating month number and month for aggregation with the daily view
--used the dates from our data to make sure months are only created if there are data

CREATE OR REPLACE VIEW data_analysis.gardiner_weeks AS
 SELECT a.dt::date AS week,
    row_number() OVER () AS week_number
   FROM ( SELECT generate_series('2019-08-01 00:00:00'::timestamp without time zone, (now()-interval'1 day')::timestamp without time zone, '7 days'::interval) AS dt) a
  ORDER BY (row_number() OVER ()) DESC;

GRANT SELECT ON TABLE data_analysis.gardiner_weeks TO bdit_humans;
GRANT SELECT ON TABLE data_analysis.gardiner_weeks TO heroku_bot;

--SQL for generating week number and week for aggregation with the daily view
--used the dates from our data to make sure months are only created if there are data
CREATE OR REPLACE VIEW data_analysis.gardiner_months AS
SELECT a.dt::date AS month,
    row_number() OVER () AS month_number
   FROM ( SELECT generate_series('2019-08-01 00:00:00'::timestamp without time zone, (now()-interval'1 day')::timestamp without time zone, '1 mon'::interval) AS dt) a
  ORDER BY (row_number() OVER ()) DESC;		

GRANT SELECT ON TABLE data_analysis.gardiner_months TO bdit_humans;
GRANT SELECT ON TABLE data_analysis.gardiner_weeks TO heroku_bot;

