-- a view in our database that aggregates our daily data

CREATE MATERIALIZED VIEW data_analysis.gardiner_dash_daily_mat
TABLESPACE pg_default
AS
 SELECT gardiner_blip_daily.street,
    gardiner_blip_daily.direction,
    gardiner_blip_daily.start_crossstreet,
    gardiner_blip_daily.end_crossstreet,
    gardiner_blip_daily.dt,
    gardiner_blip_daily.day_type,
    gardiner_blip_daily.study_period AS category,
    gardiner_blip_daily.period,
    gardiner_blip_daily.tt
   FROM data_analysis.gardiner_blip_daily
UNION ALL
 SELECT a.street,
    a.direction,
    'summary'::character varying AS start_crossstreet,
    'summary'::character varying AS end_crossstreet,
    a.dt,
    a.day_type,
    a.study_period AS category,
    a.period,
    sum(a.tt) * (b.total_length::numeric / sum(b.length)::numeric) AS tt
   FROM data_analysis.gardiner_blip_daily a
     JOIN data_analysis.gardiner_segments b ON a.street::text = b.street::text AND a.start_crossstreet::text = b.start_cross::text AND a.end_crossstreet::text = b.end_cross::text
  GROUP BY a.street, a.direction, a.dt, a.day_type, a.study_period, a.period, b.total_length
WITH DATA;

ALTER TABLE data_analysis.gardiner_dash_daily_mat
    OWNER TO heroku_bot;

GRANT SELECT ON TABLE data_analysis.gardiner_dash_daily_mat TO bdit_humans;
GRANT ALL ON TABLE data_analysis.gardiner_dash_daily_mat TO heroku_bot;