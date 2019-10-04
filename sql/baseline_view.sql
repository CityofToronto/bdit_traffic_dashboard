-- a view in our database that aggregates our baseline data
CREATE OR REPLACE VIEW data_analysis.richmond_dash_baseline AS
 WITH seg_num AS (
         SELECT watermain_blip_daily.street,
            watermain_blip_daily.direction,
            count(DISTINCT watermain_blip_daily.start_crossstreet) AS number_seg
           FROM data_analysis.watermain_blip_daily
          GROUP BY watermain_blip_daily.street, watermain_blip_daily.direction
        ), tempa AS (
         SELECT a.street, from_intersection, to_intersection, street_suffix,
                CASE
                    WHEN a.direction = 'NB'::text THEN 'Northbound'::text
                    WHEN a.direction = 'EB'::text THEN 'Eastbound'::text
                    WHEN a.direction = 'WB'::text THEN 'Westbound'::text
                    WHEN a.direction = 'SB'::text THEN 'Southbound'::text
                    ELSE NULL::text
                END AS direction,
            a.study_period,
            a.day_type,
            a.dt,
            a.period,
            richmond_periods.time_range AS period_range,
            sum(a.tt) AS tt
           FROM data_analysis.watermain_blip_daily a
             JOIN data_analysis.richmond_segment_lookup using (street, direction)
             JOIN data_analysis.richmond_periods USING (period, day_type)
             JOIN seg_num b USING (street, direction)
          WHERE a.study_period = 'Baseline'::text
          GROUP BY a.street, a.direction, a.study_period, a.day_type, a.period, a.dt, richmond_periods.time_range, b.number_seg, from_intersection, to_intersection, street_suffix
         HAVING count(1) = b.number_seg
        )
 SELECT tempa.street,street_suffix, tempa.direction,from_intersection,to_intersection,
    tempa.day_type,
    tempa.period,
    tempa.period_range,
    round(avg(tempa.tt) / 60::numeric, 1) AS tt
   FROM tempa
  GROUP BY tempa.street, tempa.direction, tempa.from_intersection, tempa.to_intersection, tempa.day_type, tempa.period, tempa.period_range, street_suffix
  order by street