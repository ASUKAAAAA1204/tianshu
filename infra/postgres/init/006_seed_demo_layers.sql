INSERT INTO layers(name, layer_type, level, geometry_json, geometry, source)
VALUES
('梁平机场净空保护区', 'restricted', 'hard', '{"type":"Polygon","coordinates":[[[107.775,30.668],[107.805,30.668],[107.805,30.692],[107.775,30.692],[107.775,30.668]]]}', ST_SetSRID(ST_GeomFromText('POLYGON((107.775 30.668,107.805 30.668,107.805 30.692,107.775 30.692,107.775 30.668))'),4326), 'demo'),
('城区低空运行区', 'operable', 'soft', '{"type":"Polygon","coordinates":[[[107.740,30.630],[107.785,30.630],[107.785,30.660],[107.740,30.660],[107.740,30.630]]]}', ST_SetSRID(ST_GeomFromText('POLYGON((107.740 30.630,107.785 30.630,107.785 30.660,107.740 30.660,107.740 30.630))'),4326), 'demo'),
('临时限制区 A-01', 'restricted', 'temporary', '{"type":"Polygon","coordinates":[[[107.815,30.635],[107.837,30.635],[107.837,30.653],[107.815,30.653],[107.815,30.635]]]}', ST_SetSRID(ST_GeomFromText('POLYGON((107.815 30.635,107.837 30.635,107.837 30.653,107.815 30.653,107.815 30.635))'),4326), 'demo')
ON CONFLICT DO NOTHING;

INSERT INTO vehicles(id, name, model, longitude, latitude, altitude, battery, status)
VALUES
('UAV-LP-001', '巡检一号', '多旋翼 M300', 107.758, 30.646, 120, 86, 'online'),
('UAV-LP-002', '测绘二号', '垂直起降 V2', 107.739, 30.713, 220, 64, 'online'),
('UAV-LP-003', '平台演示机', '多旋翼 S20', 107.825, 30.620, 0, 97, 'standby')
ON CONFLICT DO NOTHING;

INSERT INTO rules(code, name, level, level_label)
VALUES
('R-001', '硬限制区禁止穿越', 'hard', '硬约束'),
('R-002', '任务高度上限 1200m', 'hard', '硬约束'),
('R-003', '临时限制区需人工确认', 'soft', '软约束'),
('R-004', '航线冲突提前 120 秒预警', 'alert', '预警')
ON CONFLICT DO NOTHING;

INSERT INTO missions(id, name, vehicle_id, route_name, start_lng, start_lat, end_lng, end_lat, planned_altitude, status, status_label)
VALUES
('MS-20260915-001', '城区基础巡查航线', 'UAV-LP-001', 'R-城区-01', 107.745, 30.638, 107.780, 30.657, 120, 'running', '运行中'),
('MS-20260915-002', '北部空域测绘演示', 'UAV-LP-002', 'R-北部-03', 107.725, 30.704, 107.755, 30.725, 220, 'warning', '需处置'),
('MS-20260915-003', '平台联调测试任务', 'UAV-LP-003', 'R-测试-01', 107.820, 30.615, 107.805, 30.650, 100, 'planned', '已计划')
ON CONFLICT DO NOTHING;
