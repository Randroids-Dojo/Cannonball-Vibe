// Hero GT metallic car paint: a dielectric base coat with metallic flakes
// under a clear coat. The flake layer is a hashed per-cell normal jitter so no
// texture is needed; the clear coat uses Godot's built-in clearcoat term. The
// base colour darkens at grazing angles (a "flop") and picks up an edge tint,
// which is what separates paint from plastic in motion.
shader_type spatial;
render_mode cull_back, depth_draw_opaque;

uniform vec4 base_color : source_color = vec4(0.04, 0.125, 0.27, 1.0);
uniform vec3 edge_tint : source_color = vec3(0.02, 0.05, 0.12);
uniform float flop : hint_range(0.0, 1.0) = 0.55;
uniform float metallic : hint_range(0.0, 1.0) = 0.22;
uniform float roughness : hint_range(0.0, 1.0) = 0.36;
uniform float clearcoat : hint_range(0.0, 1.0) = 1.0;
uniform float clearcoat_roughness : hint_range(0.01, 1.0) = 0.04;
uniform float flake_scale = 900.0;
uniform float flake_strength : hint_range(0.0, 1.0) = 0.35;
uniform float flake_roughness : hint_range(0.0, 1.0) = 0.22;
uniform sampler2D orange_peel : hint_normal, filter_linear_mipmap, repeat_enable;
uniform float orange_peel_scale = 3.0;
uniform float orange_peel_strength : hint_range(0.0, 1.0) = 0.2;

varying vec3 object_position;

vec3 hash33(vec3 p) {
	p = fract(p * vec3(0.1031, 0.1030, 0.0973));
	p += dot(p, p.yxz + 33.33);
	return fract((p.xxy + p.yxx) * p.zyx);
}

void vertex() {
	object_position = VERTEX;
}

void fragment() {
	// Flakes: one random tilt per cell in object space so they stay put on
	// the body and sparkle as the view moves.
	vec3 cell = floor(object_position * flake_scale);
	vec3 jitter = hash33(cell) * 2.0 - 1.0;
	// Flakes smaller than a pixel would alias into grain, so their strength
	// fades with the screen footprint of one cell: full up close, gone at
	// chase distance where real flake reads as a uniform sheen.
	float footprint = length(fwidth(object_position)) * flake_scale;
	float visible_flake = flake_strength * clamp(1.0 - footprint * 0.6, 0.0, 1.0);
	vec3 flake_normal = normalize(vec3(jitter.xy * visible_flake, 1.0));
	// Orange peel from the sourced clear-coat normal, object-space planar.
	vec2 peel_uv = (abs(NORMAL.y) > 0.6 ? object_position.xz : (abs(NORMAL.x) > abs(NORMAL.z) ? object_position.zy : object_position.xy)) * orange_peel_scale;
	vec3 peel = texture(orange_peel, peel_uv).xyz * 2.0 - 1.0;
	vec3 detail = normalize(vec3(peel.xy * orange_peel_strength + flake_normal.xy, 1.0));
	NORMAL_MAP = detail * 0.5 + 0.5;
	NORMAL_MAP_DEPTH = 1.0;
	// Flop: darker and tinted toward the edge colour at grazing angles.
	float facing = clamp(dot(normalize(NORMAL), normalize(VIEW)), 0.0, 1.0);
	float fresnel = pow(1.0 - facing, 3.0);
	vec3 color = mix(base_color.rgb, base_color.rgb * (1.0 - flop) + edge_tint, fresnel);
	ALBEDO = color;
	METALLIC = metallic;
	ROUGHNESS = mix(roughness, flake_roughness, flake_strength * 0.5);
	SPECULAR = 0.55;
	CLEARCOAT = clearcoat;
	CLEARCOAT_ROUGHNESS = clearcoat_roughness;
}
