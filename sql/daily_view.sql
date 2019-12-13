-- a view in our database that aggregates our daily data

CREATE OR REPLACE VIEW data_analysis.gardiner_dash_daily AS
 SELECT gardiner_blip_daily.street,
    gardiner_blip_daily.direction,
    gardiner_blip_daily.start_crossstreet,
    gardiner_blip_daily.end_crossstreet,
    gardiner_blip_daily.dt AS date,
    gardiner_blip_daily.day_type,
    gardiner_blip_daily.study_period AS category,
    gardiner_blip_daily.period,
    gardiner_blip_daily.tt,
        CASE
            WHEN gardiner_blip_daily.dt = first_value(gardiner_blip_daily.dt) OVER (PARTITION BY gardiner_blip_daily.direction, gardiner_blip_daily.day_type, gardiner_blip_daily.period ORDER BY gardiner_blip_daily.dt DESC) THEN 1
            ELSE 0
        END AS most_recent,
    weeks.week_number,
    months.month_number
   FROM data_analysis.gardiner_blip_daily
     LEFT JOIN data_analysis.gardiner_weeks weeks ON gardiner_blip_daily.dt >= weeks.week AND gardiner_blip_daily.dt < (weeks.week + '7 days'::interval)
     LEFT JOIN data_analysis.gardiner_months months ON gardiner_blip_daily.dt >= months.month AND gardiner_blip_daily.dt < (months.month + '1 mon'::interval);

ALTER TABLE data_analysis.gardiner_dash_daily
    OWNER TO natalie;

GRANT SELECT ON TABLE data_analysis.gardiner_dash_daily TO bdit_humans;
GRANT ALL ON TABLE data_analysis.gardiner_dash_daily TO natalie;
GRANT SELECT ON TABLE data_analysis.gardiner_dash_daily TO heroku_bot;