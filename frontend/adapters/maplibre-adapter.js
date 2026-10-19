(() => {
  const emptyCollection = () => ({ type: "FeatureCollection", features: [] });
  const FACILITY_MIN_ZOOM = 12;
  const REGIONAL_POINT_MIN_ZOOM = 10;
  const collection = (features) => ({ type: "FeatureCollection", features });
  const validPoint = (point) => Array.isArray(point) && point.length >= 2 && Number.isFinite(Number(point[0])) && Number.isFinite(Number(point[1]));
  const safeJson = (value) => { try { return typeof value === "string" ? JSON.parse(value) : value; } catch { return null; } };
  const routeFeature = (points, properties) => points?.filter(validPoint).length >= 2 ? ({ type: "Feature", geometry: { type: "LineString", coordinates: points.filter(validPoint) }, properties }) : null;
  const pointFeature = (coordinates, properties) => validPoint(coordinates) ? ({ type: "Feature", geometry: { type: "Point", coordinates: [Number(coordinates[0]), Number(coordinates[1])] }, properties }) : null;
  const objectKey = (feature) => { const properties = feature?.properties || {}; return String(properties.id || properties.point_id || properties.name || ""); };

  const style = {
    version: 8,
    sources: {},
    layers: [
      { id: "lp-background", type: "background", paint: { "background-color": "#0b1726" } },
    ],
  };

  function selectedMission(data, selectedMissionId) {
    return (data.missions || []).find((item) => item.id === selectedMissionId)
      || (data.missions || []).find((item) => item.status === "running")
      || (data.missions || [])[0]
      || null;
  }

  function vehicleForMission(data, mission) {
    return mission ? (data.vehicles || []).find((item) => item.id === mission.vehicle_id) || null : null;
  }

  function missionPoints(data, mission, selectedRoute) {
    const vehicle = vehicleForMission(data, mission);
    const fallback = [[Number(mission?.start_lng), Number(mission?.start_lat)], vehicle ? [Number(vehicle.longitude), Number(vehicle.latitude)] : null, [Number(mission?.end_lng), Number(mission?.end_lat)]].filter(validPoint);
    const selected = (selectedRoute?.points || []).filter(validPoint);
    return selected.length >= 2 ? selected : fallback;
  }

  function smoothRoute(points, steps = 8) {
    if (points.length < 3) return points;
    const output = [];
    for (let i = 0; i < points.length - 1; i += 1) {
      const p0 = points[Math.max(0, i - 1)]; const p1 = points[i]; const p2 = points[i + 1]; const p3 = points[Math.min(points.length - 1, i + 2)];
      for (let step = 0; step < steps; step += 1) {
        const t = step / steps; const t2 = t * t; const t3 = t2 * t;
        output.push([0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3), 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)]);
      }
    }
    output.push(points[points.length - 1]);
    return output;
  }

  function circleFromPolygon(feature) {
    const ring = feature.geometry?.type === "Polygon" ? feature.geometry.coordinates?.[0] : feature.geometry?.type === "MultiPolygon" ? feature.geometry.coordinates?.[0]?.[0] : null;
    if (!ring || ring.length < 4) return feature;
    const openRing = ring.slice(0, -1); const center = [openRing.reduce((sum, point) => sum + point[0], 0) / openRing.length, openRing.reduce((sum, point) => sum + point[1], 0) / openRing.length];
    const cosLat = Math.cos(center[1] * Math.PI / 180); const radius = Math.max(...openRing.map((point) => Math.hypot((point[0] - center[0]) * 111320 * cosLat, (point[1] - center[1]) * 110540)));
    const coordinates = Array.from({ length: 33 }, (_, index) => { const angle = (index / 32) * Math.PI * 2; return [center[0] + (Math.cos(angle) * radius) / (111320 * cosLat), center[1] + (Math.sin(angle) * radius) / 110540]; });
    return { ...feature, geometry: { type: "Polygon", coordinates: [coordinates] }, properties: { ...feature.properties, display_shape: "derived_circle" } };
  }

  function nearbyToRoute(feature, points, limitMeters = 2500) {
    if (feature.geometry?.type !== "Point" || points.length < 2) return false;
    const [lng, lat] = feature.geometry.coordinates; const cosLat = Math.cos(lat * Math.PI / 180); const xy = (point) => [(point[0] - lng) * 111320 * cosLat, (point[1] - lat) * 110540];
    for (let i = 1; i < points.length; i += 1) {
      const a = xy(points[i - 1]); const b = xy(points[i]); const dx = b[0] - a[0]; const dy = b[1] - a[1]; const length = dx * dx + dy * dy; const t = length ? Math.max(0, Math.min(1, -(a[0] * dx + a[1] * dy) / length)) : 0;
      if (Math.hypot(a[0] + t * dx, a[1] + t * dy) <= limitMeters) return true;
    }
    return false;
  }

  function featureBounds(feature) {
    const points = [];
    const walk = (value) => { if (!Array.isArray(value)) return; if (value.length >= 2 && value.every((item) => typeof item === "number")) points.push(value); else value.forEach(walk); };
    walk(feature?.geometry?.coordinates || []);
    if (!points.length) return null;
    return { minLng: Math.min(...points.map((p) => p[0])), maxLng: Math.max(...points.map((p) => p[0])), minLat: Math.min(...points.map((p) => p[1])), maxLat: Math.max(...points.map((p) => p[1])) };
  }

  function boundsForFeatures(features) {
    const points = (features || []).flatMap((feature) => {
      const bounds = featureBounds(feature);
      return bounds ? [[bounds.minLng, bounds.minLat], [bounds.maxLng, bounds.maxLat]] : [];
    }).filter(validPoint);
    if (!points.length) return [[107.70, 30.62], [107.82, 30.74]];
    return [[Math.min(...points.map((p) => p[0])), Math.min(...points.map((p) => p[1]))], [Math.max(...points.map((p) => p[0])), Math.max(...points.map((p) => p[1]))]];
  }

  function statusFor(vehicle) {
    if (Number(vehicle?.battery) <= 20) return { key: "low-battery", label: "低电量", color: "#ef9b4a" };
    if (vehicle?.link_status === "offline" || vehicle?.status === "lost") return { key: "lost", label: "失联", color: "#e46b72" };
    if (vehicle?.status === "warning") return { key: "confirm", label: "需确认", color: "#efc15b" };
    if (vehicle?.status === "completed") return { key: "completed", label: "已完成", color: "#8797aa" };
    if (["online", "running"].includes(vehicle?.status)) return { key: "running", label: "运行中", color: "#45d5b2" };
    return { key: "standby", label: "待命", color: "#8da8c5" };
  }

  class MapLibreAdapter {
    constructor({ fallbackController }) {
      this.kind = "maplibre";
      this.state = { zoom: 9.2, panX: 0, panY: 0, showDem: false, selectedWaypointIds: [], filters: { task: true, airspace: true, facilities: true, risks: true, altitude: "all" } };
      this.fallbackController = fallbackController;
      this.map = null;
      this.context = null;
      this.loading = null;
      this.failed = false;
      this.didFitMission = false;
      this.userMoved = false;
      this.lastMissionId = null;
      this.resizeObserver = null;
      this.referenceGeographyLoaded = false;
      this.referenceGeographyLoading = null;
      this.styleMode = "local-reference";
      this.tileStyleState = "not-configured";
      this.tileProvider = "OpenMapTiles";
    }

    async resolveMapStyle() {
      try {
        const configResponse = await fetch("/api/map/config", { cache: "no-store" });
        if (!configResponse.ok) { this.tileStyleState = "config-unavailable"; return style; }
        const config = await configResponse.json();
        if (!config.style_url) { this.tileStyleState = "not-configured"; return style; }
        const styleUrl = new URL(config.style_url, window.location.href);
        if (![window.location.origin, "http://127.0.0.1:8090", "http://localhost:8090", "https://tiles.openfreemap.org"].includes(styleUrl.origin)) { this.tileStyleState = "invalid-config"; return style; }
        const styleResponse = await fetch(styleUrl.href, { cache: "no-store" });
        if (!styleResponse.ok) { this.tileStyleState = "unavailable"; return style; }
        const styleDocument = await styleResponse.json();
        if (styleDocument?.version !== 8 || !Array.isArray(styleDocument.layers)) { this.tileStyleState = "invalid-style"; return style; }
        this.styleMode = "openmaptiles";
        this.tileProvider = config.provider || (styleUrl.hostname === "tiles.openfreemap.org" ? "OpenFreeMap" : "OpenMapTiles");
        this.tileStyleState = "ready";
        return styleUrl.href;
      } catch {
        this.tileStyleState = "unavailable";
        return style;
      }
    }

    async ensureMap() {
      if (this.map) return this.map;
      if (this.loading) return this.loading;
      this.loading = Promise.resolve().then(async () => {
        const module = window.maplibregl;
        if (!module?.Map) throw new Error("MAPLIBRE_VENDOR_UNAVAILABLE");
        const target = document.querySelector("#mapCanvas");
        if (!target) throw new Error("MAP_CONTAINER_NOT_FOUND");
        const mapStyle = await this.resolveMapStyle();
        target.replaceChildren();
        const viewport = document.createElement("div"); viewport.id = "maplibreViewport"; viewport.className = "maplibre-viewport"; viewport.style.cssText = "position:absolute;inset:0;width:100%;height:100%;"; viewport.setAttribute("aria-hidden", "true");
        const markers = document.createElement("div"); markers.id = "maplibreMarkers"; markers.className = "maplibre-markers";
        const status = document.createElement("span"); status.id = "mapModeStatus"; status.className = "map-mode-status"; status.textContent = "MapLibre · loading";
        const north = document.createElement("div"); north.className = "map-label label-north"; north.textContent = "N · WGS84 参考";
        const south = document.createElement("div"); south.className = "map-label label-south"; south.textContent = "公开参考 / 合成演示数据 · 非授权生产数据";
        const attribution = document.createElement("a"); attribution.className = "map-attribution"; attribution.href = "https://www.openstreetmap.org/copyright"; attribution.target = "_blank"; attribution.rel = "noopener noreferrer"; attribution.textContent = "© OpenStreetMap contributors · OpenFreeMap / OpenMapTiles"; attribution.setAttribute("aria-label", "OpenStreetMap、OpenFreeMap和OpenMapTiles来源与许可信息");
        target.append(viewport, markers, north, south, attribution, status);
        this.map = new module.Map({ container: "maplibreViewport", style: mapStyle, center: [107.75, 30.70], zoom: this.state.zoom, minZoom: 8, maxZoom: 18, attributionControl: false, antialias: true, dragRotate: false, pitchWithRotate: false, scrollZoom: true, dragPan: true, doubleClickZoom: true });
        if (window.ResizeObserver) {
          this.resizeObserver = new ResizeObserver(() => this.map?.resize());
          this.resizeObserver.observe(target);
        }
        this.map.on("load", () => { try { this.addLayers(); if (this.styleMode === "local-reference") this.loadReferenceGeography(); this.syncSources(true); } catch (error) { this.fail(error); } });
        this.map.on("error", (event) => {
          const message = String(event?.error?.message || "");
          if (message.includes("lp-geography")) this.setStatus("local reference data unavailable");
        });
        // Some WebGL implementations emit styledata before load; retry once after
        // initialization so a valid data context cannot leave an empty canvas.
        window.setTimeout(() => {
          if (!this.map || this.failed || !this.context) return;
          try { this.addLayers(); this.syncSources(true); } catch (error) { this.fail(error); }
        }, 900);
        this.map.on("movestart", () => { this.userMoved = true; });
        this.map.on("move", () => { this.state.zoom = this.map.getZoom(); if (this.context) { const next = this.buildData(); this.renderRouteOverlay(next); this.layoutMarkers(); } });
        this.map.on("moveend", () => { if (this.context && !this.failed) this.syncSources(); });
        this.map.on("mousemove", (event) => { const targetCoords = document.querySelector("#mapCoords"); if (targetCoords) targetCoords.textContent = `坐标 ${Number(event.lngLat.lng).toFixed(5)}, ${Number(event.lngLat.lat).toFixed(5)}`; });
        this.map.on("click", "lp-aircraft", (event) => { const id = event.features?.[0]?.properties?.id; if (id) this.context?.onVehicleClick?.(id); });
        ["lp-airspace-fill", "lp-facilities", "lp-risks"].forEach((layer) => this.map.on("click", layer, (event) => { const feature = event.features?.[0]; if (feature) this.context?.onSpatialClick?.(feature); }));
        return this.map;
      }).catch((error) => {
        this.fail(error);
        if (this.fallbackController && this.context) return this.fallbackController.render(this.context);
        throw error;
      });
      return this.loading;
    }

    setStatus(value) { const node = document.querySelector("#mapModeStatus"); if (node) node.textContent = `MapLibre · ${value}`; }
    fail(error) { console.error("MapLibre adapter failed", error); this.failed = true; this.setStatus("fallback"); if (this.fallbackController && this.context) this.fallbackController.render(this.context); }

    buildData() {
      const data = this.context?.data || {};
      const mission = selectedMission(data, this.context?.selectedMissionId);
      const liveVehicle = vehicleForMission(data, mission);
      const replay = this.context?.replayTrack?.missionId === mission?.id ? this.context.replayTrack : null;
      const replaySamples = replay?.samples || [];
      const replayIndex = Math.max(0, Math.min(replaySamples.length - 1, Number(replay?.index) || 0));
      const replaySample = replaySamples[replayIndex];
      const vehicle = replaySample && liveVehicle ? { ...liveVehicle, longitude: Number(replaySample.longitude), latitude: Number(replaySample.latitude), altitude: replaySample.altitude ?? liveVehicle.altitude, battery: replaySample.battery ?? liveVehicle.battery, status: replaySample.status ?? liveVehicle.status } : liveVehicle;
      const originalRoute = missionPoints(data, mission, this.context?.selectedRoute);
      const spatial = (data.map_features?.features || data.spatial_assets?.features || []).filter((feature) => feature.visible !== false && feature.properties?.visible_default !== false);
      const candidates = spatial.filter((feature) => ["facility", "facility_point", "route_reference_point"].includes(feature.properties?.asset_type) && nearbyToRoute(feature, originalRoute));
      const candidateById = new Map(candidates.map((feature) => [objectKey(feature), feature]));
      this.state.selectedWaypointIds = this.state.selectedWaypointIds.filter((id) => candidateById.has(id));
      const chosenWaypoints = this.state.selectedWaypointIds.map((id) => candidateById.get(id)).filter(Boolean).map((feature) => feature.geometry.coordinates.map(Number));
      const primary = chosenWaypoints.length >= 1 && originalRoute.length >= 2 ? smoothRoute([originalRoute[0], ...chosenWaypoints, originalRoute[originalRoute.length - 1]]) : originalRoute;
      const actual = replaySamples.length ? replaySamples.slice(0, replayIndex + 1).filter((sample) => validPoint([sample.longitude, sample.latitude])).map((sample) => [Number(sample.longitude), Number(sample.latitude)]) : vehicle && validPoint([vehicle.longitude, vehicle.latitude]) ? [primary[0], [Number(vehicle.longitude), Number(vehicle.latitude)]] : [];
      const relevant = spatial.filter((feature) => {
        const type = feature.properties?.asset_type;
        if (type === "elevation_sample") return this.state.showDem;
        if (type === "route_reference_point") return this.state.filters.facilities && this.map?.getZoom() > REGIONAL_POINT_MIN_ZOOM;
        if (type === "facility" || type === "facility_point") return this.state.filters.facilities && this.map?.getZoom() > FACILITY_MIN_ZOOM && nearbyToRoute(feature, originalRoute);
        if (["obstacle", "hazard"].includes(type)) return this.state.filters.risks && this.map?.getZoom() > REGIONAL_POINT_MIN_ZOOM;
        return type === "restricted" && this.state.filters.airspace;
      });
      const selectedKey = this.context?.selectedMapObject?.type === "spatial" ? objectKey(this.context.selectedMapObject.feature) : "";
      const markSelected = (feature) => ({ ...feature, properties: { ...feature.properties, selected: (Boolean(selectedKey) && objectKey(feature) === selectedKey) || this.state.selectedWaypointIds.includes(objectKey(feature)), path_reference: this.state.selectedWaypointIds.includes(objectKey(feature)) } });
      const airspace = relevant.filter((feature) => feature.properties?.asset_type === "restricted" && ["Polygon", "MultiPolygon"].includes(feature.geometry?.type)).map((feature) => markSelected(circleFromPolygon(feature)));
      const facilities = relevant.filter((feature) => ["facility", "facility_point", "route_reference_point"].includes(feature.properties?.asset_type) && feature.geometry?.type === "Point").map(markSelected);
      const risks = relevant.filter((feature) => ["obstacle", "hazard"].includes(feature.properties?.asset_type)).map(markSelected);
      const dem = relevant.filter((feature) => feature.properties?.asset_type === "elevation_sample");
      const vehicles = (data.vehicles || []).filter((item) => item.id === vehicle?.id || item.id === this.context?.selectedVehicleId).map((item) => item.id === vehicle?.id ? vehicle : item).filter((item) => {
        const altitude = Number(item.altitude || 0); const layer = this.state.filters.altitude; if (layer === "all") return true; if (layer === "0-60") return altitude < 60; if (layer === "60-120") return altitude >= 60 && altitude < 120; if (layer === "120-300") return altitude >= 120 && altitude < 300; return altitude >= 300;
      }).map((item) => { const status = statusFor(item); return pointFeature([item.longitude, item.latitude], { id: item.id, name: item.name || item.id, status: status.key, status_label: status.label, altitude: item.altitude || 0, battery: item.battery ?? "--", selected: item.id === this.context?.selectedVehicleId }); }).filter(Boolean);
      const routeFeatures = this.state.filters.task ? [routeFeature(primary, { route_type: "primary", name: "主航线" }), routeFeature(actual, { route_type: "actual", name: "实际轨迹" })].filter(Boolean) : [];
      const hasRisk = mission?.status === "warning" || (data.alerts || []).some((item) => item.status === "open" && item.mission_id === mission?.id);
      if (hasRisk && primary.length >= 2) routeFeatures.push(routeFeature(primary.slice(-2), { route_type: "risk", name: "风险航段", action_required: "需人工处置" }));
      const focusFeatures = [...routeFeatures, ...vehicles];
      return { mission, vehicle, airspace: collection(airspace), facilities: collection(facilities), waypointCandidates: candidates, selectedWaypointIds: [...this.state.selectedWaypointIds], risks: collection([...risks, ...dem]), routes: collection(routeFeatures.filter(Boolean)), vehicles: collection(vehicles), bounds: boundsForFeatures(focusFeatures) };
    }

    addLayers() {
      if (!this.map) return;
      const addSource = (id, options = {}) => { if (!this.map.getSource(id)) this.map.addSource(id, { type: "geojson", data: emptyCollection(), ...options }); };
      addSource("lp-geography");
      ["lp-airspace", "lp-risks", "lp-routes", "lp-aircraft"].forEach((id) => addSource(id));
      addSource("lp-facilities", { cluster: true, clusterRadius: 36, clusterMaxZoom: 11 });
      if (this.styleMode === "local-reference" && !this.map.getLayer("lp-reference-roads")) {
        this.map.addLayer({ id: "lp-reference-landuse", type: "fill", source: "lp-geography", filter: ["==", ["get", "asset_type"], "landuse"], paint: { "fill-color": ["match", ["get", "class"], "forest", "#344d43", "grass", "#30463c", "meadow", "#35473a", "#293e3a"], "fill-opacity": 0.42 } });
        this.map.addLayer({ id: "lp-reference-water-fill", type: "fill", source: "lp-geography", filter: ["all", ["==", ["get", "asset_type"], "water"], ["==", ["geometry-type"], "Polygon"]], paint: { "fill-color": "#28516b", "fill-opacity": 0.76 } });
        this.map.addLayer({ id: "lp-reference-waterways", type: "line", source: "lp-geography", filter: ["all", ["==", ["get", "asset_type"], "water"], ["==", ["geometry-type"], "LineString"]], paint: { "line-color": "#4285a2", "line-width": ["interpolate", ["linear"], ["zoom"], 8, 0.7, 13, 2.2], "line-opacity": 0.88 } });
        this.map.addLayer({ id: "lp-reference-roads", type: "line", source: "lp-geography", filter: ["==", ["get", "asset_type"], "road"], paint: { "line-color": ["match", ["get", "class"], "motorway", "#b69462", "trunk", "#b69462", "primary", "#ae9a77", "secondary", "#8292a0", "tertiary", "#718292", "#5c6c7b"], "line-width": ["interpolate", ["linear"], ["zoom"], 8, ["match", ["get", "class"], "motorway", 1.2, "trunk", 1.1, "primary", 0.9, 0.55], 13, ["match", ["get", "class"], "motorway", 4, "trunk", 3.5, "primary", 3, "secondary", 2.2, 1.4]], "line-opacity": 0.94 } });
      }
      if (!this.map.getLayer("lp-airspace-fill")) {
        this.map.addLayer({ id: "lp-airspace-fill", type: "fill", source: "lp-airspace", paint: { "fill-color": ["case", ["boolean", ["get", "selected"], false], "#83b9aa", "#699e92"], "fill-opacity": ["case", ["boolean", ["get", "selected"], false], 0.13, 0.075] } });
        this.map.addLayer({ id: "lp-airspace-outline", type: "line", source: "lp-airspace", paint: { "line-color": "#8abdb1", "line-opacity": 0.72, "line-width": ["case", ["boolean", ["get", "selected"], false], 1.5, 0.9] } });
      }
      if (!this.map.getLayer("lp-facilities")) {
        this.map.addLayer({ id: "lp-facilities", type: "circle", source: "lp-facilities", filter: ["!", ["has", "point_count"]], paint: { "circle-radius": ["case", ["boolean", ["get", "selected"], false], 5, ["match", ["get", "asset_type"], "route_reference_point", 2.6, 3.2]], "circle-color": ["case", ["boolean", ["get", "selected"], false], "#fff0a5", ["match", ["get", "asset_type"], "route_reference_point", "#87b5cb", "#cfa459"]], "circle-stroke-color": ["match", ["get", "asset_type"], "route_reference_point", "#c7e1eb", "#f0d49a"], "circle-stroke-width": ["case", ["boolean", ["get", "selected"], false], 1.5, 0.8] } });
      }
      if (!this.map.getLayer("lp-risks")) this.map.addLayer({ id: "lp-risks", type: "circle", source: "lp-risks", filter: ["!=", ["get", "asset_type"], "elevation_sample"], paint: { "circle-radius": ["case", ["boolean", ["get", "selected"], false], 4.8, 3.2], "circle-color": ["case", ["boolean", ["get", "selected"], false], "#ffd184", ["match", ["get", "risk_level"], "high", "#d45c62", "medium", "#d8964f", "#b86f70"]], "circle-stroke-color": ["case", ["boolean", ["get", "selected"], false], "#ffffff", "#f3d3d1"], "circle-stroke-width": ["case", ["boolean", ["get", "selected"], false], 1.5, 0.8] } });
      if (!this.map.getLayer("lp-aircraft")) {
        this.map.addLayer({ id: "lp-aircraft", type: "circle", source: "lp-aircraft", paint: { "circle-radius": ["case", ["boolean", ["get", "selected"], false], 3.4, 2.4], "circle-color": ["match", ["get", "status"], "running", "#45d5b2", "confirm", "#efc15b", "lost", "#e46b72", "low-battery", "#ef9b4a", "#8797aa"], "circle-stroke-color": "#eaf1f5", "circle-stroke-width": 0.8 } });
      }
    }

    syncSources(force = false) {
      if (!this.map) return;
      if (!force && !this.map.isStyleLoaded() && !this.map.loaded()) {
        if (!this.retryTimer) this.retryTimer = window.setTimeout(() => { this.retryTimer = null; this.syncSources(); }, 250);
        return;
      }
      this.addLayers();
      const next = this.buildData();
      this.map.getSource("lp-airspace")?.setData(next.airspace);
      this.map.getSource("lp-facilities")?.setData(next.facilities);
      this.map.getSource("lp-risks")?.setData(next.risks);
      this.map.getSource("lp-routes")?.setData(next.routes);
      this.map.getSource("lp-aircraft")?.setData(next.vehicles);
      this.syncMarkers(next);
      this.renderRouteOverlay(next);
      this.renderWaypointControls(next);
      const localStyleNote = this.tileStyleState === "not-configured" ? "OpenMapTiles style not configured" : this.tileStyleState === "unavailable" ? "TileServer unavailable" : this.tileStyleState === "invalid-style" || this.tileStyleState === "invalid-config" ? "TileServer configuration invalid" : "TileServer configuration unavailable";
      this.setStatus(this.styleMode === "openmaptiles" ? `${this.tileProvider} · OpenMapTiles vector tiles · data synced` : this.referenceGeographyLoaded ? `local OSM reference · ${localStyleNote} · data synced` : "reference data loading · data synced");
      if (!this.userMoved || !this.didFitMission) { this.map.fitBounds(next.bounds, { padding: 48, maxZoom: 13, duration: 0 }); this.didFitMission = true; }
      const summary = document.querySelector("#mapObjectSummary");
      if (summary) { summary.replaceChildren(); const objects = []; if (next.mission) objects.push({ label: `任务 ${next.mission.id}`, action: () => document.querySelector(`[data-mission="${CSS.escape(next.mission.id)}"]`)?.click() }); objects.push({ label: `航线 ${next.routes.features.length} 条`, action: () => {} }); if (next.vehicle) objects.push({ label: `飞行器 ${next.vehicle.id}`, action: () => this.context?.onVehicleClick?.(next.vehicle.id) }); const selectedFeature = this.context?.selectedMapObject?.type === "spatial" ? this.context.selectedMapObject.feature : null; const details = [...(selectedFeature ? [selectedFeature] : []), ...(next.airspace.features || []), ...(next.facilities.features || []).filter((feature) => feature.properties?.asset_type !== "route_reference_point"), ...(next.risks.features || []).filter((feature) => !String(feature.properties?.point_id || "").startsWith("SYN-RISK-"))].filter((feature, index, all) => all.findIndex((item) => objectKey(item) === objectKey(feature)) === index).slice(0, 5); details.forEach((feature) => objects.push({ label: feature.properties?.name || feature.properties?.point_id || "空间对象", action: () => this.context?.onSpatialClick?.(feature) })); objects.forEach((item) => { const button = document.createElement("button"); button.type = "button"; button.textContent = item.label; button.addEventListener("click", item.action); summary.append(button); }); }
    }

    loadReferenceGeography() {
      if (!this.map || this.referenceGeographyLoaded || this.referenceGeographyLoading) return this.referenceGeographyLoading;
      this.referenceGeographyLoading = fetch("/data/liangping-osm-reference.geojson", { cache: "no-cache" })
        .then((response) => { if (!response.ok) throw new Error(`REFERENCE_GEOJSON_HTTP_${response.status}`); return response.json(); })
        .then((geojson) => {
          if (geojson?.type !== "FeatureCollection" || !Array.isArray(geojson.features) || !geojson.features.length) throw new Error("REFERENCE_GEOJSON_INVALID");
          this.map?.getSource("lp-geography")?.setData(geojson);
          this.referenceGeographyLoaded = true;
          this.referenceGeographyLoading = null;
          if (this.context) this.syncSources();
        })
        .catch((error) => { this.referenceGeographyLoading = null; this.setStatus("local reference data unavailable"); console.error("Local OSM reference data unavailable", error); });
      return this.referenceGeographyLoading;
    }


    syncMarkers(next) {
      const container = document.querySelector("#maplibreMarkers");
      if (!container || !this.map || !window.maplibregl?.Marker) return;
      this.markers?.forEach((item) => item.marker.remove()); this.markers = [];
      const add = (coordinates, title, detail, kind, click, priority, selected = false) => {
        if (!validPoint(coordinates)) return;
        const element = document.createElement("button"); element.type = "button"; element.className = `maplibre-marker ${kind}${selected ? " is-selected" : ""}`; element.title = `${title} · ${detail}`; element.setAttribute("aria-label", `${title}，${detail}`); element.dataset.mapLabel = `${title} · ${detail}`; element.dataset.labelPriority = String(priority);
        const glyph = document.createElement("span"); glyph.className = "marker-glyph"; glyph.setAttribute("aria-hidden", "true"); const leader = document.createElement("span"); leader.className = "maplibre-marker-leader"; leader.setAttribute("aria-hidden", "true"); element.append(glyph, leader); element.addEventListener("click", (event) => { event.stopPropagation(); click?.(); });
        const marker = new window.maplibregl.Marker({ element, anchor: "center" }).setLngLat(coordinates.map(Number)).addTo(this.map); this.markers.push({ marker, element, coordinates: coordinates.map(Number), priority });
      };
      const vehicle = next.vehicle;
      if (vehicle) { const status = statusFor(vehicle); add([vehicle.longitude, vehicle.latitude], vehicle.name || vehicle.id, `${vehicle.altitude || 0}m · ${status.label}`, `vehicle ${status.key}`, () => this.context?.onVehicleClick?.(vehicle.id), 0, vehicle.id === this.context?.selectedMapObject?.id); }
      const protectedCoordinates = [
        next.vehicle ? [next.vehicle.longitude, next.vehicle.latitude] : null,
        this.context?.selectedMapObject?.type === "spatial" && this.context.selectedMapObject.feature?.geometry?.type === "Point" ? this.context.selectedMapObject.feature.geometry.coordinates : null,
        next.risks.features?.find((feature) => feature.properties?.risk_level === "high" && feature.geometry?.type === "Point")?.geometry.coordinates,
      ].filter(validPoint).map((coordinates) => this.map.project(coordinates));
      this.map.querySourceFeatures("lp-facilities").filter((feature) => Number(feature.properties?.point_count) > 1).forEach((feature) => {
        const clusterPoint = this.map.project(feature.geometry.coordinates);
        if (protectedCoordinates.some((point) => Math.hypot(point.x - clusterPoint.x, point.y - clusterPoint.y) < 13)) return;
        const count = Number(feature.properties.point_count); const element = document.createElement("button"); element.type = "button"; element.className = "maplibre-marker cluster"; element.textContent = String(count); element.title = `${count} 处设施 · 点击放大`; element.setAttribute("aria-label", `设施聚合，共 ${count} 处，点击放大`);
        element.addEventListener("click", (event) => {
          event.stopPropagation();
          const source = this.map?.getSource("lp-facilities"); const clusterId = Number(feature.properties?.cluster_id);
          if (source?.getClusterExpansionZoom && Number.isFinite(clusterId)) source.getClusterExpansionZoom(clusterId, (error, zoom) => { if (!error) this.map?.easeTo({ center: feature.geometry.coordinates, zoom }); });
          else this.map?.easeTo({ center: feature.geometry.coordinates, zoom: Math.min(18, this.map.getZoom() + 2) });
        });
        const marker = new window.maplibregl.Marker({ element, anchor: "center" }).setLngLat(feature.geometry.coordinates).addTo(this.map); element.setAttribute("aria-label", `设施聚合，共 ${count} 处，点击放大`);
        this.markers.push({ marker, element, coordinates: feature.geometry.coordinates.map(Number), priority: 3 });
      });
      const chosen = this.context?.selectedMapObject?.type === "spatial" ? this.context.selectedMapObject.feature : null;
      const chosenProps = chosen?.properties || {};
      const chosenCoords = chosen?.geometry?.type === "Point" ? chosen.geometry.coordinates : null;
      if (validPoint(chosenCoords)) add(chosenCoords, chosenProps.name || chosenProps.point_id || "空间对象", this.objectDetail(chosenProps), ["obstacle", "hazard", "restricted"].includes(chosenProps.asset_type) ? "risk" : "facility", () => this.context?.onSpatialClick?.(chosen), 1, true);
      this.layoutMarkers();
    }

    renderWaypointControls(next) {
      const target = document.querySelector("#routeWaypointList");
      if (!target) return;
      target.replaceChildren();
      if (this.map?.getZoom() <= FACILITY_MIN_ZOOM) { const hint = document.createElement("span"); hint.className = "route-waypoint-empty"; hint.textContent = "地图缩放至 12 级以上后显示附近参考点"; target.append(hint); return; }
      if (!next.waypointCandidates.length) { const hint = document.createElement("span"); hint.className = "route-waypoint-empty"; hint.textContent = "当前任务附近没有可用参考点"; target.append(hint); return; }
      next.waypointCandidates.forEach((feature) => {
        const id = objectKey(feature); const selectedIndex = next.selectedWaypointIds.indexOf(id); const button = document.createElement("button"); button.type = "button"; button.dataset.waypointId = id; button.setAttribute("aria-pressed", String(selectedIndex >= 0));
        button.setAttribute("aria-label", `${selectedIndex >= 0 ? `取消第 ${selectedIndex + 1} 个` : "添加"}参考航点：${feature.properties?.name || id}`);
        button.textContent = `${selectedIndex >= 0 ? `${selectedIndex + 1} · ` : "+ "}${feature.properties?.name || id}`;
        button.addEventListener("click", () => {
          const currentIndex = this.state.selectedWaypointIds.indexOf(id);
          if (currentIndex >= 0) this.state.selectedWaypointIds.splice(currentIndex, 1); else this.state.selectedWaypointIds.push(id);
          this.userMoved = true; this.syncSources();
        });
        target.append(button);
      });
    }

    objectDetail(properties) {
      const risk = properties.risk_level ? `风险 ${properties.risk_level}` : "风险级别未提供";
      const height = Number.isFinite(Number(properties.height_m)) ? `高度 ${properties.height_m}m` : "高度未提供";
      return `${risk} · ${height}`;
    }

    layoutMarkers() {
      if (!this.map || !this.markers?.length) return;
      const rect = document.querySelector("#maplibreViewport")?.getBoundingClientRect(); if (!rect) return;
      for (const { marker, element, coordinates } of this.markers) {
        const point = this.map.project(coordinates);
        element.hidden = point.x < -12 || point.y < -12 || point.x > rect.width + 12 || point.y > rect.height + 12;
        marker.setOffset([0, 0]);
      }
    }

    renderRouteOverlay(next) {
      const viewport = document.querySelector("#maplibreViewport");
      if (!viewport || !this.map) return;
      let svg = document.querySelector("#maplibreRouteOverlay");
      if (!svg) { svg = document.createElementNS("http://www.w3.org/2000/svg", "svg"); svg.id = "maplibreRouteOverlay"; svg.setAttribute("aria-label", "任务航线叠加"); svg.style.cssText = "position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:2;overflow:visible"; viewport.appendChild(svg); }
      const rect = viewport.getBoundingClientRect(); svg.setAttribute("viewBox", `0 0 ${Math.max(1, rect.width)} ${Math.max(1, rect.height)}`); svg.replaceChildren();
      const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
      const arrow = document.createElementNS("http://www.w3.org/2000/svg", "marker"); arrow.id = "lp-route-arrow"; arrow.setAttribute("viewBox", "0 0 10 10"); arrow.setAttribute("refX", "8"); arrow.setAttribute("refY", "5"); arrow.setAttribute("markerWidth", "3.5"); arrow.setAttribute("markerHeight", "3.5"); arrow.setAttribute("orient", "auto");
      const arrowHead = document.createElementNS("http://www.w3.org/2000/svg", "path"); arrowHead.setAttribute("d", "M 0 0 L 10 5 L 0 10 z"); arrowHead.setAttribute("fill", "#e7f1f7"); arrow.appendChild(arrowHead); defs.appendChild(arrow); svg.appendChild(defs);
      const colors = { primary: "#44d7b5", actual: "#f0f4f9", risk: "#e56e73" };
      for (const feature of next.routes.features || []) {
        const points = (feature.geometry?.coordinates || []).map((point) => this.map.project([Number(point[0]), Number(point[1])])).map((point) => `${point.x},${point.y}`).join(" ");
        if (!points) continue;
        const type = feature.properties?.route_type; const zoomScale = Math.max(0.72, Math.min(1.35, 0.82 + (this.map.getZoom() - 8) * 0.08)); const baseWidth = type === "risk" ? 2.7 : type === "primary" ? 2 : 0.95; const line = document.createElementNS("http://www.w3.org/2000/svg", "polyline"); line.setAttribute("points", points); line.setAttribute("fill", "none"); line.setAttribute("stroke", colors[type] || "#44d7b5"); line.setAttribute("stroke-width", String(Number((baseWidth * zoomScale).toFixed(2)))); line.setAttribute("stroke-linecap", "round"); line.setAttribute("stroke-linejoin", "round"); line.setAttribute("class", `route-overlay-${type || "primary"}`); line.setAttribute("aria-label", type === "risk" ? "风险航段" : type === "actual" ? "实际轨迹" : "主航线"); line.setAttribute("marker-end", "url(#lp-route-arrow)"); const title = document.createElementNS("http://www.w3.org/2000/svg", "title"); title.textContent = type === "risk" ? "风险航段" : type === "actual" ? "实际轨迹" : "主航线"; line.appendChild(title); svg.appendChild(line);
      }
    }

    render(context) {
      if (context?.selectedMissionId !== this.lastMissionId) {
        this.lastMissionId = context?.selectedMissionId || null;
        this.userMoved = false;
        this.didFitMission = false;
      }
      this.context = context;
      this.setStatus("loading");
      if (this.failed) return this.fallbackController?.render(context);
      this.ensureMap().then(() => { this.map?.resize(); this.syncSources(); }).catch((error) => this.fail(error));
    }
    setZoom(value, context) { this.context = context; this.state.zoom = Math.max(0.8, Math.min(18, value)); this.map?.zoomTo(this.state.zoom, { duration: 120 }); this.render(context); }
    reset(context) { this.context = context; this.userMoved = false; this.didFitMission = false; this.map?.setPitch(0); this.render(context); }
    toggleDem(context) { this.context = context; this.state.showDem = !this.state.showDem; this.render(context); return this.state.showDem; }
    setFilters(filters, context) { this.context = context; this.state.filters = { ...this.state.filters, ...filters }; this.render(context); }
  }

  window.lpMapLibreAdapterFactory = { create: (options) => new MapLibreAdapter(options) };
})();
