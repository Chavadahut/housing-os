import { useMemo, useRef, useState } from "react";
import {
  CircleMarker,
  GeoJSON,
  MapContainer,
  Marker,
  Popup,
  TileLayer,
  useMap,
  useMapEvents,
} from "react-leaflet";
import L from "leaflet";

import "./App.css";

const DEFAULT_CENTER = [32.7157, -117.1611];
const DEFAULT_ZOOM = 10;

const CORE_SECTIONS = [
  "zoning",
  "general_plan",
  "current_land_use",
  "fire_hazard",
  "flood_hazard",
  "road_access",
];

const SECONDARY_SECTIONS = [
  "terrain",
  "habitat",
  "wetlands",
  "utilities",
  "easements",
  "permit_history",
];

const SECTION_LABELS = {
  zoning: "Zoning",
  general_plan: "General Plan",
  current_land_use: "Land use",
  fire_hazard: "Fire hazard",
  flood_hazard: "Flood hazard",
  road_access: "Road access",
  terrain: "Terrain",
  habitat: "Habitat",
  wetlands: "Wetlands",
  utilities: "Utilities",
  easements: "Easements",
  permit_history: "Permit history",
};

function FitMapToProperty({ parcel }) {
  const map = useMap();

  useMemo(() => {
    const geometry = parcel?.map_geometry;
    const boundary = geometry?.simplified_parcel_boundary;

    if (!boundary) {
      return;
    }

    const layer = L.geoJSON(boundary);
    const bounds = layer.getBounds();

    if (bounds.isValid()) {
      map.fitBounds(bounds, {
        padding: [35, 35],
        maxZoom: 20,
      });
    }
  }, [map, parcel]);

  return null;
}

function CanvasEvents({ activeTool, onCanvasClick }) {
  useMapEvents({
    click(event) {
      if (activeTool) onCanvasClick([event.latlng.lng, event.latlng.lat]);
    },
  });
  return null;
}

function getZoneStyle(feature) {
  const terrainClass = feature?.properties?.terrain_class;

  const fillByClass = {
    mostly_flat: "#2f9e44",
    gentle_slope: "#82c91e",
    moderate_slope: "#f59f00",
    steep: "#f76707",
    very_steep: "#c92a2a",
  };

  return {
    color: "#ffffff",
    weight: 1,
    fillColor: fillByClass[terrainClass] || "#868e96",
    fillOpacity: 0.45,
  };
}

function slopePointStyle(feature) {
  const terrainClass = feature?.properties?.terrain_class;

  const colorByClass = {
    mostly_flat: "#2f9e44",
    gentle_slope: "#82c91e",
    moderate_slope: "#f59f00",
    steep: "#f76707",
    very_steep: "#c92a2a",
  };

  return {
    radius: 6,
    color: "#ffffff",
    weight: 1.5,
    fillColor: colorByClass[terrainClass] || "#495057",
    fillOpacity: 1,
  };
}

function onEachSlopeZone(feature, layer) {
  const properties = feature?.properties || {};

  layer.bindPopup(`
    <strong>Slope zone</strong><br />
    Slope: ${properties.local_slope_percent ?? "Unknown"}%<br />
    Class: ${properties.terrain_class ?? "Unknown"}<br />
    Elevation: ${properties.elevation_feet ?? "Unknown"} ft<br />
    Constraint: ${properties.constraint_level ?? "Unknown"}
  `);
}

function onEachSlopeSample(feature, layer) {
  const properties = feature?.properties || {};

  layer.bindPopup(`
    <strong>Terrain sample</strong><br />
    Sample: ${properties.sample_number ?? "Unknown"}<br />
    Slope: ${properties.local_slope_percent ?? "Unknown"}%<br />
    Elevation: ${properties.elevation_feet ?? "Unknown"} ft<br />
    Class: ${properties.terrain_class ?? "Unknown"}
  `);
}

function getOuterRing(geojson) {
  const geometry = geojson?.type === "Feature"
    ? geojson.geometry
    : geojson?.type === "FeatureCollection"
      ? geojson.features?.[0]?.geometry
      : geojson;

  if (geometry?.type === "Polygon") return geometry.coordinates?.[0] || [];
  if (geometry?.type === "MultiPolygon") return geometry.coordinates?.[0]?.[0] || [];
  return [];
}

function pointInRing([x, y], ring) {
  let inside = false;
  for (let index = 0, prior = ring.length - 1; index < ring.length; prior = index++) {
    const [xi, yi] = ring[index];
    const [xj, yj] = ring[prior];
    const crosses = yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi;
    if (crosses) inside = !inside;
  }
  return inside;
}

function getLineStrings(geojson) {
  const geometries = geojson?.type === "FeatureCollection"
    ? (geojson.features || []).map((feature) => feature.geometry)
    : [geojson?.type === "Feature" ? geojson.geometry : geojson];
  return geometries.flatMap((geometry) => {
    if (geometry?.type === "LineString") return [geometry.coordinates || []];
    if (geometry?.type === "MultiLineString") return geometry.coordinates || [];
    return [];
  });
}

function nearestPointOnFrontage(point, frontage) {
  let nearest = null;
  let nearestDistance = Infinity;
  const latitudeScale = Math.cos((point[1] * Math.PI) / 180);

  getLineStrings(frontage).forEach((line) => {
    for (let index = 1; index < line.length; index += 1) {
      const start = line[index - 1];
      const end = line[index];
      const dx = (end[0] - start[0]) * latitudeScale;
      const dy = end[1] - start[1];
      const lengthSquared = dx * dx + dy * dy;
      const projection = lengthSquared
        ? Math.max(0, Math.min(1, (((point[0] - start[0]) * latitudeScale * dx) + ((point[1] - start[1]) * dy)) / lengthSquared))
        : 0;
      const candidate = [start[0] + (end[0] - start[0]) * projection, start[1] + (end[1] - start[1]) * projection];
      const distance = ((candidate[0] - point[0]) * latitudeScale) ** 2 + (candidate[1] - point[1]) ** 2;
      if (distance < nearestDistance) {
        nearestDistance = distance;
        nearest = candidate;
      }
    }
  });
  return nearest;
}

function distanceFeet(start, end) {
  const latitudeFeet = (end[1] - start[1]) * 364000;
  const longitudeFeet = (end[0] - start[0]) * 364000 * Math.cos((start[1] * Math.PI) / 180);
  return Math.round(Math.hypot(latitudeFeet, longitudeFeet));
}

function buildAccessFeatures(parcel, points) {
  const frontage = parcel?.map_geometry?.frontage_edge;
  const steep = ["steep", "very_steep"].includes(parcel?.terrain?.terrain_class);
  const legalAccessConfirmed = parcel?.road_access?.legal_access_confirmed === true;
  const features = [];
  const lengths = [];

  points.forEach((home, index) => {
    const connection = nearestPointOnFrontage(home, frontage);
    if (!connection) return;
    const length = distanceFeet(home, connection);
    lengths.push(length);
    const warnings = [
      ...(!legalAccessConfirmed ? ["Legal access is not confirmed"] : []),
      ...(steep ? ["Overall terrain screen is steep"] : []),
      ...(length > 300 ? ["Long driveway concept"] : []),
    ];
    features.push({
      type: "Feature",
      properties: { kind: "driveway", unit: index + 1, length, warnings },
      geometry: { type: "LineString", coordinates: [home, connection] },
    });
    const arrivalCenter = [home[0] + (connection[0] - home[0]) * 0.16, home[1] + (connection[1] - home[1]) * 0.16];
    features.push({
      type: "Feature",
      properties: { kind: "arrival", unit: index + 1 },
      geometry: { type: "Point", coordinates: arrivalCenter },
    });
  });

  return { type: "FeatureCollection", features, lengths, legalAccessConfirmed, steep, frontageFound: features.length > 0 };
}

