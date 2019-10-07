--SQL we used to read data from our rdb to dash in app.py

--DATA
SELECT street, case when direction = 'EB' then 'Eastbound'
                        when direction = 'WB' then 'Westbound'
                        when direction = 'NB' then 'Northbound'
                        when direction ='SB' then 'Southbound' end as direction, 
                        date, day_type, category, period, tt, most_recent, week_number, month_number from data_analysis.richmond_dash_daily

--BASELINE
SELECT street, street_suffix, direction, from_intersection, to_intersection, 
                             day_type, period, to_char(lower(period_range::TIMERANGE), 'FMHH AM')||' to '||to_char(upper(period_range::TIMERANGE), 'FMHH AM') as period_range , tt
                             FROM data_analysis.richmond_dash_baseline
                             order by richmond_dash_baseline.period_range

--HOLIDAY
SELECT dt FROM ref.holiday WHERE dt > '2019-07-02'

--WEEK
SELECT * FROM data_analysis.richmond_closure_weeks order by week_number desc

--MONTH
SELECT * FROM data_analysis.richmond_closure_months order by month_number desc