--SQL we used to read data from our rdb to dash in app.py

--DATA
SELECT case when d.street in ('Adelaide', 'Richmond', 'Queen', 'Front', 'Wellington') then d.street||' Street' 
                            when d.street in ('Eastern') then d.street||' Avenue'
                            when d.street = 'DVP' then 'Don Valley Parkway'
                            when d.street = 'Gardiner' then 'Gardiner Expressway'
                            when d.street = 'Lakeshore' then 'Lake Shore Boulevard' end
                            as street_short, case when direction = 'EB' then 'Eastbound'
                            when direction = 'WB' then 'Westbound'
                            when direction = 'NB' then 'Northbound'
                            when direction ='SB' then 'Southbound' 
                            else direction end as direction,  COALESCE(name2, d.start_crossstreet || ' to ' || d.end_crossstreet) as street1,
							COALESCE(name1, d.street || ': ' || d.start_crossstreet || ' and ' || d.end_crossstreet) as street, 
                            date, day_type, category, period, round(tt/60,2) as tt, most_recent, week_number, month_number 
                            FROM data_analysis.gardiner_dash_daily_mat d
							join data_analysis.gardiner_periods using (period, day_type)
                            left join (SELECT DISTINCT ON (d1.street, d1.start_cross, d1.end_cross) d1.street, d1.start_cross, d1.end_cross, 
                                        d1.street || ': ' || d1.start_cross || ' and ' || d1.end_cross as name1,
									   d1.start_cross || ' to ' || d1.end_cross as name2
                                        FROM data_analysis.gardiner_segments d1, data_analysis.gardiner_segments d2 
                                        WHERE d1.street = d2.street and d1.start_cross = d2.end_cross and d1.direction in ('NB', 'EB')
                                        ORDER BY d1.street) n	
                            ON n.street = d.street AND ( (n.start_cross = d.start_crossstreet AND n.end_cross = d.end_crossstreet) OR (n.start_cross = d.end_crossstreet AND n.end_cross = d.start_crossstreet)) 									
                            order by d.street, d.direction, start_crossstreet,time_range
--BASELINE
SELECT COALESCE(name1, d.street || ': ' || d.from_intersection || ' and ' || d.to_intersection) as street,
	                            COALESCE(name2, d.from_intersection || ' to ' || d.to_intersection) as street1, d.street as street_short,
                                d.direction, from_intersection, to_intersection,day_type, period, to_char(lower(period_range::TIMERANGE), 'FMHH AM')||' to '||to_char(upper(period_range::TIMERANGE), 'FMHH AM') as period_range , tt
                                FROM data_analysis.gardiner_dash_baseline_mat d 
								join data_analysis.gardiner_periods using (period, day_type)
                                left join (SELECT DISTINCT ON (d1.street, d1.start_cross, d1.end_cross) d1.street, d1.start_cross, d1.end_cross, 
                                                            d1.street || ': ' || d1.start_cross || ' and ' || d1.end_cross as name1,
										  					d1.start_cross || ' to ' || d1.end_cross as name2
                                                            FROM data_analysis.gardiner_segments d1, data_analysis.gardiner_segments d2 
                                                            WHERE d1.street = d2.street and d1.start_cross = d2.end_cross and d1.direction in ('NB', 'EB')
                                                            ORDER BY d1.street) n																																   
                                ON n.street = d.street AND ( (n.start_cross = d.from_intersection AND n.end_cross = d.to_intersection) 
                                OR (n.start_cross = d.to_intersection AND n.end_cross = d.from_intersection))
								order by time_range		
--HOLIDAY
SELECT dt FROM ref.holiday WHERE dt >= '2019-08-01'

--WEEK
SELECT * FROM data_analysis.gardiner_weeks

--MONTH
SELECT * FROM data_analysis.gardiner_months