function buildConceptDraft(parcel, option, settings = {}) {
  const envelope = parcel?.map_geometry?.setback_envelope || parcel?.map_geometry?.simplified_parcel_boundary;
  const ring = getOuterRing(envelope);
  const requestedUnits = Math.max(1, Number(option?.units) || 1);

  if (ring.length < 3) {
    const points = [[parcel?.longitude, parcel?.latitude]];
    const draft = { apn: parcel?.apn, option, settings, points, envelopeRing: [], access: buildAccessFeatures(parcel, points), geometryBasis: "parcel center" };
    draft.assessment = assessConcept(parcel, draft);
    return draft;
  }

  const xs = ring.map(([x]) => x);
  const ys = ring.map(([, y]) => y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const center = [(minX + maxX) / 2, (minY + maxY) / 2];
  const target = [
    center[0] + ((maxX - minX) * (Number(settings.placementX) || 0)) / 200,
    center[1] + ((maxY - minY) * (Number(settings.placementY) || 0)) / 200,
  ];
  const gridSize = Math.max(9, Math.ceil(Math.sqrt(requestedUnits * 9)));
  const candidates = [];

  for (let row = 1; row < gridSize; row += 1) {
    for (let column = 1; column < gridSize; column += 1) {
      const point = [minX + ((maxX - minX) * column) / gridSize, minY + ((maxY - minY) * row) / gridSize];
      if (pointInRing(point, ring)) candidates.push(point);
    }
  }

  candidates.sort((a, b) =>
    ((a[0] - target[0]) ** 2 + (a[1] - target[1]) ** 2) -
    ((b[0] - target[0]) ** 2 + (b[1] - target[1]) ** 2)
  );
  const spacing = Math.max(1, Math.floor(candidates.length / requestedUnits));
  const points = [];
  for (let index = 0; index < candidates.length && points.length < requestedUnits; index += spacing) points.push(candidates[index]);

  const draft = {
    apn: parcel?.apn,
    option,
    settings,
    points: points.slice(0, requestedUnits),
    envelopeRing: ring,
    access: buildAccessFeatures(parcel, points.slice(0, requestedUnits)),
    geometryBasis: parcel?.map_geometry?.setback_envelope ? "screened setback envelope" : "parcel boundary",
  };
  draft.assessment = assessConcept(parcel, draft);
  return draft;
}

function buildFootprintGeoJson(conceptDraft) {
  const size = Number(conceptDraft?.settings?.homeSize) || 1800;
  const stories = Number(conceptDraft?.settings?.stories) || 2;
  const rotation = ((Number(conceptDraft?.settings?.rotation) || 0) * Math.PI) / 180;
  const footprintSquareFeet = size / stories;
  const widthFeet = Math.sqrt(footprintSquareFeet * 1.5);
  const depthFeet = footprintSquareFeet / widthFeet;

  return {
    type: "FeatureCollection",
    features: (conceptDraft?.points || []).map(([longitude, latitude], index) => {
      const feetPerDegreeLatitude = 364000;
      const feetPerDegreeLongitude = Math.max(1000, feetPerDegreeLatitude * Math.cos((latitude * Math.PI) / 180));
      const corners = [
        [-widthFeet / 2, -depthFeet / 2],
        [widthFeet / 2, -depthFeet / 2],
        [widthFeet / 2, depthFeet / 2],
        [-widthFeet / 2, depthFeet / 2],
      ].map(([x, y]) => {
        const rotatedX = x * Math.cos(rotation) - y * Math.sin(rotation);
        const rotatedY = x * Math.sin(rotation) + y * Math.cos(rotation);
        return [longitude + rotatedX / feetPerDegreeLongitude, latitude + rotatedY / feetPerDegreeLatitude];
      });
      corners.push(corners[0]);
      return {
        type: "Feature",
        properties: {
          unit: index + 1,
          size,
          stories,
          footprintSquareFeet: Math.round(footprintSquareFeet),
          fitsEnvelope: conceptDraft.envelopeRing?.length ? corners.slice(0, 4).every((corner) => pointInRing(corner, conceptDraft.envelopeRing)) : null,
        },
        geometry: { type: "Polygon", coordinates: [corners] },
      };
    }),
  };
}

function geometryRings(geojson) {
  const geometries = geojson?.type === "FeatureCollection"
    ? (geojson.features || []).map((feature) => ({ geometry: feature.geometry, properties: feature.properties || {} }))
    : [{ geometry: geojson?.type === "Feature" ? geojson.geometry : geojson, properties: geojson?.properties || {} }];
  return geometries.flatMap(({ geometry, properties }) => {
    if (geometry?.type === "Polygon") return [{ ring: geometry.coordinates?.[0] || [], properties }];
    if (geometry?.type === "MultiPolygon") return (geometry.coordinates || []).map((polygon) => ({ ring: polygon?.[0] || [], properties }));
    return [];
  });
}

function orientation(a, b, c) {
  return Math.sign((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]));
}

function segmentsCross(a, b, c, d) {
  return orientation(a, b, c) !== orientation(a, b, d) && orientation(c, d, a) !== orientation(c, d, b);
}

function ringsOverlap(first, second) {
  if (!first.length || !second.length) return false;
  if (first.some((point) => pointInRing(point, second)) || second.some((point) => pointInRing(point, first))) return true;
  for (let firstIndex = 1; firstIndex < first.length; firstIndex += 1) {
    for (let secondIndex = 1; secondIndex < second.length; secondIndex += 1) {
      if (segmentsCross(first[firstIndex - 1], first[firstIndex], second[secondIndex - 1], second[secondIndex])) return true;
    }
  }
  return false;
}

function assessConcept(parcel, conceptDraft) {
  const footprints = geometryRings(buildFootprintGeoJson(conceptDraft));
  const slopeConflicts = geometryRings(parcel?.map_geometry?.slope_zones).filter(({ ring, properties }) => {
    const classification = `${properties.terrain_class || ""} ${properties.constraint_level || ""}`.toLowerCase();
    return ["steep", "very_steep", "very steep", "high", "major"].some((term) => classification.includes(term)) && footprints.some((footprint) => ringsOverlap(footprint.ring, ring));
  });
  const outsideEnvelope = footprints.some(({ properties }) => properties.fitsEnvelope === false);
  const cautions = [];
  if (parcel?.flood_hazard?.special_flood_hazard_area) cautions.push("Parcel intersects a special flood hazard screen");
  if (parcel?.habitat?.constrained_acres || ["high", "major"].includes(parcel?.habitat?.constraint_level)) cautions.push("Parcel has mapped habitat constraints; exact footprint overlap is not resolved");
  if (parcel?.wetlands?.mapped_wetland || parcel?.wetlands?.wetland_indicator || parcel?.wetlands?.hydric_soils_indicator) cautions.push("Parcel has wetland indicators; field and boundary review may be required");
  if (parcel?.easements?.title_review_required || parcel?.easements?.wastewater_easement_found || parcel?.easements?.open_space_easement_found) cautions.push("Recorded or screened easements require title and location review");

  const conflicts = [
    ...(outsideEnvelope ? ["Building footprint extends beyond the screened envelope"] : []),
    ...(slopeConflicts.length ? ["Building footprint overlaps a mapped steep-slope zone"] : []),
  ];
  return {
    status: conflicts.length ? "conflict" : cautions.length ? "review" : "fits",
    conflicts,
    cautions,
    slopeConflict: slopeConflicts.length > 0,
  };
}

function rebuildConceptDraft(parcel, draft, points) {
  const next = {
    ...draft,
    points,
    option: { ...draft.option, units: points.length },
    settings: { ...draft.settings, unitCount: points.length },
  };
  next.access = buildAccessFeatures(parcel, points);
  next.assessment = assessConcept(parcel, next);
  return next;
}

function buildCanvasChecks(parcel, draft, objects) {
  if (!draft) return [];
  const footprints = geometryRings(buildFootprintGeoJson(draft));
  let overlaps = false;
  for (let first = 0; first < footprints.length; first += 1) {
    for (let second = first + 1; second < footprints.length; second += 1) {
      if (ringsOverlap(footprints[first].ring, footprints[second].ring)) overlaps = true;
    }
  }
  const parkingCount = objects.filter((object) => object.properties?.kind === "parking").length;
  const parkingRequired = draft.points.length * (Number(draft.settings?.parkingPerUnit) || 0);
  const lotSquareFeet = parcel?.lot_size?.square_feet || ((parcel?.lot_size?.acreage || 0) * 43560);
  const coverage = lotSquareFeet
    ? Math.round(((draft.points.length * (Number(draft.settings?.homeSize) || 0) / (Number(draft.settings?.stories) || 1)) / lotSquareFeet) * 1000) / 10
    : null;
  return [
    ["Setback fit", draft.assessment?.conflicts.some((item) => item.includes("envelope")) ? "conflict" : "pass", draft.assessment?.conflicts.find((item) => item.includes("envelope")) || "Footprints remain inside the preliminary envelope"],
    ["Building overlap", overlaps ? "conflict" : "pass", overlaps ? "Two or more conceptual footprints overlap" : "No building overlap identified"],
    ["Road access", draft.access?.frontageFound ? "pass" : "review", draft.access?.frontageFound ? "Concept connects to probable frontage" : "No frontage connection available"],
    ["Fire access", "review", "Conceptual width and fire-apparatus turnaround still require agency criteria"],
    ["Parking", parkingCount >= parkingRequired ? "pass" : "review", `${parkingCount} of ${parkingRequired} conceptual spaces placed`],
    ["Slope exposure", draft.assessment?.slopeConflict ? "conflict" : "pass", draft.assessment?.slopeConflict ? "Footprint overlaps a mapped steep-slope zone" : "No mapped steep-slope overlap identified"],
    ["Habitat / wetlands", draft.assessment?.cautions.some((item) => /habitat|wetland/i.test(item)) ? "review" : "pass", draft.assessment?.cautions.filter((item) => /habitat|wetland/i.test(item)).join("; ") || "No parcel-level habitat or wetland caution identified"],
    ["Lot coverage", coverage === null ? "review" : "pass", coverage === null ? "Lot area unavailable" : `Approximate conceptual building coverage: ${coverage}%`],
    ["Density", draft.points.length <= (parcel?.development_pathway?.concept_eligibility?.screened_max_units || draft.points.length) ? "pass" : "conflict", `${draft.points.length} conceptual units`],
  ];
}

function canvasObjectStyle(feature) {
  const colors = { driveway: "#e67700", private_road: "#7048e8", lot_line: "#1864ab", retaining_wall: "#c92a2a", measurement: "#343a40" };
  return { color: colors[feature?.properties?.kind] || "#495057", weight: feature?.properties?.kind === "private_road" ? 7 : 4, dashArray: ["lot_line", "measurement"].includes(feature?.properties?.kind) ? "7 6" : undefined };
}

function onEachConceptFootprint(feature, layer) {
  const properties = feature?.properties || {};
  const fitMessage = properties.fitsEnvelope === false
    ? "<br /><strong>Warning:</strong> footprint extends beyond the screened envelope."
    : properties.fitsEnvelope === true
      ? "<br />Footprint is inside the screened envelope."
      : "<br />Envelope fit could not be checked.";
  layer.bindPopup(`<strong>Concept home ${properties.unit}</strong><br />${properties.size.toLocaleString()} sq ft · ${properties.stories} stor${properties.stories === 1 ? "y" : "ies"}<br />Approx. ${properties.footprintSquareFeet.toLocaleString()} sq ft ground footprint${fitMessage}`);
}

