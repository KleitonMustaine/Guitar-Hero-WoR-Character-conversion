#pragma once

#include "common.h"


typedef struct{
    unsigned char *data;
    long size;
}Skinfile;

typedef struct{
    size_t off;
    uint32_t checksum;
    uint32_t name;
    uint32_t template_id;
    uint32_t vs_count; //vertex shader count
    uint32_t vs_ptr;
    uint32_t ps_count; //pixel shader count
    uint32_t ps_ptr;
    uint32_t tex_count; //texture count
    uint32_t tex_ptr;
    uint32_t size;
    uint32_t flags;
    int32_t draw_order;
    uint32_t blend;
    uint32_t *textures;
}Material;

void dump_skin(const char *path);
void read_materials(const unsigned char *data, size_t core, size_t file_size);
void read_scene(const unsigned char *data, size_t scene_offset, size_t file_size);
