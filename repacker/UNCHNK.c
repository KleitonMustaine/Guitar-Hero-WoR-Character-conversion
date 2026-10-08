#include "common.h"
#include "chnk.h"
#include "archive.h"

int decompress_chnk(const char *input_path, const char *output_path){
    FILE *file = fopen (input_path, "rb");
    if(!file){
        printf("Failed to open the archive\n");
        return -1;
    }

    FILE *output = fopen(output_path, "wb");
    if(!output){
        printf("Failed to write the output archive\n");
        fclose(file);
        return -1;
    }

    CHNKHeader header;
    unsigned long int current_chnk_pos = 0;
    unsigned int chnk_count = 0;
    int result = -1;

    while(1){
        
        fseek(file, current_chnk_pos, SEEK_SET);
        if (fread(&header, 1, sizeof(CHNKHeader),file) != sizeof(CHNKHeader)){
            fprintf(stderr, "Failed to read the header at the offset 0x%lX\n", current_chnk_pos);
            break;
        }
        header_from_file(&header);
        if(memcmp(header.signature, "CHNK", 4) != 0){
            fprintf(stderr, "Invalid Signature at the 0x%lX\n", current_chnk_pos);
            break;
        }

        printf("Processing Chunk #%d | Compressed: %u bytes | Decompressed: %u bytes | Address: 0x%X\n", chnk_count++, header.compressed_size, header.decompressed_size, header.output_offset);

        unsigned char *comp_buf = (unsigned char *)malloc(header.compressed_size);
        unsigned char *decomp_buf = (unsigned char *)malloc(header.decompressed_size);

        if (!comp_buf || !decomp_buf){
            fprintf(stderr, "Memory allocation error for the chunck #%d\n", chnk_count);
            free(comp_buf);
            free(decomp_buf);
            break;
        }

        fseek(file, current_chnk_pos + header.header_size, SEEK_SET);
        if (fread(comp_buf, 1, header.compressed_size, file) != header.compressed_size) {
            fprintf(stderr, "Error at reading Chunk data\n");
            free(comp_buf); free(decomp_buf);
            break;
        }

        mz_ulong addr_len = header.decompressed_size;

        size_t written = tinfl_decompress_mem_to_mem(decomp_buf, header.decompressed_size, comp_buf, header.compressed_size, 0);

        if(written == TINFL_DECOMPRESS_MEM_TO_MEM_FAILED || written != header.decompressed_size){
            fprintf(stderr, "Failed to decompress. Error code: %zu\n", written);
            free(comp_buf);
            free(decomp_buf);
            break;
        }
        fseek(output, header.output_offset, SEEK_SET);
        fwrite(decomp_buf, 1, addr_len, output);

        free(comp_buf);
        free(decomp_buf);

        if(header.next_chunk_dist == 0xFFFFFFFF){
            printf("End of the archive reached\n");
            result = 0;
            break;
        }

        current_chnk_pos += header.next_chunk_dist;

    }
    fclose(file);
    fclose(output);

    return result;
}

int recompress_chnk(const char *input_path, const char *output_path){
    long size = 0;
    size_t blob_size = 0;
    uint32_t chunks, first;

    unsigned char *data = load_file(input_path, &size);
    if(!data || size <= 0){
        fprintf(stderr, "Failed to read the input file\n");
        free(data);
        return -1;
    }

    unsigned char *blob = chnk_comp(data, size, &blob_size, &chunks, &first);
    free(data);
    if(!blob){
        fprintf(stderr, "Compression failed\n");
        return -1;
    }

    FILE *out = fopen(output_path, "wb");
    int ok = out && fwrite(blob, 1, blob_size, out) == blob_size;
    if(out){
        fclose(out);
        free(blob);
    }if(!ok){
        fprintf(stderr, "Failed to write %s\n", output_path);
    }
    if(ok){
        return 0;
    }else {
        return -1;
    }
}