function onEachAccessFeature(feature, layer) {
  const properties = feature?.properties || {};
  if (properties.kind !== "driveway") return;
  const warnings = properties.warnings?.length
    ? `<br /><strong>Review:</strong> ${properties.warnings.join("; ")}.`
    : "<br />No preliminary access warning identified.";
  layer.bindPopup(`<strong>Concept driveway ${properties.unit}</strong><br />Approximately ${properties.length.toLocaleString()} feet to probable frontage.${warnings}`);
}

function PropertyMap({ parcel, layerVisibility, conceptDraft, canvasObjects, activeCanvasTool, onCanvasClick, onMoveUnit }) {
  const geometry = parcel?.map_geometry || {};
  const parcelCenter = [
    parcel?.latitude ?? DEFAULT_CENTER[0],
    parcel?.longitude ?? DEFAULT_CENTER[1],
  ];

  return (
    <MapContainer
      center={parcelCenter}
      zoom={DEFAULT_ZOOM}
      maxZoom={22}
      zoomSnap={0.5}
      zoomDelta={0.5}
      className="property-map"
      scrollWheelZoom
    >
      <TileLayer
        attribution="&copy; OpenStreetMap contributors"
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        maxNativeZoom={19}
        maxZoom={22}
      />

      <FitMapToProperty parcel={parcel} />
      <CanvasEvents activeTool={activeCanvasTool} onCanvasClick={onCanvasClick} />

      {layerVisibility.slopeZones && geometry.slope_zones && (
        <GeoJSON
          key={`slope-zones-${parcel.apn}`}
          data={geometry.slope_zones}
          style={getZoneStyle}
          onEachFeature={onEachSlopeZone}
        />
      )}

      {layerVisibility.setback && geometry.setback_envelope && (
        <GeoJSON
          key={`setback-${parcel.apn}`}
          data={geometry.setback_envelope}
          style={{
            color: "#6f42c1",
            weight: 2,
            dashArray: "6 5",
            fillColor: "#9775fa",
            fillOpacity: 0.18,
          }}
        />
      )}

      {layerVisibility.parcel && geometry.simplified_parcel_boundary && (
        <GeoJSON
          key={`parcel-${parcel.apn}`}
          data={geometry.simplified_parcel_boundary}
          style={{
            color: "#1864ab",
            weight: 3,
            fillColor: "#74c0fc",
            fillOpacity: 0.08,
          }}
        />
      )}

      {layerVisibility.frontage && geometry.frontage_edge && (
        <GeoJSON
          key={`frontage-${parcel.apn}`}
          data={geometry.frontage_edge}
          style={{
            color: "#e03131",
            weight: 5,
          }}
        />
      )}

      {layerVisibility.rear && geometry.rear_edge && (
        <GeoJSON
          key={`rear-${parcel.apn}`}
          data={geometry.rear_edge}
          style={{
            color: "#495057",
            weight: 4,
            dashArray: "5 5",
          }}
        />
      )}

      {layerVisibility.samples && geometry.slope_samples && (
        <GeoJSON
          key={`samples-${parcel.apn}`}
          data={geometry.slope_samples}
          pointToLayer={(feature, latlng) =>
            L.circleMarker(latlng, slopePointStyle(feature))
          }
          onEachFeature={onEachSlopeSample}
        />
      )}

      {layerVisibility.concept && conceptDraft?.apn === parcel.apn && (
        <>
          {conceptDraft.access?.frontageFound && (
            <GeoJSON
              key={`concept-access-${parcel.apn}-${JSON.stringify(conceptDraft.settings)}`}
              data={conceptDraft.access}
              style={(feature) => feature?.properties?.kind === "driveway"
                ? { color: "#e67700", weight: 5, dashArray: "8 6" }
                : { color: "#ffffff", fillColor: "#f59f00", fillOpacity: 0.9, weight: 2 }}
              pointToLayer={(feature, latlng) => L.circleMarker(latlng, { radius: 8, color: "#ffffff", fillColor: "#f59f00", fillOpacity: 0.9, weight: 2 })}
              onEachFeature={onEachAccessFeature}
            />
          )}
          <GeoJSON
            key={`concept-footprints-${parcel.apn}-${JSON.stringify(conceptDraft.settings)}`}
            data={buildFootprintGeoJson(conceptDraft)}
            style={(feature) => ({ color: "#ffffff", fillColor: feature?.properties?.fitsEnvelope === false || conceptDraft.assessment?.slopeConflict ? "#d94841" : conceptDraft.assessment?.status === "review" ? "#e67700" : "#0f8b5f", fillOpacity: 0.82, weight: 2 })}
            onEachFeature={onEachConceptFootprint}
          />
          {(canvasObjects || []).length > 0 && (
            <GeoJSON
              key={`canvas-objects-${canvasObjects.length}-${canvasObjects.map((object) => object.id).join("-")}`}
              data={{ type: "FeatureCollection", features: canvasObjects }}
              style={canvasObjectStyle}
              pointToLayer={(feature, latlng) => L.circleMarker(latlng, {
                radius: feature?.properties?.kind === "parking" ? 7 : 11,
                color: "#ffffff",
                fillColor: feature?.properties?.kind === "parking" ? "#1971c2" : feature?.properties?.kind === "septic" ? "#7950f2" : "#2b8a3e",
                fillOpacity: 0.9,
                weight: 2,
              })}
              onEachFeature={(feature, layer) => layer.bindPopup(`<strong>${formatStatus(feature?.properties?.kind)}</strong>${feature?.properties?.length ? `<br />Approx. ${feature.properties.length} feet` : ""}`)}
            />
          )}
          {conceptDraft.points.map(([longitude, latitude], index) => (
            <Marker
              key={`unit-handle-${parcel.apn}-${index}`}
              position={[latitude, longitude]}
              draggable
              icon={L.divIcon({ className: "unit-drag-handle", html: `<span>${index + 1}</span>`, iconSize: [24, 24], iconAnchor: [12, 12] })}
              eventHandlers={{ dragend: (event) => { const point = event.target.getLatLng(); onMoveUnit(index, [point.lng, point.lat]); } }}
            />
          ))}
        </>
      )}

      <CircleMarker
        center={parcelCenter}
        radius={7}
        pathOptions={{
          color: "#111827",
          fillColor: "#ffffff",
          fillOpacity: 1,
          weight: 2,
        }}
      >
        <Popup>
          <strong>{parcel.address}</strong>
          <br />
          APN: {parcel.apn}
        </Popup>
      </CircleMarker>
    </MapContainer>
  );
}

function DataCard({ label, value, detail }) {
  return (
    <article className="data-card">
      <span>{label}</span>
      <strong>{value ?? "Not available"}</strong>
      {detail && <small>{detail}</small>}
    </article>
  );
}

function fallbackConceptEligibility(parcel) {
  const units = parcel?.development_scenario?.density?.preliminary_max_units ?? parcel?.feasibility_summary?.preliminary_unit_estimate;
  const zoningText = `${parcel?.zoning?.code || ""} ${parcel?.zoning?.use_regulation || ""}`.toLowerCase();
  const useText = `${parcel?.current_land_use?.description || ""}`.toLowerCase();
  const planText = `${parcel?.general_plan?.designation || ""} ${parcel?.general_plan?.designation_code || ""}`.toLowerCase();
  const residentialTerms = ["residential", "dwelling", "single family", "single-family"];
  const residential = residentialTerms.some((term) => zoningText.includes(term) || planText.includes(term));
  const vacant = ["vacant", "undeveloped", "unused land"].some((term) => useText.includes(term));
  const nonresidentialTerms = ["commercial", "industrial", "office", "institutional", "park", "open space"];
  const confirmedNonresidential = parcel?.zoning?.status === "found" && nonresidentialTerms.some((term) => zoningText.includes(term)) && !residentialTerms.some((term) => planText.includes(term));
  const ready = parcel?.zoning?.status === "found" && residential && (vacant || residentialTerms.some((term) => useText.includes(term)) || !useText) && Number.isInteger(units) && units >= 1 && !confirmedNonresidential;
  const options = ready ? [
    { id: "one_home", label: "One home", description: "Explore one detached home within the screened site envelope.", units: 1 },
    ...(units >= 2 ? [
      { id: "two_homes", label: "Two homes", description: "Explore a two-home layout within the screened yield.", units: 2 },
      { id: "lot_subdivision", label: "Lot subdivision", description: `Explore separate residential lots within the ${units}-unit screen.`, units },
      { id: "home_plus_adu", label: "Home plus ADU", description: "Explore a primary home and accessory dwelling.", units: 2 },
    ] : []),
    { id: "custom_project", label: "Custom residential project", description: `Set a custom residential program from 1 to ${units} units.`, units },
  ] : [];
  return {
    eligible: ready,
    status: ready ? "eligible" : confirmedNonresidential ? "incompatible" : "assumption_required",
    determination: ready ? "supported" : confirmedNonresidential ? "confirmed_nonresidential" : "unconfirmed_or_conflicting",
    screened_max_units: Number.isInteger(units) ? units : null,
    options,
    assumption_options: [{ id: "assumed_residential", label: "Residential concept using assumptions", description: "Explore a conservative residential layout without treating the use as confirmed.", units: Number.isInteger(units) ? units : 1 }],
    bypass_allowed: !confirmedNonresidential,
    blockers: [
      ...(confirmedNonresidential ? ["The mapped zoning and General Plan screening do not support a residential concept"] : []),
      ...(!confirmedNonresidential && (parcel?.zoning?.status !== "found" || !residential) ? ["Residential zoning or General Plan support is not confirmed"] : []),
      ...(!Number.isInteger(units) ? ["A preliminary residential unit yield is not available"] : []),
    ],
    evidence: [`Zoning: ${parcel?.zoning?.code || "not confirmed"}`, `General Plan: ${parcel?.general_plan?.designation || "not confirmed"}`, `Existing use: ${parcel?.current_land_use?.description || "not confirmed"}`],
    basis: "preliminary zoning, current-use, and density screening",
  };
}

