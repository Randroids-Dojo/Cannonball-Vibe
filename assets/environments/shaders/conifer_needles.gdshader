// Needle-cluster cards for the project-original conifer.
//
// Alpha-scissored, double-sided, with a translucency term so backlit crowns
// glow at dawn and dusk the way a real ponderosa does. Vertex colour alpha
// carries a per-card sway weight baked by the generator (0 at the trunk, 1 at
// the tips) so the crown moves without the trunk shearing.
shader_type spatial;
render_mode cull_disabled, depth_draw_opaque, depth_prepass_alpha;

#include "conifer_lod_fade.gdshaderinc"

uniform sampler2D needle_albedo : source_color, filter_linear_mipmap_anisotropic;
uniform sampler2D needle_normal : hint_normal, filter_linear_mipmap;
uniform float alpha_scissor : hint_range(0.0, 1.0) = 0.42;
uniform vec3 tint : source_color = vec3(1.0);
uniform float translucency : hint_range(0.0, 1.0) = 0.35;
uniform float sway_strength : hint_range(0.0, 0.5) = 0.045;
uniform float sway_speed : hint_range(0.0, 4.0) = 0.9;
uniform float roughness : hint_range(0.0, 1.0) = 0.86;

void vertex() {
	float weight = COLOR.a;
	vec3 world = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	float phase = world.x * 0.15 + world.z * 0.11;
	float gust = sin(TIME * sway_speed + phase) * 0.6 + sin(TIME * sway_speed * 2.3 + phase * 1.7) * 0.4;
	VERTEX.x += gust * sway_strength * weight;
	VERTEX.z += gust * sway_strength * 0.6 * weight;
}

void fragment() {
	// ALPHA arrives with the native visibility fade. Preserve it as coverage
	// before the needle texture supplies its independent cutout mask.
	if (ALPHA <= tree_lod_threshold(FRAGCOORD.xy)) {
		discard;
	}
	vec4 sample = texture(needle_albedo, UV);
	ALPHA = sample.a;
	ALPHA_SCISSOR_THRESHOLD = alpha_scissor;
	ALBEDO = sample.rgb * tint * mix(0.9, 1.0, COLOR.r);
	NORMAL_MAP = texture(needle_normal, UV).rgb;
	NORMAL_MAP_DEPTH = 0.6;
	ROUGHNESS = roughness;
	METALLIC = 0.0;
	SPECULAR = 0.2;
	BACKLIGHT = vec3(translucency) * sample.rgb;
	AO = mix(0.55, 1.0, COLOR.g);
	AO_LIGHT_AFFECT = 0.3;
}
