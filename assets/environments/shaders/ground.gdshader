// Regional ground surface for the terrain ribbons and road terrain margins.
//
// Four sourced PBR layers are blended by vertex colour and slope:
//   grass  - the base layer
//   COLOR.r - dry-grass weight (plains, urban edge)
//   COLOR.g - bare-dirt weight (arid ground, cut and fill faces)
//   slope   - rock weight where the surface normal leaves the horizontal
//
// UVs arrive in metres: U is lateral offset from the route, V is route
// distance wrapped to the anti-tiling period on the CPU so float32 UVs stay
// precise thousands of kilometres from the start line (see
// RegionalTerrainRibbon.UvWrapPeriodMeters).
//
// Tiling is broken by sampling each albedo at two scales and mixing them with
// a low-frequency hash so the repeat is not readable from the car, and the
// far field converges on each layer's mean colour so distant ground shows no
// texture moire at speed.
shader_type spatial;
render_mode cull_disabled, depth_draw_opaque;

uniform sampler2D grass_albedo : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D grass_normal : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D grass_arm : hint_default_white, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D dry_albedo : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D dry_normal : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D dry_arm : hint_default_white, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D dirt_albedo : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D dirt_normal : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D dirt_arm : hint_default_white, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D rock_albedo : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D rock_normal : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D rock_arm : hint_default_white, filter_linear_mipmap_anisotropic, repeat_enable;

uniform float tile_meters : hint_range(1.0, 40.0) = 7.0;
uniform float macro_tile_meters : hint_range(10.0, 400.0) = 53.0;
uniform float rock_slope_start : hint_range(0.0, 1.0) = 0.80;
uniform float rock_slope_full : hint_range(0.0, 1.0) = 0.55;
uniform float far_fade_start_meters = 350.0;
uniform float far_fade_end_meters = 2200.0;
uniform vec3 grass_tint : source_color = vec3(1.0);
uniform vec3 dry_tint : source_color = vec3(1.0);
uniform vec3 dirt_tint : source_color = vec3(1.0);
uniform vec3 rock_tint : source_color = vec3(1.0);
uniform float normal_strength : hint_range(0.0, 2.0) = 1.0;
// Meshes whose UVs are not already in metres (the 30 km backdrop plane) scale
// them here; weight_override.w > 0.5 replaces the vertex-colour layer weights.
uniform vec2 uv_scale_meters = vec2(1.0, 1.0);
uniform vec4 weight_override = vec4(0.0, 0.0, 0.0, 0.0);

varying vec2 uv_meters;
varying vec3 layer_weights;
varying float view_distance;
varying float slope_up;

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

vec4 sample_bombed(sampler2D tex, vec2 uv, float mix_weight) {
	vec2 macro_uv = mat2(vec2(0.83, 0.56), vec2(-0.56, 0.83)) * (uv * (tile_meters / macro_tile_meters));
	return mix(texture(tex, uv), texture(tex, macro_uv), mix_weight);
}

void vertex() {
	uv_meters = UV * uv_scale_meters;
	vec3 world_normal = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);
	// Ribbons are double-sided with mixed winding; the facing is irrelevant to slope.
	slope_up = abs(world_normal.y);
	layer_weights = weight_override.w > 0.5 ? weight_override.rgb : clamp(COLOR.rgb, 0.0, 1.0);
	view_distance = length((MODELVIEW_MATRIX * vec4(VERTEX, 1.0)).xyz);
}

void fragment() {
	vec2 uv = uv_meters / tile_meters;
	float bomb = value_noise(uv_meters / 41.0);
	bomb = smoothstep(0.35, 0.65, bomb);

	float rock_w = 1.0 - smoothstep(rock_slope_full, rock_slope_start, slope_up);
	rock_w = max(rock_w, layer_weights.b);
	float dirt_w = layer_weights.g * (1.0 - rock_w);
	float dry_w = layer_weights.r * (1.0 - rock_w) * (1.0 - dirt_w);
	float grass_w = max(0.0, 1.0 - rock_w - dirt_w - dry_w);

	vec3 albedo = vec3(0.0);
	vec3 normal = vec3(0.0);
	vec3 arm = vec3(0.0);
	if (grass_w > 0.001) {
		albedo += sample_bombed(grass_albedo, uv, bomb).rgb * grass_tint * grass_w;
		normal += texture(grass_normal, uv).rgb * grass_w;
		arm += texture(grass_arm, uv).rgb * grass_w;
	}
	if (dry_w > 0.001) {
		albedo += sample_bombed(dry_albedo, uv * 1.13, bomb).rgb * dry_tint * dry_w;
		normal += texture(dry_normal, uv * 1.13).rgb * dry_w;
		arm += texture(dry_arm, uv * 1.13).rgb * dry_w;
	}
	if (dirt_w > 0.001) {
		albedo += sample_bombed(dirt_albedo, uv * 0.91, bomb).rgb * dirt_tint * dirt_w;
		normal += texture(dirt_normal, uv * 0.91).rgb * dirt_w;
		arm += texture(dirt_arm, uv * 0.91).rgb * dirt_w;
	}
	if (rock_w > 0.001) {
		vec2 rock_uv = uv * 0.6;
		albedo += sample_bombed(rock_albedo, rock_uv, bomb).rgb * rock_tint * rock_w;
		normal += texture(rock_normal, rock_uv).rgb * rock_w;
		arm += texture(rock_arm, rock_uv).rgb * rock_w;
	}

	// Far field: converge on the mean colour of the same blend so distant
	// ground reads as surface, not as a shimmering repeat.
	float far = smoothstep(far_fade_start_meters, far_fade_end_meters, view_distance);
	if (far > 0.001) {
		vec3 mean = textureLod(grass_albedo, uv, 9.0).rgb * grass_tint * grass_w
			+ textureLod(dry_albedo, uv, 9.0).rgb * dry_tint * dry_w
			+ textureLod(dirt_albedo, uv, 9.0).rgb * dirt_tint * dirt_w
			+ textureLod(rock_albedo, uv, 9.0).rgb * rock_tint * rock_w;
		albedo = mix(albedo, mean, far);
		normal = mix(normal, vec3(0.5, 0.5, 1.0), far);
	}

	ALBEDO = albedo;
	NORMAL_MAP = normal;
	NORMAL_MAP_DEPTH = normal_strength;
	AO = arm.r;
	AO_LIGHT_AFFECT = 0.35;
	ROUGHNESS = clamp(arm.g, 0.35, 1.0);
	METALLIC = 0.0;
	SPECULAR = 0.3;
}
