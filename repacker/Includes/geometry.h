#pragma once

#include <stdint.h>

typedef struct {
    float x, y, z;
    float nx, ny, nz;
    float weights[3];
    uint8_t bones[4];
} Vertex;

typedef struct {
    uint16_t v[3];
} Triangle;

// Funções públicas expostas para o skin_reader.c
int read_mesh_vertices(const unsigned char *data, size_t scene_offset, int off_vert_rel, int is_wor, Vertex **out_verts, int *out_count);
int read_mesh_faces(const unsigned char *data, size_t off_face, uint16_t face_count, uint32_t face_type, Triangle **out_tris, int *out_tri_count);
void export_to_obj(const char *filename, const unsigned char *data, size_t scene_offset, void *meshes, int mesh_count, int is_wor);
