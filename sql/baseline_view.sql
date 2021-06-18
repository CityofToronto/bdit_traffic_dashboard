-- a view in our database that aggregates our baseline data

CREATE MATERIALIZED VIEW data_analysis.gardiner_dash_baseline_mat as 
with temp as (SELECT gardiner_blip_daily.street,
        CASE
            WHEN gardiner_blip_daily.direction::text = 'NB'::text THEN 'Northbound'::text
            WHEN gardiner_blip_daily.direction::text = 'EB'::text THEN 'Eastbound'::text
            WHEN gardiner_blip_daily.direction::text = 'WB'::text THEN 'Westbound'::text
            WHEN gardiner_blip_daily.direction::text = 'SB'::text THEN 'Southbound'::text
            ELSE NULL::text
        END AS direction,
    gardiner_blip_daily.start_crossstreet AS from_intersection,
    gardiner_blip_daily.end_crossstreet AS to_intersection,
    gardiner_blip_daily.day_type,
    gardiner_blip_daily.period,
    gardiner_periods.time_range AS period_range,
    round(avg(gardiner_blip_daily.tt) / 60::numeric, 1) AS tt,
	sum(round(avg(gardiner_blip_daily.tt) / 60::numeric, 1)) over (partition by street, direction, day_type, period, time_range) as sum_tt 
   FROM data_analysis.gardiner_blip_daily
     JOIN data_analysis.gardiner_periods USING (period, day_type)
  WHERE gardiner_blip_daily.study_period = 'Baseline'::text
  GROUP BY gardiner_blip_daily.street, gardiner_blip_daily.direction, gardiner_blip_daily.start_crossstreet, gardiner_blip_daily.end_crossstreet, gardiner_blip_daily.day_type, gardiner_blip_daily.period, gardiner_periods.time_range
)
select street, direction, from_intersection, to_intersection, day_type, period, period_range, tt from temp
union all
select street, direction, 'summary' as from_intersection, 'summary' as to_intersection, day_type, period, period_range, sum_tt from (
	select distinct street, direction, day_type, period, period_range, sum_tt from temp) a
order by street, direction
ALTER TABLE data_analysis.gardiner_dash_baseline_mat
    OWNER TO heroku_bot;

GRANT SELECT ON TABLE data_analysis.gardiner_dash_baseline_mat TO bdit_humans;
GRANT ALL ON TABLE data_analysis.gardiner_dash_baseline_mat TO heroku_bot;		