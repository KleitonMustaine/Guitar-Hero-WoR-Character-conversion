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
            expected_offset += 8 + pad;
        }else{
            expected_offset = (expected_offset + 127) & ~127;
        }
    }
    printf("Scene starts at offset 0x%zX\n", expected_offset);
    read_scene(data, expected_offset, file_size);
}

void read_scene(const unsigned char *data, size_t expected_offset, size_t file_size) {
    if (expected_offset + 0x80 > file_size) {
        fprintf(stderr, "Error: File too small for scene header.\n");
        return;
    }
    // Read scene header
    uint16_t unk_a = be16(data + expected_offset + 0x40);
    uint16_t unk_b = be16(data + expected_offset + 0x42);

    // Read counts and offsets
    uint32_t smesh_count = be32(data + expected_offset + 0x4C);
    uint32_t sector_count = be32(data + expected_offset + 0x64);
    
    uint32_t rel_sector = be32(data + expected_offset + 0x68);
    uint32_t rel_cgeom  = be32(data + expected_offset + 0x6C);
    uint32_t rel_smesh  = be32(data + expected_offset + 0x74);

    size_t off_sector = expected_offset + rel_sector;
    size_t off_cgeom  = expected_offset + rel_cgeom;
    size_t off_smesh  = expected_offset + rel_smesh;

    printf(" Cena: unk_a=%d, unk_b=%d, setores=%d, mesh_smesh=%d\n", unk_a, unk_b, sector_count, smesh_count);
    printf("   -> off_sector = 0x%zX\n", off_sector);
    printf("   -> off_cgeom  = 0x%zX\n", off_cgeom);
    printf("   -> off_smesh  = 0x%zX\n", off_smesh);

    read_sector(data, off_sector, off_cgeom, sector_count, file_size);

    read_smesh(data, off_smesh, off_cgeom, smesh_count, file_size);
}

void read_sector(const unsigned char *data, size_t off_sector, size_t off_cgeom, uint32_t sector_count, size_t file_size) {
    printf("Reading Sectors %d sector \n", sector_count);

    size_t sec_curr = off_sector;
    size_t cgeom_curr = off_cgeom;

    for(uint32_t i = 0; i < sector_count; i++) {
        if (sec_curr + 0x50 > file_size) {
            fprintf(stderr, "Error: File too small for sector %d header.\n", i);
            break;
        }

        Sector s;
        s.checksum = be32(data + sec_curr);
        s.flags = be32(data + sec_curr + 4);
        s.first_mesh = be32(data + sec_curr + 8);
        s.mesh_count = (int32_t)be32(data + sec_curr + 12);

        printf("-> Sector [%d] checksum=0x%08X, flags=0x%08X, first_mesh=%d, mesh_count=%d\n", i, s.checksum, s.flags, s.first_mesh, s.mesh_count);

        // Move to the next sector
        sec_curr += 0x80;
    }
}

int read_smesh(const unsigned char *data, size_t off_smesh, size_t off_cgeom, uint32_t smesh_count, size_t file_size) {
    printf("reading Mesh (Total: %d) ---\n", smesh_count);

    for (uint32_t i = 0; i < smesh_count; i++) {

        size_t smesh_off = off_smesh + (i * 112);

        if (smesh_off + 112 > file_size) {
            fprintf(stderr, "Error: End of file while reading mesh %d\n", i);
            return -1;
        }

        uint32_t flags       = be32(data + smesh_off + 0x20);
        uint32_t material    = be32(data + smesh_off + 0x38);
        uint16_t face_count  = be16(data + smesh_off + 0x50);
        uint16_t vertex_count = be16(data + smesh_off + 0x52);
        uint32_t face_type   = be32(data + smesh_off + 0x6C);

        printf("-> MESH [%d] verts=%d, faces=%d, face_type=%d, material=0x%08X\n", i, vertex_count, face_count, face_type, material);
    }

    return 0;
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
