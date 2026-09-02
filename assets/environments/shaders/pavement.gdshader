// Mainline pavement and paved shoulder.
//
// UVs are metres: U is lateral offset from the route centreline, V is route
// distance wrapped to the anti-tiling period on the CPU. A second, rotated
// sample scale and a low-frequency hash break the repeat; a large-scale
// patch mask darkens and smooths bands the way sealed cracks and fresh
// overlays do, and the far field converges on the mean colour so the road
// does not shimmer at speed.
shader_type spatial;
render_mode cull_disabled, depth_draw_opaque;

uniform sampler2D albedo_map : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D normal_map : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D arm_map : hint_default_white, filter_linear_mipmap_anisotropic, repeat_enable;

uniform float tile_meters : hint_range(0.5, 20.0) = 3.4;
uniform float macro_tile_meters : hint_range(5.0, 200.0) = 23.0;
uniform vec3 tint : source_color = vec3(1.0);
uniform float roughness_bias : hint_range(-0.5, 0.5) = 0.0;
uniform float patch_strength : hint_range(0.0, 1.0) = 0.18;
uniform float far_fade_start_meters = 220.0;
uniform float far_fade_end_meters = 1800.0;
uniform float normal_strength : hint_range(0.0, 2.0) = 0.9;

varying vec2 uv_meters;
varying float view_distance;

float hash12(vec2 p) {
	vec3 p3 = fract(vec3(p.xyx) * 0.1031);
	p3 += dot(p3, p3.yzx + 33.33);
	return fract((p3.x + p3.y) * p3.z);
}

float value_noise(vec2 p) {
	vec2 i = floor(p);
	vec2 f = fract(p);
	f = f * f * (3.0 - 2.0 * f);
	float a = hash12(i);
	float b = hash12(i + vec2(1.0, 0.0));
	float c = hash12(i + vec2(0.0, 1.0));
	float d = hash12(i + vec2(1.0, 1.0));
	return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
}

void vertex() {
	uv_meters = UV;
	view_distance = length((MODELVIEW_MATRIX * vec4(VERTEX, 1.0)).xyz);
}

void fragment() {
	vec2 uv = uv_meters / tile_meters;
	vec2 macro_uv = mat2(vec2(0.83, 0.56), vec2(-0.56, 0.83)) * (uv_meters / macro_tile_meters);
	float bomb = smoothstep(0.35, 0.65, value_noise(uv_meters / 31.0));
	vec3 albedo = mix(texture(albedo_map, uv).rgb, texture(albedo_map, macro_uv).rgb, bomb);
	vec3 normal = texture(normal_map, uv).rgb;
	vec3 arm = texture(arm_map, uv).rgb;

	// Overlay and seal patches: long along the road, narrow across it.
	float patch = value_noise(vec2(uv_meters.x / 2.6, uv_meters.y / 47.0));
	patch = smoothstep(0.62, 0.78, patch) * patch_strength;
	albedo *= 1.0 - patch * 0.55;
	float roughness = clamp(arm.g + roughness_bias - patch * 0.25, 0.25, 1.0);

	float far = smoothstep(far_fade_start_meters, far_fade_end_meters, view_distance);
	albedo = mix(albedo, textureLod(albedo_map, uv, 9.0).rgb, far);
	normal = mix(normal, vec3(0.5, 0.5, 1.0), far);

	ALBEDO = albedo * tint;
	NORMAL_MAP = normal;
	NORMAL_MAP_DEPTH = normal_strength;
	AO = arm.r;
	AO_LIGHT_AFFECT = 0.3;
	ROUGHNESS = roughness;
	METALLIC = 0.0;
	SPECULAR = 0.35;
}
