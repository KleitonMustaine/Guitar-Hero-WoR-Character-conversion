#include "common.h"
#include "geometry.h"
#include "skin.h"

int read_mesh_vertices(const unsigned char *data, size_t expected_offset, int off_vert_rel, int is_wor, Vertex **out_verts, int *out_count) {
    if (off_vert_rel < 0){
        *out_verts = NULL;
        *out_count = 0;
        return 0;
    }

    size_t cursor = expected_offset + off_vert_rel + 16;
    cursor += 4;

    uint32_t c1 = be32(data + cursor); 
    cursor += 4;
    uint32_t c2 = be32(data + cursor); 
    cursor += 4;
    uint32_t c3 = be32(data + cursor); 
    cursor += 4;

    uint32_t total_groups = c1 + c2 + c3;
    size_t scan_cursor = cursor;
    int total_vertices = 0;

    for(uint32_t g = 0; g < total_groups; g++){
        uint32_t n = be32(data + scan_cursor);
        scan_cursor += 16;
        size_t stride = is_wor ? 32 : 56;
        scan_cursor += n * stride;
        total_vertices += n;
    }

    if (total_vertices == 0) {
        *out_verts = NULL;
        *out_count = 0;
        return 0;
    }

    Vertex *verts = malloc(total_vertices * sizeof(Vertex));
    if (!verts) return -1;

    int v_idx = 0;

    for (uint32_t g = 0; g < total_groups; g++) {
        uint32_t n = be32(data + cursor);
        uint8_t bones[4] = {
            data[cursor + 4], data[cursor + 5],
            data[cursor + 6], data[cursor + 7]
        };
        cursor += 16;

    for (uint32_t i = 0; i < n; i++) {
            verts[v_idx].bones[0] = bones[0];
            verts[v_idx].bones[1] = bones[1];
            verts[v_idx].bones[2] = bones[2];
            verts[v_idx].bones[3] = bones[3];

        if (!is_wor) {

            verts[v_idx].x = be_float_local(data + cursor);
            verts[v_idx].y = be_float_local(data + cursor + 16);
            verts[v_idx].z = be_float_local(data + cursor + 32);

            verts[v_idx].nx = be_float_local(data + cursor + 4);
            verts[v_idx].ny = be_float_local(data + cursor + 20);
            verts[v_idx].nz = be_float_local(data + cursor + 36);

            verts[v_idx].weights[0] = 1.0f;
            verts[v_idx].weights[1] = 0.0f;
            verts[v_idx].weights[2] = 0.0f;
            cursor += 56;
            } else {

            verts[v_idx].x = be_float_local(data + cursor);
            verts[v_idx].y = be_float_local(data + cursor + 4);
            verts[v_idx].z = be_float_local(data + cursor + 8);

            uint16_t b_val = be16(data + cursor + 12);
            uint16_t a_val = be16(data + cursor + 14);
            float b = b_val / 65535.0f;
            float a = a_val / 65535.0f;
            float d = 1.0f - (a + b);

            verts[v_idx].weights[0] = a + d;
            verts[v_idx].weights[1] = b + d;
            verts[v_idx].weights[2] = d;

            uint32_t packed_nrm = be32(data + cursor + 16);
            unpack_normal_func(packed_nrm, &verts[v_idx].nx, &verts[v_idx].ny, &verts[v_idx].nz);

            cursor += 32;
        }
        v_idx++;
        }
    }

    *out_verts = verts;
    *out_count = total_vertices;
    return 0;
}

int read_mesh_faces(const unsigned char *data, size_t off_face, uint16_t face_count, uint32_t face_type, Triangle **out_tris, int *out_tri_count){
    size_t cursor = off_face + 12;
    cursor += 4;
    cursor += 12;
    cursor += 4;

    uint16_t *raw_indices = malloc(face_count * sizeof(uint16_t));
    if (!raw_indices) return -1;

    for (uint16_t i = 0; i < face_count; i++) {
        raw_indices[i] = be16(data + cursor);
        cursor += 2;
    }

    Triangle *tris = malloc(face_count * 3 * sizeof(Triangle));
    if (!tris) {
        free(raw_indices);
        return -1;
    }

    int tri_count = 0;

    if (face_type == 4) {
        // Triangle List
        for (int i = 0; i <= (int)face_count - 3; i += 3) {
            tris[tri_count].v[0] = raw_indices[i];
            tris[tri_count].v[1] = raw_indices[i+1];
            tris[tri_count].v[2] = raw_indices[i+2];
            tri_count++;
        }
    } else {
        uint16_t strip[4096];
        int strip_len = 0;

        for (int i = 0; i <= face_count; i++) {
            uint16_t val = (i < face_count) ? raw_indices[i] : 0x7FFF;

            if (val == 0x7FFF) {
                if (strip_len >= 3) {
                    for (int f = 2; f < strip_len; f++) {
                        uint16_t i1 = strip[f - 2];
                        uint16_t i2 = strip[f - 1];
                        uint16_t i3 = strip[f];

                        if (i1 != i2 && i2 != i3 && i1 != i3) {
                            if (f % 2 == 0) {
                                tris[tri_count].v[0] = i1;
                                tris[tri_count].v[1] = i2;
                                tris[tri_count].v[2] = i3;
                            } else {
                                tris[tri_count].v[0] = i1;
                                tris[tri_count].v[1] = i3;
                                tris[tri_count].v[2] = i2;
                            }
                            tri_count++;
                        }
                    }
                }
                strip_len = 0;
            } else {
                if (strip_len < 4096) {
                    strip[strip_len++] = val;
                }
            }
        }
    }

    free(raw_indices);
    *out_tris = tris;
    *out_tri_count = tri_count;
    return 0;

}
