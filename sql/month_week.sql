--SQL for generating month number and month for aggregation with the daily view
--used the dates from our data to make sure months are only created if there are data

CREATE OR REPLACE VIEW data_analysis.gardiner_weeks AS
 SELECT a.week,
    row_number() OVER () AS week_number
   FROM ( SELECT DISTINCT ON ((date_trunc('week'::text, gardiner_dash_daily_mat.date::timestamp with time zone)::date)) date_trunc('week'::text, gardiner_dash_daily_mat.date::timestamp with time zone)::date AS week
           FROM data_analysis.gardiner_dash_daily_mat) a
  ORDER BY (row_number() OVER ()) DESC;

ALTER TABLE data_analysis.gardiner_weeks
    OWNER TO natalie;

GRANT SELECT ON TABLE data_analysis.gardiner_weeks TO bdit_humans;
GRANT ALL ON TABLE data_analysis.gardiner_weeks TO natalie;
GRANT SELECT ON TABLE data_analysis.gardiner_weeks TO heroku_bot;


--SQL for generating week number and week for aggregation with the daily view
--used the dates from our data to make sure months are only created if there are data
CREATE OR REPLACE VIEW data_analysis.gardiner_months AS
 SELECT a.month,
    row_number() OVER () AS month_number
   FROM ( SELECT DISTINCT ON ((date_trunc('month'::text, gardiner_dash_daily_mat.date::timestamp with time zone)::date)) date_trunc('month'::text, gardiner_dash_daily_mat.date::timestamp with time zone)::date AS month
           FROM data_analysis.gardiner_dash_daily_mat) a
  ORDER BY (row_number() OVER ()) DESC;

ALTER TABLE data_analysis.gardiner_months
    OWNER TO natalie;

GRANT SELECT ON TABLE data_analysis.gardiner_months TO bdit_humans;
GRANT ALL ON TABLE data_analysis.gardiner_months TO natalie;
GRANT SELECT ON TABLE data_analysis.gardiner_months TO heroku_bot;