function SiteConceptTransition({ parcel, onConceptChange }) {
  const baseEligibility = parcel?.development_pathway?.concept_eligibility || fallbackConceptEligibility(parcel);
  const [phase, setPhase] = useState("closed");
  const [selectedOption, setSelectedOption] = useState("");
  const [readinessAccepted, setReadinessAccepted] = useState(false);
  const [generatedAlternatives, setGeneratedAlternatives] = useState([]);
  const [selectedAlternative, setSelectedAlternative] = useState("");
  const [assumptionMode, setAssumptionMode] = useState("");
  const [settings, setSettings] = useState({
    unitCount: 1, homeSize: 1800, stories: 2, parkingPerUnit: 2,
    ownership: "shared", preserveStructures: "review", drivewayPreference: "probable_frontage",
    wastewater: parcel?.utilities?.inside_sanitation_district ? "sewer" : "septic_review",
    rotation: 0, placementX: 0, placementY: 0,
  });
  const assumptionOptions = baseEligibility.assumption_options?.length
    ? baseEligibility.assumption_options
    : fallbackConceptEligibility(parcel).assumption_options;
  const eligibility = assumptionMode ? {
    ...baseEligibility,
    eligible: true,
    screened_max_units: baseEligibility.screened_max_units || assumptionOptions?.[0]?.units || 1,
    options: assumptionOptions,
  } : baseEligibility;

  const activeConcept = eligibility.options.find((option) => option.id === selectedOption);

  function selectProject(option) {
    setSelectedOption(option.id);
    setSettings((current) => ({
      ...current,
      unitCount: option.id === "custom_project" ? 1 : option.units,
      ownership: option.id === "lot_subdivision" ? "separate_lots" : "shared",
    }));
  }

  function updateSetting(name, value, live = false) {
    const numeric = ["unitCount", "homeSize", "stories", "parkingPerUnit", "rotation", "placementX", "placementY"].includes(name);
    const next = { ...settings, [name]: numeric ? Number(value) : value };
    setSettings(next);
    if (live && activeConcept) {
      setGeneratedAlternatives((current) => current.map((alternative) => alternative.id === selectedAlternative ? { ...alternative, settings: next } : alternative));
      onConceptChange({ ...activeConcept, units: next.unitCount }, next);
    }
  }

  function createAlternatives() {
    const projectMaximum = ["one_home"].includes(activeConcept.id)
      ? 1
      : ["two_homes", "home_plus_adu"].includes(activeConcept.id)
        ? Math.min(2, eligibility.screened_max_units)
        : eligibility.screened_max_units;
    const balancedUnits = Math.min(projectMaximum, settings.unitCount);
    const lowRiskUnits = Math.max(1, balancedUnits > 2 ? Math.ceil(balancedUnits / 2) : 1);
    return [
      {
        id: "A", title: "Lowest entitlement risk", risk: "Lower preliminary risk",
        summary: "Fewer units, a smaller ground footprint, central placement, and straightforward access.",
        tradeoff: "Prioritizes approval simplicity over development yield.",
        settings: { ...settings, unitCount: lowRiskUnits, homeSize: Math.min(settings.homeSize, 1800), stories: Math.max(2, settings.stories), parkingPerUnit: Math.max(2, settings.parkingPerUnit), placementX: 0, placementY: 0 },
      },
      {
        id: "B", title: "Balanced development", risk: "Moderate preliminary risk",
        summary: "Uses your requested program and balances unit yield, parking, access, and footprint size.",
        tradeoff: "May require design adjustments as field information is confirmed.",
        settings: { ...settings, unitCount: balancedUnits },
      },
      {
        id: "C", title: "Maximum preliminary yield", risk: "Higher preliminary risk",
        summary: `Tests the highest ${projectMaximum}-unit yield supported for this project type by the initial screen.`,
        tradeoff: "Likely increases grading, infrastructure, access, and entitlement review.",
        settings: { ...settings, unitCount: projectMaximum, homeSize: Math.min(settings.homeSize, 1800), parkingPerUnit: Math.max(1, settings.parkingPerUnit) },
      },
    ];
  }

  const carriedData = [
    ["Parcel boundary", parcel?.map_geometry?.simplified_parcel_boundary, "Mapped"],
    ["Setback envelope", parcel?.map_geometry?.setback_envelope, "Preliminary"],
    ["Probable frontage", parcel?.map_geometry?.frontage_edge, parcel?.road_access?.frontage_confidence || "Screened"],
    ["Slope areas", parcel?.map_geometry?.slope_zones || parcel?.terrain?.status === "found", parcel?.terrain?.terrain_class],
    ["Fire constraints", parcel?.fire_hazard?.status === "found", parcel?.fire_hazard?.risk_level],
    ["Habitat", parcel?.habitat?.status === "found", parcel?.habitat?.constraint_level],
    ["Wetlands", parcel?.wetlands?.status === "found", parcel?.wetlands?.constraint_level],
    ["Easements", parcel?.easements, parcel?.easements?.title_review_required ? "Title review required" : "Screened"],
    ["Road access", parcel?.road_access, parcel?.road_access?.legal_access_confirmed ? "Legal access confirmed" : "Not confirmed"],
    ["Water", parcel?.utilities, parcel?.utilities?.water_district || "Service not confirmed"],
    ["Sewer", parcel?.utilities, parcel?.utilities?.sanitation_district || "Connection not confirmed"],
    ["Unit capacity", eligibility.screened_max_units, `${eligibility.screened_max_units || "No"} preliminary units`],
    ["Zoning", parcel?.zoning?.status === "found", parcel?.zoning?.code || "Not confirmed"],
  ];

  const readiness = [
    ...(assumptionMode ? [[assumptionMode === "use_change" ? "Residential use-change approval confirmed" : "Residential eligibility confirmed", false, "assumption"]] : []),
    ["Parcel boundary available", Boolean(parcel?.map_geometry?.simplified_parcel_boundary), "known"],
    ["Preliminary setbacks available", Boolean(parcel?.map_geometry?.setback_envelope), "known"],
    ["Road frontage identified", Boolean(parcel?.map_geometry?.frontage_edge), "known"],
    ["Terrain data available", parcel?.terrain?.status === "found" || Boolean(parcel?.map_geometry?.slope_zones), "known"],
    ["Legal access confirmed", parcel?.road_access?.legal_access_confirmed === true, "assumption"],
    ["Sewer connection confirmed", false, "assumption"],
    ["Exact easement locations available", parcel?.easements?.title_review_required === false, "assumption"],
  ];

  if (!eligibility.eligible) {
    const incompatible = eligibility.status === "incompatible" || eligibility.determination === "confirmed_nonresidential";
    return (
      <section className="concept-gate concept-gate-locked">
        <div><p className="eyebrow">Residential site concept</p><h2>{incompatible ? "Residential use is not supported by the mapped screening" : "Residential eligibility needs confirmation"}</h2><p>{incompatible ? "Housing OS cannot derive a normal residential concept from the current zoning and General Plan evidence." : "The available evidence is incomplete or conflicting. You may continue only by stating a residential-use assumption."}</p></div>
        <ul>{(eligibility.blockers || []).map((blocker) => <li key={blocker}>{blocker}</li>)}</ul>
        {(eligibility.evidence || []).length > 0 && <div className="eligibility-evidence">{eligibility.evidence.map((item) => <span key={item}>{item}</span>)}</div>}
        <button type="button" className={incompatible ? "concept-secondary" : "concept-primary"} onClick={() => { setAssumptionMode(incompatible ? "use_change" : "residential_assumption"); setPhase("choose"); }}>{incompatible ? "Explore a use-change concept" : "Continue using a residential-use assumption"}</button>
        <small className="concept-basis">{incompatible ? "This explores a hypothetical use change; it does not imply rezoning or residential approval." : "All resulting concepts will remain labeled assumption-based."}</small>
      </section>
    );
  }

  if (phase === "started" && activeConcept) {
    const configuredConcept = { ...activeConcept, units: settings.unitCount };
    const preview = buildConceptDraft(parcel, configuredConcept, settings);
    const longestDriveway = preview.access.lengths?.length ? Math.max(...preview.access.lengths) : null;
    return (
      <section className="concept-gate concept-started">
        <div>
          <p className="eyebrow">Concept {selectedAlternative} · Site concept workspace</p><h2>{generatedAlternatives.find((item) => item.id === selectedAlternative)?.title || activeConcept.label}</h2>
          <p>{settings.unitCount} unit{settings.unitCount === 1 ? "" : "s"} · {settings.homeSize.toLocaleString()} sq ft average · {settings.stories} stor{settings.stories === 1 ? "y" : "ies"} · {settings.parkingPerUnit} parking spaces per unit</p>
          <details className="advanced-controls"><summary>Placement controls</summary><div className="placement-controls"><label><span>Rotation · {settings.rotation}°</span><input type="range" min="0" max="175" step="5" value={settings.rotation} onChange={(event) => updateSetting("rotation", event.target.value, true)} /></label><label><span>Horizontal position</span><input type="range" min="-90" max="90" step="5" value={settings.placementX} onChange={(event) => updateSetting("placementX", event.target.value, true)} /></label><label><span>Vertical position</span><input type="range" min="-90" max="90" step="5" value={settings.placementY} onChange={(event) => updateSetting("placementY", event.target.value, true)} /></label></div></details>
          <div className={preview.access.frontageFound ? "access-summary" : "access-summary access-summary-warning"}><strong>{preview.access.frontageFound ? `Preliminary driveway · about ${longestDriveway?.toLocaleString()} ft` : "Driveway could not be placed"}</strong><span>{preview.access.legalAccessConfirmed ? "Legal access marked confirmed" : "Legal access still requires confirmation"}</span></div>
          <div className={`constraint-summary constraint-summary-${preview.assessment.status}`}><strong>{preview.assessment.status === "fits" ? "Fits preliminary mapped screen" : preview.assessment.status === "conflict" ? "Mapped placement conflict" : "Placement needs review"}</strong>{(preview.assessment.conflicts.length || preview.assessment.cautions.length) ? <ul>{preview.assessment.conflicts.map((item) => <li key={item}><strong>Conflict:</strong> {item}</li>)}{preview.assessment.cautions.map((item) => <li key={item}>{item}</li>)}</ul> : <span>No setback or mapped steep-slope conflict was identified.</span>}</div>
        </div>
        <div className="concept-started-actions"><button type="button" className="concept-primary" onClick={() => setPhase("alternatives")}>Compare concepts</button><button type="button" className="concept-secondary" onClick={() => { setPhase("configure"); onConceptChange(null); }}>Edit assumptions</button><button type="button" className="concept-secondary" onClick={() => { setPhase("choose"); setSelectedOption(""); onConceptChange(null); }}>Change project</button></div>
      </section>
    );
  }

  return (
    <section className="concept-gate">
      <div className="concept-gate-heading"><div><p className="eyebrow">{assumptionMode ? "Assumption-based exploration" : "Eligible next step"}</p><h2>Create a conceptual site plan</h2><p>Use the parcel boundary, setbacks, terrain, access, and environmental constraints already identified for this property.</p></div>{phase === "closed" && <button className="concept-primary" type="button" onClick={() => setPhase("choose")}>Create Site Concept</button>}</div>
      {assumptionMode && <div className="assumption-mode-banner"><strong>{assumptionMode === "use_change" ? "Hypothetical use-change concept" : "Residential-use assumption"}</strong><span>{assumptionMode === "use_change" ? "Mapped screening does not currently support residential use. This concept assumes a future use change or rezoning." : "Residential eligibility is not confirmed. No concept result should be read as zoning approval."}</span><button type="button" onClick={() => { setAssumptionMode(""); setPhase("closed"); setSelectedOption(""); onConceptChange(null); }}>Exit assumption mode</button></div>}

      {phase !== "closed" && <div className="builder-data"><div><strong>{parcel.address}</strong><span>Property data carried into this workspace—no re-entry required.</span></div><div className="builder-data-grid">{carriedData.map(([label, available, detail]) => <div key={label} className={available ? "data-chip" : "data-chip data-chip-missing"}><span>{available ? "✓" : "—"} {label}</span><small>{formatStatus(detail)}</small></div>)}</div></div>}

      {phase === "choose" && <div className="concept-chooser"><fieldset><legend>What would you like to build?</legend><div className="concept-options">{eligibility.options.map((option) => <label className={selectedOption === option.id ? "concept-option concept-option-selected" : "concept-option"} key={option.id}><input type="radio" name="site-concept" checked={selectedOption === option.id} onChange={() => selectProject(option)} /><span><strong>{option.label}</strong><small>{option.description}</small></span></label>)}</div></fieldset><div className="concept-actions"><button type="button" className="concept-secondary" onClick={() => setPhase("closed")}>Cancel</button><button type="button" className="concept-primary" disabled={!activeConcept} onClick={() => setPhase("configure")}>Continue</button></div><small className="concept-basis">Only project types supported by {eligibility.basis?.toLowerCase()} are shown.</small></div>}

      {phase === "configure" && activeConcept && <div className="concept-questionnaire"><div><p className="eyebrow">Project questions</p><h3>{activeConcept.label}</h3><p>Only assumptions relevant to this concept are requested.</p></div><div className="question-grid">
        {(activeConcept.units > 1 || activeConcept.id === "custom_project") && <label><span>Desired units</span><input type="number" min="1" max={eligibility.screened_max_units} value={settings.unitCount} onChange={(event) => updateSetting("unitCount", Math.max(1, Math.min(eligibility.screened_max_units, Number(event.target.value))))} /><small>Screened maximum: {eligibility.screened_max_units}</small></label>}
        <label><span>Average building size</span><select value={settings.homeSize} onChange={(event) => updateSetting("homeSize", event.target.value)}>{[800, 1200, 1800, 2400, 3000, 4000].map((size) => <option key={size} value={size}>{size.toLocaleString()} sq ft</option>)}</select></label>
        <label><span>Stories</span><select value={settings.stories} onChange={(event) => updateSetting("stories", event.target.value)}>{[1, 2, 3].map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
        <label><span>Parking per unit</span><select value={settings.parkingPerUnit} onChange={(event) => updateSetting("parkingPerUnit", event.target.value)}>{[0, 1, 2, 3].map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
        {settings.unitCount > 1 && <label><span>Ownership</span><select value={settings.ownership} onChange={(event) => updateSetting("ownership", event.target.value)}><option value="shared">Shared ownership</option><option value="separate_lots">Separate lots</option><option value="condominium">Condominium</option></select></label>}
        <label><span>Existing structures</span><select value={settings.preserveStructures} onChange={(event) => updateSetting("preserveStructures", event.target.value)}><option value="review">Preserve if feasible</option><option value="yes">Preserve</option><option value="no">Remove for concept</option></select></label>
        <label><span>Driveway location</span><select value={settings.drivewayPreference} onChange={(event) => updateSetting("drivewayPreference", event.target.value)}><option value="probable_frontage">Connect to probable frontage</option><option value="existing_access">Prefer existing access</option><option value="manual_review">Leave for manual placement</option></select></label>
        <label><span>Wastewater assumption</span><select value={settings.wastewater} onChange={(event) => updateSetting("wastewater", event.target.value)}><option value="sewer">Assume sewer connection</option><option value="septic_review">Assume septic feasibility review</option><option value="unknown">Keep undecided</option></select></label>
      </div><details className="advanced-controls"><summary>Advanced placement controls</summary><div className="question-grid"><label><span>Rotation · {settings.rotation}°</span><input type="range" min="0" max="175" step="5" value={settings.rotation} onChange={(event) => updateSetting("rotation", event.target.value)} /></label><label><span>Horizontal start</span><input type="range" min="-90" max="90" step="5" value={settings.placementX} onChange={(event) => updateSetting("placementX", event.target.value)} /></label><label><span>Vertical start</span><input type="range" min="-90" max="90" step="5" value={settings.placementY} onChange={(event) => updateSetting("placementY", event.target.value)} /></label></div></details><div className="concept-actions"><button type="button" className="concept-secondary" onClick={() => setPhase("choose")}>Back</button><button type="button" className="concept-primary" onClick={() => { setReadinessAccepted(false); setPhase("readiness"); }}>Review readiness</button></div></div>}

      {phase === "readiness" && activeConcept && <div className="readiness-panel"><div><p className="eyebrow">Readiness checkpoint</p><h3>Ready to model</h3><p>Known property data will be used directly. Missing items will remain stated assumptions.</p></div><div className="readiness-columns"><article><h4>Available</h4><ul>{readiness.filter(([, ready]) => ready).map(([label]) => <li key={label}><span>✓</span>{label}</li>)}</ul></article><article><h4>Assumptions required</h4><ul>{readiness.filter(([, ready]) => !ready).map(([label]) => <li key={label}><span>!</span>{label.replace(" confirmed", " not confirmed").replace(" available", " unavailable")}</li>)}</ul></article></div><div className="assumption-summary"><strong>Project assumptions</strong><span>{settings.unitCount} unit{settings.unitCount === 1 ? "" : "s"}, {settings.homeSize.toLocaleString()} sq ft average, {settings.stories} stories, {settings.parkingPerUnit} parking/unit, {formatStatus(settings.ownership)}, {formatStatus(settings.wastewater)}</span></div><label className="readiness-consent"><input type="checkbox" checked={readinessAccepted} onChange={(event) => setReadinessAccepted(event.target.checked)} /><span>I understand this concept uses preliminary data and the assumptions shown above.</span></label><div className="concept-actions"><button type="button" className="concept-secondary" onClick={() => setPhase("configure")}>Edit assumptions</button><button type="button" className="concept-primary" disabled={!readinessAccepted} onClick={() => { const alternatives = createAlternatives(); const balanced = alternatives[1]; setGeneratedAlternatives(alternatives); setSelectedAlternative("B"); setSettings(balanced.settings); onConceptChange({ ...activeConcept, units: balanced.settings.unitCount }, balanced.settings); setPhase("alternatives"); }}>Generate three concepts</button></div></div>}

      {phase === "alternatives" && activeConcept && <div className="alternatives-panel"><div><p className="eyebrow">Three preliminary approaches</p><h3>Compare site concepts</h3><p>Each concept uses the same property screening and stated assumptions with a different development priority.</p></div><div className="alternative-grid">{generatedAlternatives.map((alternative) => { const preview = buildConceptDraft(parcel, { ...activeConcept, units: alternative.settings.unitCount }, alternative.settings); return <article key={alternative.id} className={selectedAlternative === alternative.id ? "alternative-card alternative-card-selected" : "alternative-card"}><div className="alternative-label">Concept {alternative.id}</div><h4>{alternative.title}</h4><span className={`alternative-risk alternative-risk-${alternative.id.toLowerCase()}`}>{alternative.risk}</span><dl><div><dt>Units</dt><dd>{alternative.settings.unitCount}</dd></div><div><dt>Avg. size</dt><dd>{alternative.settings.homeSize.toLocaleString()} sq ft</dd></div><div><dt>Map check</dt><dd>{formatStatus(preview.assessment.status)}</dd></div></dl><p>{alternative.summary}</p><small>{alternative.tradeoff}</small><button type="button" className={selectedAlternative === alternative.id ? "concept-primary" : "concept-secondary"} onClick={() => { setSelectedAlternative(alternative.id); setSettings(alternative.settings); onConceptChange({ ...activeConcept, units: alternative.settings.unitCount }, alternative.settings); setPhase("started"); }}>{selectedAlternative === alternative.id ? "View selected concept" : `View Concept ${alternative.id}`}</button></article>; })}</div><div className="concept-actions"><button type="button" className="concept-secondary" onClick={() => setPhase("readiness")}>Back to readiness</button></div></div>}
    </section>
  );
}

function formatStatus(value) {
  if (value === null || value === undefined || value === "") {
    return "Not available";
  }

  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }

  return String(value).replaceAll("_", " ");
}

function DueDiligencePanel({ parcel }) {
  const permitHistory = parcel?.permit_history || {};
  const easements = parcel?.easements || {};
  const roadAccess = parcel?.road_access || {};

  const buildingPermits = permitHistory?.building_permit_records || [];
  const inspections = permitHistory?.building_inspection_records || [];

  const failedInspections = inspections.filter((inspection) => {
    const status = String(inspection?.status || "").toLowerCase();
    return status.includes("fail");
  });

  const accessStatus = roadAccess?.legal_access_confirmed
    ? "Confirmed"
    : "Not confirmed";

  const titleStatus = easements?.title_review_required
    ? "Title review required"
    : "No title review flag";

  const codeComplianceStatus =
    permitHistory?.code_compliance_research_status ===
    "manual_official_research_required"
      ? "Manual official research required"
      : permitHistory?.code_compliance_history_checked
        ? "Checked"
        : "Not verified";

  return (
    <section className="details-panel">
      <div>
        <p className="eyebrow">Due Diligence</p>
        <h2>Permit, access, and title review</h2>
        <p>
          These items flag records or legal questions that should be reviewed
          before relying on the parcel for acquisition, design, or development.
        </p>
      </div>

      <section className="summary-grid">
        <DataCard
          label="Building permits"
          value={
            permitHistory?.building_permit_history_checked
              ? permitHistory?.building_permit_count ?? 0
              : "Not checked"
          }
          detail={
            permitHistory?.building_permit_found
              ? "County permit record identified"
              : "No permit record identified in checked dataset"
          }
        />

        <DataCard
          label="Failed inspections"
          value={failedInspections.length}
          detail={
            failedInspections.length
              ? "Requires permit-file follow-up"
              : inspections.length
                ? "No failed inspection in returned records"
                : "No inspection records returned"
          }
        />

        <DataCard
          label="Code compliance"
          value={codeComplianceStatus}
          detail={
            permitHistory?.code_compliance_source ||
            "County code-compliance research"
          }
        />

        <DataCard
          label="Legal access"
          value={accessStatus}
          detail={
            roadAccess?.frontage_edge_found
              ? `${formatStatus(
                  roadAccess?.frontage_confidence
                )} confidence probable frontage`
              : "Probable frontage not identified"
          }
        />

        <DataCard
          label="Easement screen"
          value={
            easements?.wastewater_easement_screened ||
            easements?.open_space_easement_screened
              ? "Partial GIS screen"
              : "Not fully screened"
          }
          detail={
            easements?.wastewater_easement_found
              ? "Mapped wastewater easement identified"
              : easements?.open_space_easement_found
                ? "Mapped open-space easement identified"
                : "No mapped easement identified in successful checks"
          }
        />

        <DataCard
          label="Title review"
          value={titleStatus}
          detail="Recorded access and private easements still require title documents"
        />
      </section>

      <div className="detail-columns">
        <article>
          <h3>Permit history</h3>

          {buildingPermits.length ? (
            <ul>
              {buildingPermits.map((permit, index) => (
                <li key={`${permit?.permit_number || "permit"}-${index}`}>
                  <strong>{permit?.permit_number || "Permit record"}</strong>
                  {" · "}
                  {permit?.status || "Status unavailable"}
                  {permit?.description ? ` · ${permit.description}` : ""}
                  {permit?.applied_date ? ` · Applied ${permit.applied_date}` : ""}
                </li>
              ))}
            </ul>
          ) : (
            <p>No building permit records were returned.</p>
          )}
        </article>

        <article>
          <h3>Inspection history</h3>

          {inspections.length ? (
            <ul>
              {inspections.map((inspection, index) => (
                <li
                  key={`${inspection?.permit_number || "inspection"}-${index}`}
                >
                  <strong>
                    {inspection?.inspection_type || "Inspection"}
                  </strong>
                  {" · "}
                  {inspection?.status || "Status unavailable"}
                  {inspection?.inspection_date
                    ? ` · ${inspection.inspection_date}`
                    : ""}
                  {inspection?.permit_number
                    ? ` · Permit ${inspection.permit_number}`
                    : ""}
                </li>
              ))}
            </ul>
          ) : (
            <p>No inspection records were returned.</p>
          )}
        </article>
      </div>

      <div className="detail-columns">
        <article>
          <h3>Code compliance</h3>
          <p>
            {permitHistory?.code_compliance_message ||
              "Code-compliance history has not been verified."}
          </p>

          {permitHistory?.code_compliance_search_url && (
            <p>
              <a
                href={permitHistory.code_compliance_search_url}
                target="_blank"
                rel="noreferrer"
              >
                Open County Citizen Access
              </a>
            </p>
          )}
        </article>

        <article>
          <h3>Easements and title</h3>

          <ul>
            <li>
              Open-space easement screen:{" "}
              {easements?.open_space_easement_screened
                ? easements?.open_space_easement_found
                  ? `${easements?.open_space_easement_count ?? 0} mapped feature(s) found`
                  : "No mapped feature identified"
                : "Not completed"}
            </li>

            <li>
              Wastewater easement screen:{" "}
              {easements?.wastewater_easement_screened
                ? easements?.wastewater_easement_found
                  ? `${easements?.wastewater_easement_count ?? 0} mapped feature(s) found`
                  : "No mapped feature identified"
                : "Not completed"}
            </li>

            <li>
              Legal access:{" "}
              {roadAccess?.legal_access_confirmed
                ? "Confirmed"
                : "Not confirmed"}
            </li>

            <li>
              Title report:{" "}
              {easements?.title_review_required
                ? "Required for complete easement and access review"
                : "No title-review flag returned"}
            </li>
          </ul>

          {easements?.message && <p>{easements.message}</p>}
        </article>
      </div>
    </section>
  );
}

function createInitialSectionStatus() {
  return [...CORE_SECTIONS, ...SECONDARY_SECTIONS].reduce(
    (status, section) => {
      status[section] = "waiting";
      return status;
    },
    {}
  );
}

function mergeSectionIntoResult(currentResult, section, sectionPayload) {
  if (!currentResult?.parcels?.length || !sectionPayload?.results?.length) {
    return currentResult;
  }

  const sectionByApn = new Map(
    sectionPayload.results.map((item) => [
      String(item?.apn ?? ""),
      item?.data ?? null,
    ])
  );

  return {
    ...currentResult,
    parcels: currentResult.parcels.map((parcel) => {
      const apnKey = String(parcel?.apn ?? "");

      if (!sectionByApn.has(apnKey)) {
        return parcel;
      }

      return {
        ...parcel,
        [section]: sectionByApn.get(apnKey),
      };
    }),
  };
}

function App() {
  const [address, setAddress] = useState("3411 Fairway Drive, La Mesa, CA 91941");
  const [result, setResult] = useState(null);
  const [selectedParcelIndex, setSelectedParcelIndex] = useState(0);
  const [loading, setLoading] = useState(false);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [finalizing, setFinalizing] = useState(false);
  const [error, setError] = useState("");
  const [detailsWarning, setDetailsWarning] = useState("");
  const [conceptDraft, setConceptDraft] = useState(null);
  const [canvasObjects, setCanvasObjects] = useState([]);
  const [activeCanvasTool, setActiveCanvasTool] = useState("");
  const [pendingCanvasPoint, setPendingCanvasPoint] = useState(null);
  const [sectionStatus, setSectionStatus] = useState(
    createInitialSectionStatus
  );
  const [layerVisibility, setLayerVisibility] = useState({
    parcel: true,
    setback: true,
    slopeZones: true,
    samples: true,
    frontage: true,
    rear: false,
    concept: true,
  });

  const activeSearchId = useRef(0);

  const parcel = result?.parcels?.[selectedParcelIndex] || null;

  function isCurrentSearch(searchId) {
    return activeSearchId.current === searchId;
  }

  function setSectionsStatus(sections, status) {
    setSectionStatus((current) => {
      const next = { ...current };

      sections.forEach((section) => {
        next[section] = status;
      });

      return next;
    });
  }

  async function loadSection(cleanAddress, section, searchId) {
    if (!isCurrentSearch(searchId)) {
      return;
    }

    setSectionStatus((current) => ({
      ...current,
      [section]: "loading",
    }));

    try {
      const response = await fetch("/api/lookup-property/section", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          address: cleanAddress,
          section,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          data?.detail ||
            data?.message ||
            `${SECTION_LABELS[section]} could not be loaded.`
        );
      }

      if (!isCurrentSearch(searchId)) {
        return;
      }

      setResult((current) =>
        mergeSectionIntoResult(current, section, data)
      );

      setSectionStatus((current) => ({
        ...current,
        [section]: "complete",
      }));
    } catch (sectionError) {
      if (!isCurrentSearch(searchId)) {
        return;
      }

      setSectionStatus((current) => ({
        ...current,
        [section]: "error",
      }));

      setDetailsWarning((current) => {
        const message = `${SECTION_LABELS[section]} could not be loaded.`;

        if (current.includes(message)) {
          return current;
        }

        return current
          ? `${current} ${message}`
          : message;
      });
    }
  }

  async function loadSectionGroup(cleanAddress, sections, searchId) {
    await Promise.allSettled(
      sections.map((section) =>
        loadSection(cleanAddress, section, searchId)
      )
    );
  }

  async function finalizeProperty(cleanAddress, searchId) {
    if (!isCurrentSearch(searchId)) {
      return;
    }

    setFinalizing(true);

    try {
      const response = await fetch("/api/lookup-property", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          address: cleanAddress,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          data?.detail ||
            data?.message ||
            "Final feasibility analysis could not be completed."
        );
      }

      if (!isCurrentSearch(searchId)) {
        return;
      }

      if (data?.parcels?.length) {
        setResult(data);
        setSelectedParcelIndex((current) =>
          Math.min(current, data.parcels.length - 1)
        );
      }
    } catch (finalError) {
      if (!isCurrentSearch(searchId)) {
        return;
      }

      setDetailsWarning((current) =>
        current
          ? `${current} Final feasibility could not be completed.`
          : "Final feasibility could not be completed."
      );
    } finally {
      if (isCurrentSearch(searchId)) {
        setFinalizing(false);
      }
    }
  }

  async function searchProperty(event) {
    event.preventDefault();

    const cleanAddress = address.trim();

    if (!cleanAddress) {
      setError("Enter a property address.");
      return;
    }

    const searchId = activeSearchId.current + 1;
    activeSearchId.current = searchId;

    setLoading(true);
    setDetailsLoading(false);
    setFinalizing(false);
    setError("");
    setDetailsWarning("");
    setConceptDraft(null);
    setCanvasObjects([]);
    setActiveCanvasTool("");
    setPendingCanvasPoint(null);
    setResult(null);
    setSelectedParcelIndex(0);
    setSectionStatus(createInitialSectionStatus());

    try {
      const baseResponse = await fetch("/api/lookup-property/base", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          address: cleanAddress,
        }),
      });

      const baseData = await baseResponse.json();

      if (!baseResponse.ok) {
        throw new Error(
          baseData?.detail ||
            baseData?.message ||
            "Housing OS could not complete the parcel lookup."
        );
      }

      if (!baseData?.parcels?.length) {
        throw new Error(
          baseData?.message || "No parcels were found for that address."
        );
      }

      if (!isCurrentSearch(searchId)) {
        return;
      }

      setResult(baseData);
      setLoading(false);
      setDetailsLoading(true);

      // Stage 1: developer-critical screening.
      await loadSectionGroup(
        cleanAddress,
        CORE_SECTIONS,
        searchId
      );

      if (!isCurrentSearch(searchId)) {
        return;
      }

      // Stage 2: still-important detailed due diligence.
      await loadSectionGroup(
        cleanAddress,
        SECONDARY_SECTIONS,
        searchId
      );

      if (!isCurrentSearch(searchId)) {
        return;
      }

      setDetailsLoading(false);

      // All connector results should now be in the dataset cache.
      // This final request computes buildable area, enhanced map geometry,
      // feasibility summary, and development scenario without making the
      // user wait before seeing the earlier sections.
      await finalizeProperty(
        cleanAddress,
        searchId
      );
    } catch (requestError) {
      if (!isCurrentSearch(searchId)) {
        return;
      }

      setResult(null);
      setError(requestError.message);
      setLoading(false);
      setDetailsLoading(false);
      setFinalizing(false);
    }
  }

  function toggleLayer(layerName) {
    setLayerVisibility((current) => ({
      ...current,
      [layerName]: !current[layerName],
    }));
  }

  function startConcept(option, settings) {
    setConceptDraft(option ? buildConceptDraft(parcel, option, settings) : null);
    if (option) setLayerVisibility((current) => ({ ...current, concept: true }));
    else {
      setCanvasObjects([]);
      setActiveCanvasTool("");
      setPendingCanvasPoint(null);
    }
  }

  function moveConceptUnit(index, point) {
    setConceptDraft((current) => {
      if (!current) return current;
      const points = current.points.map((existing, pointIndex) => pointIndex === index ? point : existing);
      return rebuildConceptDraft(parcel, current, points);
    });
  }

  function handleCanvasClick(point) {
    if (!conceptDraft || !activeCanvasTool) return;
    if (activeCanvasTool === "add_unit") {
      const maximum = parcel?.development_pathway?.concept_eligibility?.screened_max_units
        || parcel?.development_scenario?.density?.preliminary_max_units
        || parcel?.feasibility_summary?.preliminary_unit_estimate
        || conceptDraft.option?.units
        || 1;
      if (conceptDraft.points.length < maximum) setConceptDraft((current) => rebuildConceptDraft(parcel, current, [...current.points, point]));
      return;
    }
    if (["parking", "septic", "open_space"].includes(activeCanvasTool)) {
      setCanvasObjects((current) => [...current, { id: `${activeCanvasTool}-${Date.now()}`, type: "Feature", properties: { kind: activeCanvasTool }, geometry: { type: "Point", coordinates: point } }]);
      return;
    }
    if (!pendingCanvasPoint) {
      setPendingCanvasPoint(point);
      return;
    }
    const length = distanceFeet(pendingCanvasPoint, point);
    setCanvasObjects((current) => [...current, { id: `${activeCanvasTool}-${Date.now()}`, type: "Feature", properties: { kind: activeCanvasTool, length }, geometry: { type: "LineString", coordinates: [pendingCanvasPoint, point] } }]);
    setPendingCanvasPoint(null);
  }

  function removeLastUnit() {
    setConceptDraft((current) => current?.points?.length > 1 ? rebuildConceptDraft(parcel, current, current.points.slice(0, -1)) : current);
  }

  const completedSections = Object.values(sectionStatus).filter(
    (status) => status === "complete"
  ).length;

  const failedSections = Object.values(sectionStatus).filter(
    (status) => status === "error"
  ).length;

  const totalSections = CORE_SECTIONS.length + SECONDARY_SECTIONS.length;

  const activeCoreSection = CORE_SECTIONS.find(
    (section) => sectionStatus[section] === "loading"
  );

  const activeSecondarySection = SECONDARY_SECTIONS.find(
    (section) => sectionStatus[section] === "loading"
  );
  const canvasChecks = buildCanvasChecks(parcel, conceptDraft, canvasObjects);

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Housing OS</p>
          <h1>Property Feasibility Map</h1>
          <p>
            Search an address to review parcel geometry, setbacks, terrain,
            access, and early development constraints.
          </p>
        </div>
      </header>

      <section className="search-panel">
        <form onSubmit={searchProperty}>
          <label htmlFor="address">Property address</label>
          <div className="search-row">
            <input
              id="address"
              value={address}
              onChange={(event) => setAddress(event.target.value)}
              placeholder="3411 Fairway Drive, La Mesa, CA 91941"
            />
            <button type="submit" disabled={loading}>
              {loading ? "Finding parcel..." : "Analyze property"}
            </button>
          </div>
        </form>

        {error && <div className="error-message">{error}</div>}

        {result && (detailsLoading || finalizing) && (
          <p>
            {detailsLoading
              ? `Property loaded. ${completedSections} of ${totalSections} datasets complete${
                  failedSections ? `, ${failedSections} unavailable` : ""
                }.${
                  activeCoreSection
                    ? ` Loading ${SECTION_LABELS[activeCoreSection]}...`
                    : activeSecondarySection
                      ? ` Loading ${SECTION_LABELS[activeSecondarySection]}...`
                      : ""
                }`
              : "All datasets loaded. Housing OS is calculating final feasibility and map constraints."}
          </p>
        )}

        {detailsWarning && (
          <div className="error-message">{detailsWarning}</div>
        )}

        {result?.parcels?.length > 1 && (
          <div className="parcel-selector">
            <label htmlFor="parcel">Parcel</label>
            <select
              id="parcel"
              value={selectedParcelIndex}
              onChange={(event) =>
                setSelectedParcelIndex(Number(event.target.value))
              }
            >
              {result.parcels.map((item, index) => (
                <option key={`${item.apn}-${index}`} value={index}>
                  {item.apn} · {item.address}
                </option>
              ))}
            </select>
          </div>
        )}
      </section>

      {parcel ? (
        <>
          <section className="summary-grid">
            <DataCard
              label="Parcel"
              value={parcel.apn}
              detail={parcel.address}
            />

            <DataCard
              label="Lot size"
              value={
                parcel.lot_size?.acreage
                  ? `${parcel.lot_size.acreage} acres`
                  : null
              }
              detail={
                parcel.zoning?.code ||
                (sectionStatus.zoning === "loading"
                  ? "Zoning loading..."
                  : null)
              }
            />

            <DataCard
              label="Preliminary units"
              value={
                parcel.general_plan?.estimate_status ===
                "specific_plan_review_required"
                  ? "Specific Plan Review"
                  : parcel.feasibility_summary?.preliminary_unit_estimate ??
                    parcel.general_plan?.estimated_maximum_units ??
                    (sectionStatus.general_plan === "loading" ||
                    sectionStatus.general_plan === "waiting"
                      ? "Loading..."
                      : null)
              }
              detail={
                parcel.general_plan?.estimate_status ===
                "specific_plan_review_required"
                  ? parcel.general_plan?.designation
                  : parcel.general_plan?.designation_code
              }
            />

            <DataCard
              label="Setback screen"
              value={
                parcel.buildable_area?.directional_setback_screened_acres
                  ? `${parcel.buildable_area.directional_setback_screened_acres} acres`
                  : finalizing || detailsLoading
                    ? "Calculating..."
                    : null
              }
              detail={
                parcel.buildable_area?.directional_setback_screened_percent
                  ? `${parcel.buildable_area.directional_setback_screened_percent}% of mapped geometry; not final buildable area`
                  : parcel.road_access
                    ? "Final envelope updates after all constraints load"
                    : "Waiting for road and zoning data"
              }
            />

            <DataCard
              label="Terrain"
              value={
                parcel.terrain?.terrain_class
                  ? parcel.terrain.terrain_class.replaceAll("_", " ")
                  : sectionStatus.terrain === "loading" ||
                      sectionStatus.terrain === "waiting"
                    ? "Loading..."
                    : parcel.terrain?.status === "not_found"
                      ? "Unavailable"
                      : null
              }
              detail={
                parcel.terrain?.estimated_slope_percent !== null &&
                parcel.terrain?.estimated_slope_percent !== undefined
                  ? `${parcel.terrain.estimated_slope_percent}% highest sampled local slope`
                  : sectionStatus.terrain === "loading"
                    ? "Terrain analysis in progress"
                    : parcel.terrain?.status === "not_found"
                      ? parcel.terrain?.message || "Terrain data unavailable"
                      : null
              }
            />

            <DataCard
              label="Overall screening"
              value={
                parcel.feasibility_summary?.overall_rating
                  ? parcel.feasibility_summary.overall_rating.replaceAll(
                      "_",
                      " "
                    )
                  : finalizing || detailsLoading
                    ? "Building..."
                    : "Incomplete data"
              }
              detail={
                parcel.feasibility_summary
                  ? `${parcel.feasibility_summary?.major_constraint_count ?? 0} major constraints`
                  : "Updates after all screening datasets finish"
              }
            />
          </section>

          <section className="map-layout">
            <aside className="layer-panel">
              <h2>Map layers</h2>

              {conceptDraft && (
                <div className="canvas-toolbar">
                  <h3>Edit concept</h3>
                  <p>Drag numbered building handles, or select a tool and click the map.</p>
                  <div className="canvas-tools">
                    {[
                      ["add_unit", "Add unit"], ["driveway", "Draw driveway"], ["parking", "Add parking"],
                      ["private_road", "Private road"], ["lot_line", "Lot line"], ["septic", "Septic area"],
                      ["open_space", "Open space"], ["retaining_wall", "Retaining wall"], ["measurement", "Measure"],
                    ].map(([tool, label]) => <button key={tool} type="button" className={activeCanvasTool === tool ? "canvas-tool canvas-tool-active" : "canvas-tool"} onClick={() => { setActiveCanvasTool((current) => current === tool ? "" : tool); setPendingCanvasPoint(null); }}>{label}</button>)}
                  </div>
                  <div className="canvas-tool-actions"><button type="button" onClick={removeLastUnit} disabled={conceptDraft.points.length <= 1}>Remove last unit</button><button type="button" onClick={() => setCanvasObjects((current) => current.slice(0, -1))} disabled={!canvasObjects.length}>Undo object</button></div>
                  {activeCanvasTool && <small>{pendingCanvasPoint ? "Click the map again to finish the line." : ["parking", "septic", "open_space", "add_unit"].includes(activeCanvasTool) ? "Click the map to place it." : "Click the start and end points on the map."}</small>}
                </div>
              )}

              {[
                ["parcel", "Parcel boundary"],
                ["setback", "Setback envelope"],
                ["slopeZones", "Slope zones"],
                ["samples", "Terrain samples"],
                ["frontage", "Probable frontage"],
                ["rear", "Probable rear edge"],
                ...(conceptDraft?.apn === parcel.apn ? [["concept", "Site concept"]] : []),
              ].map(([key, label]) => (
                <label className="layer-toggle" key={key}>
                  <input
                    type="checkbox"
                    checked={layerVisibility[key]}
                    onChange={() => toggleLayer(key)}
                  />
                  <span>{label}</span>
                </label>
              ))}

              <div className="legend">
                <h3>Slope legend</h3>
                <span>
                  <i className="legend-flat" />
                  Mostly flat
                </span>
                <span>
                  <i className="legend-gentle" />
                  Gentle
                </span>
                <span>
                  <i className="legend-moderate" />
                  Moderate
                </span>
                <span>
                  <i className="legend-steep" />
                  Steep
                </span>
                <span>
                  <i className="legend-very-steep" />
                  Very steep
                </span>
              </div>

              <p className="map-note">
                All boundaries and slope areas are preliminary screening
                geometry, not survey-grade determinations.
              </p>
            </aside>

            <PropertyMap
              parcel={parcel}
              layerVisibility={layerVisibility}
              conceptDraft={conceptDraft}
              canvasObjects={canvasObjects}
              activeCanvasTool={activeCanvasTool}
              onCanvasClick={handleCanvasClick}
              onMoveUnit={moveConceptUnit}
            />
          </section>

          {conceptDraft && (
            <section className="canvas-checks-panel">
              <div><p className="eyebrow">Live concept checks</p><h2>Interactive canvas review</h2><p>Checks update as buildings and site objects change. They remain preliminary screening results.</p></div>
              <div className="canvas-check-grid">{canvasChecks.map(([label, status, detail]) => <article key={label} className={`canvas-check canvas-check-${status}`}><span>{status === "pass" ? "✓" : status === "conflict" ? "×" : "!"}</span><div><strong>{label}</strong><small>{detail}</small></div></article>)}</div>
            </section>
          )}

          {parcel.feasibility_summary && (
            <section className="details-panel">
              <div>
                <h2>Screening conclusion</h2>
                <p>{parcel.feasibility_summary?.conclusion}</p>
              </div>

              <div className="detail-columns">
                <article>
                  <h3>Opportunities</h3>
                  <ul>
                    {(parcel.feasibility_summary?.opportunities || []).map(
                      (item) => (
                        <li key={item}>{item}</li>
                      )
                    )}
                  </ul>
                </article>

                <article>
                  <h3>Constraints</h3>
                  <ul>
                    {(parcel.feasibility_summary?.constraints || []).map(
                      (item) => (
                        <li key={item}>{item}</li>
                      )
                    )}
                  </ul>
                </article>
              </div>
            </section>
          )}

          {parcel.development_pathway && (
            <section className="pathway-panel">
              <div className="pathway-heading">
                <div>
                  <span className="eyebrow">{parcel.development_pathway.scenario_label}</span>
                  <h2>{parcel.development_pathway.scenario_name}</h2>
                  <p><strong>Likely entitlement:</strong> {parcel.development_pathway.likely_entitlement}</p>
                </div>
                <div className={`complexity complexity-${parcel.development_pathway.approval_complexity?.toLowerCase()}`}>
                  <span>Approval complexity</span>
                  <strong>{parcel.development_pathway.approval_complexity}</strong>
                </div>
              </div>

              <div className="pathway-grid">
                {[
                  ["Planning", parcel.development_pathway.planning_findings],
                  ["Environmental", parcel.development_pathway.environmental_findings],
                  ["Infrastructure", parcel.development_pathway.infrastructure_findings],
                ].map(([title, findings]) => (
                  <article key={title}>
                    <h3>{title}</h3>
                    <ul className="finding-list">
                      {(findings || []).map((finding) => (
                        <li key={`${title}-${finding.label}`}>
                          <span className={`finding-icon finding-${finding.status}`}>
                            {finding.status === "pass" ? "✓" : "⚠"}
                          </span>
                          <div><strong>{finding.label}</strong><small>{finding.detail}</small></div>
                        </li>
                      ))}
                    </ul>
                  </article>
                ))}
              </div>

              <div className="pathway-footer">
                <article>
                  <h3>Studies likely required</h3>
                  <ul>{(parcel.development_pathway.studies_likely_required || []).map((study) => <li key={study}>{study}</li>)}</ul>
                </article>
                <dl>
                  <div><dt>Preconstruction timeline</dt><dd>{parcel.development_pathway.preconstruction_timeline}</dd></div>
                  <div><dt>Confidence</dt><dd>{parcel.development_pathway.confidence_percent}%</dd></div>
                  <div><dt>Biggest unknown</dt><dd>{parcel.development_pathway.biggest_unknown}</dd></div>
                </dl>
              </div>
              <p className="pathway-disclaimer">{parcel.development_pathway.disclaimer}</p>
            </section>
          )}

          <SiteConceptTransition key={parcel.apn || selectedParcelIndex} parcel={parcel} onConceptChange={startConcept} />

          {parcel.permit_history && (
            <DueDiligencePanel parcel={parcel} />
          )}
        </>
      ) : (
        <section className="empty-state">
          <h2>Your property map will appear here</h2>
          <p>
            Enter an address above and Housing OS will load the parcel first,
            then add development datasets as each source responds.
          </p>
        </section>
      )}
    </main>
  );
}

export default App;
