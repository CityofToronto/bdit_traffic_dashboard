-- a view in our database that aggregates our baseline data
CREATE OR REPLACE VIEW data_analysis.richmond_dash_baseline AS
 WITH seg_num AS (
         SELECT watermain_blip_daily.street,
            watermain_blip_daily.direction,
            count(DISTINCT watermain_blip_daily.start_crossstreet) AS number_seg
           FROM data_analysis.watermain_blip_daily
          GROUP BY watermain_blip_daily.street, watermain_blip_daily.direction
        ), tempa AS (
         SELECT a.street,
                CASE
                    WHEN (a.street = ANY (ARRAY['Adelaide'::text, 'Front'::text, 'King'::text, 'Adelaide'::text, 'Richmond'::text, 'Queen'::text, 'Dundas'::text])) AND a.direction = 'EB'::text THEN 'Bathurst'::text
                    WHEN (a.street = ANY (ARRAY['Bathurst'::text, 'Spadina'::text, 'University'::text])) AND a.direction = 'NB'::text THEN 'Front'::text
                    WHEN (a.street = ANY (ARRAY['Adelaide'::text, 'King'::text, 'Adelaide'::text, 'Richmond'::text, 'Queen'::text, 'Dundas'::text, 'Wellington'::text])) AND a.direction = 'WB'::text THEN 'Yonge'::text
                    WHEN a.street = 'Front'::text AND a.direction = 'WB'::text THEN 'Yonge'::text
                    WHEN (a.street = ANY (ARRAY['Bathurst'::text, 'Spadina'::text, 'University'::text])) AND a.direction = 'SB'::text THEN 'Dundas'::text
                    ELSE NULL::text
                END AS from_intersection,
                CASE
                    WHEN (a.street = ANY (ARRAY['Adelaide'::text, 'Front'::text, 'King'::text, 'Adelaide'::text, 'Richmond'::text, 'Queen'::text, 'Dundas'::text])) AND a.direction = 'EB'::text THEN 'Yonge'::text
                    WHEN (a.street = ANY (ARRAY['Bathurst'::text, 'Spadina'::text, 'University'::text])) AND a.direction = 'NB'::text THEN 'Dundas'::text
                    WHEN (a.street = ANY (ARRAY['Adelaide'::text, 'Front'::text, 'King'::text, 'Adelaide'::text, 'Richmond'::text, 'Queen'::text, 'Dundas'::text])) AND a.direction = 'WB'::text THEN 'Bathurst'::text
                    WHEN (a.street = ANY (ARRAY['Bathurst'::text, 'Spadina'::text, 'University'::text])) AND a.direction = 'SB'::text THEN 'Front'::text
                    WHEN a.street = 'Wellington'::text THEN 'Blue Jays'::text
                    ELSE NULL::text
                END AS to_intersection,
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
             JOIN data_analysis.richmond_periods USING (period, day_type)
             JOIN seg_num b USING (street, direction)
          WHERE a.study_period = 'Baseline'::text
          GROUP BY a.street, a.direction, a.study_period, a.day_type, a.period, a.dt, richmond_periods.time_range, b.number_seg
         HAVING count(1) = b.number_seg
        )
 SELECT tempa.street,
        CASE
            WHEN tempa.street = ANY (ARRAY['Front'::text, 'Richmond'::text, 'Queen'::text, 'Wellington'::text, 'Dundas'::text, 'Adelaide'::text, 'Bathurst'::text]) THEN 'Street'::text
            WHEN tempa.street = ANY (ARRAY['Spadina'::text, 'University'::text]) THEN 'Avenue'::text
            ELSE tempa.street
        END AS street_suffix,
    tempa.direction,
        CASE
            WHEN tempa.from_intersection = ANY (ARRAY['Yonge'::text, 'Bathurst'::text, 'Front'::text, 'Dundas'::text]) THEN tempa.from_intersection || ' St.'::text
            WHEN tempa.from_intersection = 'Blue Jays'::text THEN tempa.from_intersection || ' Way'::text
            ELSE NULL::text
        END AS from_intersection,
        CASE
            WHEN tempa.to_intersection = ANY (ARRAY['Yonge'::text, 'Bathurst'::text, 'Front'::text, 'Dundas'::text]) THEN tempa.to_intersection || ' St.'::text
            WHEN tempa.to_intersection = 'Blue Jays'::text THEN tempa.to_intersection || ' Way'::text
            ELSE NULL::text
        END AS to_intersection,
    tempa.day_type,
    tempa.period,
    tempa.period_range,
    round(avg(tempa.tt) / 60::numeric, 1) AS tt
   FROM tempa
  GROUP BY tempa.street, tempa.direction, tempa.from_intersection, tempa.to_intersection, tempa.day_type, tempa.period, tempa.period_range;