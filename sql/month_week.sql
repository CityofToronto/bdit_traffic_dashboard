--SQL for generating month number and month for aggregation with the daily view
--used the dates from our data to make sure months are only created if there are data

CREATE OR REPLACE VIEW data_analysis.richmond_closure_months AS
 SELECT a.month,
    row_number() OVER () AS month_number
   FROM ( SELECT DISTINCT ON ((date_trunc('month'::text, watermain_blip_30min.dt::timestamp with time zone)::date)) date_trunc('month'::text, watermain_blip_30min.dt::timestamp with time zone)::date AS month
           FROM data_analysis.watermain_blip_30min
          WHERE watermain_blip_30min.dt >= '2019-07-22'::date) a
  ORDER BY a.month;

--SQL for generating week number and week for aggregation with the daily view
--used the dates from our data to make sure months are only created if there are data
CREATE OR REPLACE VIEW data_analysis.richmond_closure_weeks AS
 SELECT a.week,
    row_number() OVER () AS week_number
   FROM ( SELECT DISTINCT ON ((date_trunc('week'::text, watermain_blip_30min.dt::timestamp with time zone)::date)) date_trunc('week'::text, watermain_blip_30min.dt::timestamp with time zone)::date AS week
           FROM data_analysis.watermain_blip_30min
          WHERE watermain_blip_30min.dt >= '2019-07-22'::date) a
  ORDER BY a.week;