static void usage(const char *prog, char mode){
    switch(mode){
    case 'd':
        fprintf(stderr, "use: %s d <input.xen> <output> decompress a CHNK file\n", prog);
        break;
    case 'c':
        fprintf(stderr, "use: %s c <input> <output.xen> compress a file to CHNK\n", prog);
        break;
    case 'l':
        fprintf(stderr, "use: %s l <pak> list an archive index\n", prog);
        break;
    case 'x':
        fprintf(stderr, "use: %s x <pak> <pab> <crc|name> <out> extract a file from an archive\n", prog);
        break;
    case 'r':
        fprintf(stderr, "use: %s r <pak> <pab> <crc|name> <file> replace a file in an archive\n", prog);
        break;
    default:
        fprintf(stderr, "Usage: %s <mode> [options]\n\n", prog);
        fprintf(stderr, "Modes:\n");
        fprintf(stderr, "  d <input.xen> <output>              Decompress a CHNK file\n");
        fprintf(stderr, "  c <input> <output.xen>              Compress a file to CHNK\n");
        fprintf(stderr, "  l <pak>                             List an archive index\n");
        fprintf(stderr, "  x <pak> <pab> <crc|name> <out>      Extract a file from an archive\n");
        fprintf(stderr, "  r <pak> <pab> <crc|name> <file>     Replace a file in an archive\n");
        break;
    }
}

int list_index(const char *pak_path){
    long size;
    unsigned char *buffer = load_file(pak_path, &size);
    if(!buffer){
        fprintf(stderr, "Failed to read %s\n", pak_path);
        return -1;
    }

    unsigned int count = 0;
    for(long off = 0; off + 32 <= size; off += 32){ 
        unsigned char *e = buffer + off;                  

        uint32_t type   = be32(e + 0);                  
        uint32_t offset = be32(e + 4);
        uint32_t usize  = be32(e + 12);
        uint32_t crc    = be32(e + 16);

        if(type == 0x2CB3EF3B){
            printf(".last  pab end = 0x%08X\n", offset);
            break;
        }

        const char *name = key_name(crc);
        printf("%08X %08X %8u %s\n", crc, offset, usize, name ? name : "?");
        count++;
    }

    printf("%u entries\n", count);
    free(buffer);                                       
    return 0;
}

int extract_file(const char *pak_path, const char *pab_path,
                 const char *what, const char *out_path){
    int result = -1;
    unsigned char *idx = NULL, *comp = NULL, *data = NULL;
    FILE *pab = NULL, *out = NULL;
    const unsigned char *e;
    long idx_size = 0;
    uint32_t crc, offset, csize, usize;

    if(resolve_crc(what, &crc) != 0){
        fprintf(stderr, "Unknown file: %s\n", what);
        goto cleanup;
    }

    idx = load_file(pak_path, &idx_size);
    if(!idx){
        fprintf(stderr, "Failed to read %s\n", pak_path);
        goto cleanup;
    }

    e = find_entry(idx, idx_size, crc);
    if(!e){
        fprintf(stderr, "%08X is not in this archive\n", crc);
        goto cleanup;
    }
    offset = be32(e + 4);
    csize  = be32(e + 8);
    usize  = be32(e + 12);
    printf("%08X  pab 0x%08X  compressed %u  decompressed %u\n", crc, offset, csize, usize);

    pab = fopen(pab_path, "rb");
    if(!pab){
        fprintf(stderr, "Failed to open %s\n", pab_path);
        goto cleanup;
    }

    comp = malloc(csize ? csize : 1);
    data = malloc(usize ? usize : 1);
    if(!comp || !data){
        fprintf(stderr, "Out of memory\n");
        goto cleanup;
    }

    if(fseek(pab, (long)offset, SEEK_SET) != 0 || fread(comp, 1, csize, pab) != csize){
        fprintf(stderr, "Failed to read the data from the pab\n");
        goto cleanup;
    }

    if(chnk_decomp(comp, csize, data, usize) != 0)
        goto cleanup;

    out = fopen(out_path, "wb");
    if(!out || fwrite(data, 1, usize, out) != usize){
        fprintf(stderr, "Failed to write %s\n", out_path);
        goto cleanup;
    }
    result = 0;

cleanup:
    free(data);
    free(comp);
    free(idx);
    if(pab) fclose(pab);
    if(out) fclose(out);
    return result;
}

