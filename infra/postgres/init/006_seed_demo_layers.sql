INSERT INTO layers(name, layer_type, level, geometry_json, geometry, source)
VALUES
('梁平机场净空保护区', 'restricted', 'hard', '{"type":"Polygon","coordinates":[[[107.775,30.668],[107.805,30.668],[107.805,30.692],[107.775,30.692],[107.775,30.668]]]}', ST_SetSRID(ST_GeomFromText('POLYGON((107.775 30.668,107.805 30.668,107.805 30.692,107.775 30.692,107.775 30.668))'),4326), 'demo'),
('城区低空运行区', 'operable', 'soft', '{"type":"Polygon","coordinates":[[[107.740,30.630],[107.785,30.630],[107.785,30.660],[107.740,30.660],[107.740,30.630]]]}', ST_SetSRID(ST_GeomFromText('POLYGON((107.740 30.630,107.785 30.630,107.785 30.660,107.740 30.660,107.740 30.630))'),4326), 'demo'),
('临时限制区 A-01', 'restricted', 'temporary', '{"type":"Polygon","coordinates":[[[107.815,30.635],[107.837,30.635],[107.837,30.653],[107.815,30.653],[107.815,30.635]]]}', ST_SetSRID(ST_GeomFromText('POLYGON((107.815 30.635,107.837 30.635,107.837 30.653,107.815 30.653,107.815 30.635))'),4326), 'demo')
ON CONFLICT DO NOTHING;
