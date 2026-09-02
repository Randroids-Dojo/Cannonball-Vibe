// Midground hills and distant mountain massifs.
//
// The meshes are deterministic noise heightfields instanced with per-instance
// footprint and height scale, so all mapping is object-space triplanar: it is
// independent of the local-origin rebase and of the instance transform.
// Rock, forest and snow are chosen from world slope and from height above the
// instance base, which lets one mesh read as a green foothill at 90 m and a
// snow-capped peak at 500 m.
shader_type spatial;
render_mode cull_back, depth_draw_opaque;

uniform sampler2D rock_albedo : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D rock_normal : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D rock_arm : hint_default_white, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D grass_albedo : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D grass_normal : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;

uniform float triplanar_tile_meters : hint_range(1.0, 400.0) = 38.0;
uniform float forest_line_meters = 3400.0;
uniform float snow_line_meters = 3600.0;
uniform float snow_band_meters = 260.0;
uniform float base_altitude_meters = 2400.0;
uniform vec3 forest_tint : source_color = vec3(0.30, 0.40, 0.24);
uniform vec3 rock_tint : source_color = vec3(0.92, 0.90, 0.88);
uniform vec3 snow_color : source_color = vec3(0.96, 0.97, 1.0);
uniform float forest_weight : hint_range(0.0, 1.0) = 1.0;

varying vec3 object_position;
varying vec3 world_normal;
varying float height_above_base;
varying float view_distance;

float hash13(vec3 p3) {
	p3 = fract(p3 * 0.1031);
	p3 += dot(p3, p3.zyx + 31.32);
	return fract((p3.x + p3.y) * p3.z);
}

void vertex() {
	object_position = VERTEX;
	world_normal = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);
	vec4 world = MODEL_MATRIX * vec4(VERTEX, 1.0);
	vec4 base = MODEL_MATRIX * vec4(0.0, 0.0, 0.0, 1.0);
	height_above_base = world.y - base.y;
	view_distance = length((MODELVIEW_MATRIX * vec4(VERTEX, 1.0)).xyz);
}

vec4 triplanar(sampler2D tex, vec3 p, vec3 blend) {
	vec4 x = texture(tex, p.yz);
	vec4 y = texture(tex, p.xz);
	vec4 z = texture(tex, p.xy);
	return x * blend.x + y * blend.y + z * blend.z;
}

void fragment() {
	vec3 n = normalize(world_normal);
	vec3 blend = abs(n);
	blend = pow(blend, vec3(4.0));
	blend /= (blend.x + blend.y + blend.z);
	vec3 p = object_position * vec3(1.0, 0.35, 1.0) * (120.0 / triplanar_tile_meters);

	vec3 rock = triplanar(rock_albedo, p, blend).rgb * rock_tint;
	vec3 rock_arm_s = triplanar(rock_arm, p, blend).rgb;
	vec3 grass = triplanar(grass_albedo, p * 2.3, blend).rgb * forest_tint;

	float altitude = base_altitude_meters + height_above_base;
	float slope = clamp(n.y, 0.0, 1.0);
	float forest = smoothstep(0.55, 0.85, slope) * (1.0 - smoothstep(forest_line_meters - 250.0, forest_line_meters, altitude)) * forest_weight;
	float snow = smoothstep(snow_line_meters - snow_band_meters, snow_line_meters + snow_band_meters, altitude)
		* smoothstep(0.35, 0.75, slope);
	snow *= 0.7 + 0.3 * hash13(floor(object_position * 40.0));

	vec3 albedo = mix(rock, grass, forest);
	albedo = mix(albedo, snow_color, snow);
	float far = smoothstep(1500.0, 9000.0, view_distance);
	ALBEDO = mix(albedo, albedo * 0.9 + vec3(0.04, 0.05, 0.07), far);
	NORMAL_MAP = mix(triplanar(rock_normal, p, blend).rgb, vec3(0.5, 0.5, 1.0), max(snow, far));
	NORMAL_MAP_DEPTH = 0.8;
	ROUGHNESS = mix(clamp(rock_arm_s.g, 0.5, 1.0), 0.75, snow);
	AO = mix(rock_arm_s.r, 1.0, snow);
	AO_LIGHT_AFFECT = 0.4;
	METALLIC = 0.0;
	SPECULAR = mix(0.25, 0.45, snow);
}