int replace_file(const char *pak_path, const char *pab_path,const char *what, const char *in_path){
    int result = -1;
    unsigned char *idx = NULL, *data = NULL, *blob = NULL, *e, *last;
    FILE *pab = NULL, *pak = NULL;
    long idx_size = 0, data_size = 0;
    size_t blob_size = 0;
    uint32_t crc, chunks, first, offset, old_csize;

    if(resolve_crc(what, &crc) != 0){
        fprintf(stderr, "Unknown file: %s\n", what);
        goto cleanup;
    }

    data = load_file(in_path, &data_size);
    if(!data || data_size <= 0){
        fprintf(stderr, "Failed to read %s\n", in_path);
        goto cleanup;
    }

    idx = load_file(pak_path, &idx_size);
    if(!idx){
        fprintf(stderr, "Failed to read %s\n", pak_path);
        goto cleanup;
    }

    e = (unsigned char *)find_entry(idx, idx_size, crc);
    last = find_last(idx, idx_size);
    if(!e || !last){
        fprintf(stderr, "%08X is not in this archive\n", crc);
        goto cleanup;
    }

    blob = chnk_comp(data, data_size, &blob_size, &chunks, &first);
    if(!blob){
        fprintf(stderr, "Compression failed\n");
        goto cleanup;
    }

    offset    = be32(e + 4);
    old_csize = be32(e + 8);

    pab = fopen(pab_path, "r+b");   
    if(!pab){
        fprintf(stderr, "Failed to open %s\n", pab_path);
        goto cleanup;
    }

    if(blob_size <= old_csize){
        if(fseek(pab, (long)offset, SEEK_SET) != 0 || fwrite(blob, 1, blob_size, pab) != blob_size){
            fprintf(stderr, "Failed to write the pab\n");
            goto cleanup;
        }
        for(size_t j = blob_size; j < old_csize; j++)   // clear what is left of the old data
            fputc(0, pab);
        printf("%08X written in place at 0x%08X\n", crc, offset);
    } else {
        offset = be32(last + 4);        // .last points at the end of the pab data
        if(fseek(pab, (long)offset, SEEK_SET) != 0 || fwrite(blob, 1, blob_size, pab) != blob_size){
            fprintf(stderr, "Failed to write the pab\n");
            goto cleanup;
        }
        put_be32(last + 4, offset + (uint32_t)blob_size);
        printf("%08X appended at 0x%08X\n", crc, offset);
    }

    int closed = fclose(pab);
    pab = NULL;
    if(closed != 0){
        fprintf(stderr, "Failed to finish writing the pab\n");
        goto cleanup;
    }

    put_be32(e + 4,  offset);
    put_be32(e + 8,  (uint32_t)blob_size);
    put_be32(e + 12, (uint32_t)data_size);
    put_be32(e + 20, chunks);
    put_be32(e + 24, first);

    pak = fopen(pak_path, "wb");
    if(!pak || fwrite(idx, 1, idx_size, pak) != (size_t)idx_size){
        fprintf(stderr, "Failed to write %s\n", pak_path);
        goto cleanup;
    }
    printf("compressed %zu  decompressed %ld  chunks %u\n", blob_size, data_size, chunks);
    result = 0;

cleanup:
    free(blob);
    free(data);
    free(idx);
    if(pab) fclose(pab);
    if(pak) fclose(pak);
    return result;
}

int main(int argc, char **argv) {
    if (argc < 2 || argv[1][0] == '\0' || argv[1][1] != '\0') {
        usage(argv[0], 0);
        return 1;
    }
    const char *keys_file = getenv("WOR_KEYS");
    if (keys_file == NULL) {
        keys_file = "ghwor_keys.txt";
    }

    load_keys(keys_file);

    char mode = argv[1][0];
    int result = -1;

    if (mode == 'd' && argc == 4) {
        result = decompress_chnk(argv[2], argv[3]);
    } else if (mode == 'c' && argc == 4) {
        result = recompress_chnk(argv[2], argv[3]);
    } else if (mode == 'l' && argc == 3) {
        result = list_index(argv[2]);
    } else if (mode == 'x' && argc == 6) {
        result = extract_file(argv[2], argv[3], argv[4], argv[5]);
    } else if (mode == 'r' && argc == 6) {
        result = replace_file(argv[2], argv[3], argv[4], argv[5]);
    }
    if (result == -1) {
        usage(argv[0], mode);
        return 1;
    }

    return (result != 0);
}
