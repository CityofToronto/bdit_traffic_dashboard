-- a view in our database that aggregates our daily data

CREATE OR REPLACE VIEW data_analysis.richmond_dash_daily AS
 WITH seg_num AS (
         SELECT watermain_blip_daily.street,
            watermain_blip_daily.direction,
            count(DISTINCT watermain_blip_daily.start_crossstreet) AS number_seg
           FROM data_analysis.watermain_blip_daily
          GROUP BY watermain_blip_daily.street, watermain_blip_daily.direction
        ), tempa AS (
         SELECT watermain_blip_daily.street,
            watermain_blip_daily.direction,
            watermain_blip_daily.study_period AS category,
            watermain_blip_daily.dt,
            watermain_blip_daily.day_type,
            watermain_blip_daily.period,
            sum(watermain_blip_daily.tt) / 60::numeric AS tt,
            count(1) AS count,
            a.number_seg
           FROM data_analysis.watermain_blip_daily
             JOIN seg_num a USING (street, direction)
          GROUP BY watermain_blip_daily.street, watermain_blip_daily.direction, watermain_blip_daily.study_period, watermain_blip_daily.dt, watermain_blip_daily.day_type, watermain_blip_daily.period, a.number_seg
         HAVING count(1) = a.number_seg
        )
 SELECT tempa.street,
    tempa.direction,
    tempa.dt AS date,
    tempa.day_type,
    tempa.category,
    tempa.period,
    round(tempa.tt, 1) AS tt,
        CASE
            WHEN tempa.dt = first_value(tempa.dt) OVER (PARTITION BY tempa.direction, tempa.day_type, tempa.period ORDER BY tempa.dt DESC) THEN 1
            ELSE 0
        END AS most_recent,
    weeks.week_number,
    months.month_number
   FROM tempa
     LEFT JOIN data_analysis.richmond_closure_weeks weeks ON tempa.dt >= weeks.week AND tempa.dt < (weeks.week + '7 days'::interval)
     LEFT JOIN data_analysis.richmond_closure_months months ON tempa.dt >= months.month AND tempa.dt < (months.month + '1 mon'::interval);