#include "common.h"
#include "skin.h"

void read_materials(const unsigned char *data, size_t core, size_t file_size){

    if(core + 12 > file_size){
        fprintf(stderr, "Skin file too small for materials: core=0x%zX, size=%zu\n", core, file_size);
        return;
    }

    unsigned char mat_version = data[core];
    uint16_t count = be16(data + core + 2);
    uint32_t matlist_size = be32(data + core + 4);
    uint32_t rel = be32(data + core + 8);

    printf(" Materiais: v%d, count=%d, matlist_size=0x%X, rel=0x%X\n", mat_version, count, matlist_size, rel);

    size_t mat_offset = core + rel;

    for(uint16_t i = 0; i < count; i++){
        if(mat_offset + 0x74 > file_size){
            fprintf(stderr, "error at reading the material %d\n", i);
            break;
        }
    Material m;

    m.off = mat_offset;
    m.checksum = be32(data + mat_offset);
    m.name = be32(data + mat_offset + 4);

    //jumps to offset 0x70 inside of the materal structure to grab the pointer to the texture list
    size_t ptrs_offset = mat_offset + 0x70;
        m.template_id = be32(data + ptrs_offset);
        m.vs_count    = be32(data + ptrs_offset + 8);
        m.vs_ptr      = be32(data + ptrs_offset + 12);
        m.ps_count    = be32(data + ptrs_offset + 16);
        m.ps_ptr      = be32(data + ptrs_offset + 20);
        m.tex_count   = be32(data + ptrs_offset + 24);
        m.tex_ptr     = be32(data + ptrs_offset + 28);
        m.size        = be32(data + ptrs_offset + 40);
        m.flags       = be32(data + ptrs_offset + 48);

        printf("   -> MAT [%d] checksum=0x%08X, template=0x%08X, tex_count=%d, size=0x%X\n", i, m.checksum, m.template_id, m.tex_count, m.size);

        mat_offset += (m.size + 15) & ~15; //align to 16 bytes
    }

    size_t expected_offset = core + matlist_size;

    if(expected_offset + 8 <= file_size){
        uint32_t magic = be32(data + expected_offset);
        if(magic == 0xBABEFACE){
            uint32_t pad = be32(data + expected_offset + 4);
            expected_offset += 8 + pad - + 4+4;
        }else{
            expected_offset = (expected_offset + 127) & ~127;
        }
    }
    printf("Scene starts at offset 0x%zX\n", expected_offset);
}

void dump_skin(const char *path){
    long size = 0;
    unsigned char *data = load_file(path, &size);
    if(!data){
        fprintf(stderr, "Failed to load skin file: %s\n", path);
        return;
    }
    if(size < 0x21){
        fprintf(stderr, "Skin file too small: %s\n", path);
        free(data);
        return;
    }

    uint32_t dq_offset = be32(data);
    size_t core = 0;
    const char *format;

    if(data[0x20] == 0){
        fprintf(stderr, "Skin file is WoR format: %s\n", path);
        core = 0x80;
        format = "WoR";
    } else {
        fprintf(stderr, "Skin file is not WoR format: %s\n", path);
        core = 0x20;
        format = "WT";
    }

    printf("%s: %s, core=0x%zX, size=%ld bytes, dq_off=0x%X\n", path, format, core, size, dq_offset);

    read_materials(data, core, size);

    free(data);
}
