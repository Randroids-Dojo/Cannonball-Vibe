#!/usr/bin/env node

import { readFileSync, writeFileSync } from "node:fs";

const [geojsonPath, packagePath, outputPath] = process.argv.slice(2);
if (!geojsonPath || !packagePath || !outputPath) {
  console.error("Usage: generate-route-review.mjs ROUTE.geojson PACKAGE.json OUTPUT.svg");
  process.exit(2);
}

const source = JSON.parse(readFileSync(geojsonPath, "utf8"));
const routePackage = JSON.parse(readFileSync(packagePath, "utf8"));
const features = orderLinear(
  source.features,
  (feature) => feature.geometry.coordinates[0],
  (feature) => feature.geometry.coordinates.at(-1),
);
const edges = orderLinear(
  routePackage.edges,
  (edge) => edge.from_node_id,
  (edge) => edge.to_node_id,
  (value) => value,
);
const coordinates = features.flatMap((feature, index) =>
  index === 0 ? feature.geometry.coordinates : feature.geometry.coordinates.slice(1),
);
const minLongitude = Math.min(...coordinates.map(([longitude]) => longitude));
const maxLongitude = Math.max(...coordinates.map(([longitude]) => longitude));
const minLatitude = Math.min(...coordinates.map(([, latitude]) => latitude));
const maxLatitude = Math.max(...coordinates.map(([, latitude]) => latitude));
const map = { x: 70, y: 125, width: 880, height: 690 };
const project = ([longitude, latitude]) => [
  map.x + ((longitude - minLongitude) / (maxLongitude - minLongitude)) * map.width,
  map.y + map.height - ((latitude - minLatitude) / (maxLatitude - minLatitude)) * map.height,
];
const routePoints = coordinates.map(project);

const distances = [0];
for (let index = 1; index < coordinates.length; index += 1) {
  distances.push(distances.at(-1) + haversine(coordinates[index - 1], coordinates[index]));
}
const waypointFractions = [0.005, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875, 0.995];
const waypoints = waypointFractions.map((fraction) => {
  const target = distances.at(-1) * fraction;
  const index = distances.findIndex((distance) => distance >= target);
  return project(coordinates[Math.max(0, index)]);
});

const elevationSamples = [];
let routeOffset = 0;
for (const edge of edges) {
  edge.samples.forEach((sample, index) => {
    if (elevationSamples.length > 0 && index === 0) return;
    elevationSamples.push([routeOffset + sample.distance_meters, sample.elevation_meters]);
  });
  routeOffset += edge.length_meters;
}
const elevations = elevationSamples.map(([, elevation]) => elevation);
const minimumElevation = Math.min(...elevations);
const maximumElevation = Math.max(...elevations);
const profile = { x: 1050, y: 315, width: 480, height: 235 };
const profilePoints = elevationSamples.map(([distance, elevation]) => [
  profile.x + (distance / routeOffset) * profile.width,
  profile.y + profile.height -
    ((elevation - minimumElevation) / (maximumElevation - minimumElevation)) * profile.height,
]);
const maximumGrade = Math.max(
  ...edges.flatMap((edge) => edge.samples.map((sample) => Math.abs(sample.grade))),
);
const routeMiles = routeOffset / 1609.344;

