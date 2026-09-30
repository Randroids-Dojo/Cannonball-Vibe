shader_type sky;

// Original analytical studio softboxes; no external image dependencies.
uniform float panel_energy = 2.4;
uniform float base_energy = 0.2;
uniform float daylight = 0.0;
uniform float horizon_fill = 0.0;

float softbox(vec3 ray, vec3 normal, vec2 size) {
    vec3 right = normalize(cross(normal, vec3(0.0, 0.0, 1.0)));
    vec3 up = cross(right, normal);
    float facing = dot(ray, normal);
    vec2 p = abs(vec2(dot(ray, right), dot(ray, up)) / max(facing, 0.001));
    vec2 box = 1.0 - smoothstep(size, size + vec2(0.025), p);
    return box.x * box.y * step(0.0, facing);
}

void sky() {
    vec3 d = normalize(EYEDIR);
    float horizon = pow(1.0 - abs(d.y), 3.0);
    vec3 neutral = mix(vec3(0.12, 0.14, 0.18), vec3(0.48, 0.49, 0.52), horizon);
    vec3 outdoors = mix(vec3(0.23, 0.42, 0.70), vec3(0.82, 0.86, 0.9), horizon);
    COLOR = mix(neutral, outdoors, daylight) * base_energy;
    // Keep lighting cards in reflections without placing a white rectangle
    // behind the car when the inspection camera looks up from below it.
    if (AT_CUBEMAP_PASS) {
        COLOR += vec3(0.60, 0.72, 1.0) * horizon_fill * pow(1.0 - abs(d.y), 2.0);
        float panels = softbox(d, normalize(vec3(-0.65, 1.0, -0.2)), vec2(0.19, 0.82));
        panels += softbox(d, normalize(vec3(0.85, 0.65, 0.45)), vec2(0.14, 0.78)) * 0.8;
        panels += softbox(d, normalize(vec3(-0.2, 0.65, 1.0)), vec2(0.65, 0.12)) * 0.5;
        COLOR += vec3(panels * panel_energy);
    }
}
