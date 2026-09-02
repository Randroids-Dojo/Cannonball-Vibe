// Concrete barriers, bridge structure and other instanced highway furniture.
//
// The kit instances unit meshes and stretches them per segment, so mesh UVs
// would smear. Texturing is triplanar in *scaled* object space: the instance
// scale is recovered from MODEL_MATRIX, which makes one texture metre equal
// one world metre whatever the stretch. INSTANCE_CUSTOM.x carries the route
// distance at the segment start (wrapped on the CPU), so the pattern runs
// continuously from one segment into the next along the road. Being object
// space, it is unaffected by local-origin rebases.
shader_type spatial;
render_mode cull_back, depth_draw_opaque;

uniform sampler2D albedo_map : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D normal_map : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D arm_map : hint_default_white, filter_linear_mipmap_anisotropic, repeat_enable;

uniform float tile_meters : hint_range(0.25, 20.0) = 2.4;
uniform vec3 tint : source_color = vec3(1.0);
uniform float roughness_bias : hint_range(-0.5, 0.5) = 0.0;
uniform float weathering : hint_range(0.0, 1.0) = 0.35;
uniform float normal_strength : hint_range(0.0, 2.0) = 0.8;

varying vec3 metres;
varying vec3 object_normal;
varying float height_fraction;

void vertex() {
	vec3 scale = vec3(
		length(MODEL_MATRIX[0].xyz),
		length(MODEL_MATRIX[1].xyz),
		length(MODEL_MATRIX[2].xyz));
	metres = VERTEX * scale;
	metres.z += INSTANCE_CUSTOM.x;
	object_normal = normalize(NORMAL);
	height_fraction = VERTEX.y + 0.5;
}

vec4 triplanar(sampler2D tex, vec3 p, vec3 blend) {
	return texture(tex, p.yz) * blend.x + texture(tex, p.xz) * blend.y + texture(tex, p.xy) * blend.z;
}

void fragment() {
	vec3 blend = pow(abs(object_normal), vec3(6.0));
	blend /= (blend.x + blend.y + blend.z);
	vec3 p = metres / tile_meters;
	vec3 albedo = triplanar(albedo_map, p, blend).rgb;
	vec3 normal = triplanar(normal_map, p, blend).rgb;
	vec3 arm = triplanar(arm_map, p, blend).rgb;
	// Road grime collects low on a barrier and streaks down from its cap.
	float grime = weathering * (1.0 - smoothstep(0.0, 0.55, height_fraction));
	albedo *= 1.0 - grime * 0.35;
	ALBEDO = albedo * tint;
	NORMAL_MAP = normal;
	NORMAL_MAP_DEPTH = normal_strength;
	AO = arm.r;
	AO_LIGHT_AFFECT = 0.3;
	ROUGHNESS = clamp(arm.g + roughness_bias + grime * 0.15, 0.2, 1.0);
	METALLIC = 0.0;
	SPECULAR = 0.3;
}