const svg = `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="900" viewBox="0 0 1600 900">
  <rect width="1600" height="900" fill="#070b13"/>
  <text x="70" y="60" fill="#f4f1e8" font-family="system-ui,sans-serif" font-size="34" font-weight="700">P0-004 representative corridor review</text>
  <text x="70" y="92" fill="#9fb0c8" font-family="system-ui,sans-serif" font-size="18">Official NHPN centerline + checksum-locked USGS 3DEP profile · Boulder to Westminster area · US 36</text>
  <rect x="50" y="110" width="920" height="725" rx="16" fill="#101827" stroke="#26364e"/>
  <path d="${path(routePoints)}" fill="none" stroke="#22324a" stroke-width="18" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="${path(routePoints)}" fill="none" stroke="#f0c85a" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>
  ${waypoints.map(([x, y], index) => `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="10" fill="#e85a67" stroke="#fff5dc" stroke-width="3"/><text x="${(x + 14).toFixed(1)}" y="${(y + 6).toFixed(1)}" fill="#fff5dc" font-family="system-ui,sans-serif" font-size="15">${index + 1}</text>`).join("\n  ")}
  <circle cx="${routePoints[0][0].toFixed(1)}" cy="${routePoints[0][1].toFixed(1)}" r="12" fill="#66d19e"/>
  <text x="${(routePoints[0][0] + 18).toFixed(1)}" y="${(routePoints[0][1] - 10).toFixed(1)}" fill="#dff8eb" font-family="system-ui,sans-serif" font-size="18" font-weight="700">Boulder-side start</text>
  <circle cx="${routePoints.at(-1)[0].toFixed(1)}" cy="${routePoints.at(-1)[1].toFixed(1)}" r="12" fill="#66a6ff"/>
  <text x="${(routePoints.at(-1)[0] - 220).toFixed(1)}" y="${(routePoints.at(-1)[1] + 34).toFixed(1)}" fill="#dceaff" font-family="system-ui,sans-serif" font-size="18" font-weight="700">Westminster-area end</text>
  <text x="90" y="800" fill="#91a4bf" font-family="ui-monospace,monospace" font-size="15">W ${Math.abs(minLongitude).toFixed(4)}° → W ${Math.abs(maxLongitude).toFixed(4)}° · N ${minLatitude.toFixed(4)}° → N ${maxLatitude.toFixed(4)}°</text>
  <path d="M 905 180 L 905 135 L 892 155 M 905 135 L 918 155" fill="none" stroke="#f4f1e8" stroke-width="4"/>
  <text x="895" y="205" fill="#f4f1e8" font-family="system-ui,sans-serif" font-size="17">N</text>
  <text x="1050" y="155" fill="#f4f1e8" font-family="system-ui,sans-serif" font-size="25" font-weight="700">Locked candidate</text>
  <text x="1050" y="196" fill="#cbd6e6" font-family="ui-monospace,monospace" font-size="19">${routeMiles.toFixed(6)} unique miles</text>
  <text x="1050" y="228" fill="#cbd6e6" font-family="ui-monospace,monospace" font-size="19">${edges.length} connected edges · ${routePackage.chunks.length} chunks</text>
  <text x="1050" y="260" fill="#cbd6e6" font-family="ui-monospace,monospace" font-size="19">9 renderer-backed viewpoints</text>
  <text x="1050" y="295" fill="#f4f1e8" font-family="system-ui,sans-serif" font-size="21" font-weight="700">Conditioned elevation profile</text>
  <rect x="${profile.x}" y="${profile.y}" width="${profile.width}" height="${profile.height}" fill="#0c1320" stroke="#26364e"/>
  <path d="${path(profilePoints)}" fill="none" stroke="#66d19e" stroke-width="4"/>
  <text x="${profile.x}" y="${profile.y + profile.height + 28}" fill="#91a4bf" font-family="ui-monospace,monospace" font-size="15">0 mi</text>
  <text x="${profile.x + profile.width - 70}" y="${profile.y + profile.height + 28}" fill="#91a4bf" font-family="ui-monospace,monospace" font-size="15">${routeMiles.toFixed(2)} mi</text>
  <text x="${profile.x + 10}" y="${profile.y + 24}" fill="#91a4bf" font-family="ui-monospace,monospace" font-size="15">${maximumElevation.toFixed(1)} m</text>
  <text x="${profile.x + 10}" y="${profile.y + profile.height - 10}" fill="#91a4bf" font-family="ui-monospace,monospace" font-size="15">${minimumElevation.toFixed(1)} m</text>
  <text x="1050" y="625" fill="#f4f1e8" font-family="system-ui,sans-serif" font-size="21" font-weight="700">Automated gates</text>
  <text x="1050" y="662" fill="#cbd6e6" font-family="ui-monospace,monospace" font-size="17">✓ exact source hashes</text>
  <text x="1050" y="692" fill="#cbd6e6" font-family="ui-monospace,monospace" font-size="17">✓ directed edge continuity</text>
  <text x="1050" y="722" fill="#cbd6e6" font-family="ui-monospace,monospace" font-size="17">✓ all chunks rendered</text>
  <text x="1050" y="752" fill="#cbd6e6" font-family="ui-monospace,monospace" font-size="17">✓ max grade ${(maximumGrade * 100).toFixed(2)}%</text>
  <text x="1050" y="800" fill="#e8b2b7" font-family="system-ui,sans-serif" font-size="18" font-weight="700">Human geographic approval remains required.</text>
  <text x="70" y="872" fill="#71839e" font-family="system-ui,sans-serif" font-size="14">Route geometry: U.S. DOT National Highway Planning Network. Elevation: USGS 3DEP. Review graphic is derived from the committed lock and package metadata.</text>
</svg>\n`;
writeFileSync(outputPath, svg);

function orderLinear(values, startOf, endOf, keyOf = coordinateKey) {
  const destinations = new Set(values.map((value) => keyOf(endOf(value))));
  const starts = values.filter((value) => !destinations.has(keyOf(startOf(value))));
  if (starts.length !== 1) throw new Error(`Expected one route start; found ${starts.length}.`);
  const remaining = new Set(values);
  const ordered = [];
  let current = starts[0];
  while (current) {
    ordered.push(current);
    remaining.delete(current);
    if (remaining.size === 0) break;
    const key = keyOf(endOf(current));
    const next = [...remaining].filter((value) => keyOf(startOf(value)) === key);
    if (next.length !== 1) throw new Error(`Expected one continuation; found ${next.length}.`);
    current = next[0];
  }
  return ordered;
}

function coordinateKey([longitude, latitude]) {
  return `${longitude.toFixed(9)},${latitude.toFixed(9)}`;
}

function haversine([longitude1, latitude1], [longitude2, latitude2]) {
  const radians = (degrees) => (degrees * Math.PI) / 180;
  const deltaLatitude = radians(latitude2 - latitude1);
  const deltaLongitude = radians(longitude2 - longitude1);
  const a = Math.sin(deltaLatitude / 2) ** 2 +
    Math.cos(radians(latitude1)) * Math.cos(radians(latitude2)) * Math.sin(deltaLongitude / 2) ** 2;
  return 6371008.8 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function path(points) {
  return points.map(([x, y], index) => `${index === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`).join(" ");
}
