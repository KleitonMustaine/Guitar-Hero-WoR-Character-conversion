#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include "miniz.h"

static int cmp_key(const void *a, const void *b);

#pragma pack(push, 1)

typedef struct 
{
    char     signature[4];       // 0x00: "CHNK"
    uint32_t header_size;        // 0x04: always 0x80
    uint32_t compressed_size;    // 0x08: size of the compressed data
    uint32_t next_chunk_dist;    // 0x0C: distance to the nearest chunk (0xFFFFFFFF = fim)
    uint32_t next_slot_size;     // 0x10: slot size (ignored)
    uint32_t decompressed_size;  // 0x14: original size of the data
    uint32_t output_offset;      // 0x18: Offset of the output data
    uint8_t  reserved[100];      // 0x1C to 0x80: zero fill or reserved
}CHNKHeader;

#pragma pack(pop)

typedef struct
{
    uint32_t crc;
    char *name;
}KeyName;

static KeyName *g_keys = NULL;
static size_t g_keys_count = 0;
static size_t g_keys_cap = 0;

//converts little endian to big endian
#define swapEndian32(x) __builtin_bswap32(x)

//reads 4 bytes at p as a big endian number
static uint32_t be32(const unsigned char *p){
    return (uint32_t)p[0] << 24 |
           (uint32_t)p[1] << 16 |
           (uint32_t)p[2] << 8  |
           (uint32_t)p[3];
}

//converts all of these to big endian
static void header_from_file(CHNKHeader *h){
    h->header_size = swapEndian32(h->header_size);
    h->compressed_size = swapEndian32(h->compressed_size);
    h->next_chunk_dist = swapEndian32(h->next_chunk_dist);
    h->next_slot_size = swapEndian32(h->next_slot_size);
    h->decompressed_size = swapEndian32(h->decompressed_size);
    h->output_offset = swapEndian32(h->output_offset);
}

static int cmp_key(const void *a, const void *b)
{
    uint32_t x = ((const KeyName *)a)->crc;
    uint32_t y = ((const KeyName *)b)->crc;
    return (x > y) - (x < y);
}

static const char *key_name(uint32_t crc)
{
    KeyName k = { crc, NULL };
    KeyName *r = bsearch(&k, g_keys, g_keys_count, sizeof *g_keys, cmp_key);
    return r ? r->name : NULL;
}

static void put_be32(unsigned char *p, uint32_t v){
    p[0] = v >> 24;
    p[1] = v >> 16;
    p[2] = v >> 8;
    p[3] = v;
}

static uint32_t slot_of(size_t csize){
    return (uint32_t)((0x80 + csize + 0x7FF) & ~(size_t)0x7FF);
}

static unsigned char *find_last(unsigned char *idx, long size){
    for(long off = 0; off + 32 <= size; off += 32)
        if(be32(idx + off) == 0x2CB3EF3B)
            return idx + off;
    return NULL;
}

int load_keys(const char *path){
    FILE *file = fopen(path, "r");
    if(!file){
        fprintf(stderr, "Failed to open the list\n");
        return -1;
    }

    unsigned int crc;
    char name[1024];
    char lines[1024];

    while(fgets(lines, sizeof lines, file)){
        if(sscanf(lines, "%x %1023[^\n]", &crc, name) != 2){
            continue;
        }
        if (g_keys_count == g_keys_cap) {
            size_t new_cap = g_keys_cap ? g_keys_cap * 2 : 1024;
            KeyName *tmp = realloc(g_keys, new_cap * sizeof *g_keys);
            if (tmp == NULL) {
                fclose(file);
                return -1;
            }
            g_keys = tmp;
            g_keys_cap = new_cap;
        }
        char *n = name;
        if (strncmp(n, "c:/gh6_burn/data/", 17) == 0)
            n += 17;

        g_keys[g_keys_count].crc  = crc;
        g_keys[g_keys_count].name = strdup(n);
        g_keys_count++;
    }
    fclose(file);
    qsort(g_keys, g_keys_count, sizeof *g_keys, cmp_key);
    return 0;
}


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
    int result = -1;    // becomes 0 only when the last chunk was reached

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

        printf("Processing Chunk #%d | Compressed: %u bytes | Decompressed: %u bytes | Address: 0x%X\n", 
               chnk_count++, header.compressed_size, header.decompressed_size, header.output_offset);

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

unsigned char *load_file(const char *path, long *size)
{
    FILE *f = fopen(path, "rb");
    if (!f) return NULL;

    fseek(f, 0, SEEK_END);
    *size = ftell(f);
    fseek(f, 0, SEEK_SET);
    if (*size < 0) { fclose(f); return NULL; }      // ftell failed

    unsigned char *buf = malloc(*size ? *size : 1);
    if (buf && fread(buf, 1, *size, f) != (size_t)*size) {
        free(buf);                                  // could not read the whole file
        buf = NULL;
    }
    fclose(f);
    return buf;
}


static unsigned char *chnk_compress_mem(const unsigned char *data, size_t size, size_t *out_size,uint32_t *out_chunks, uint32_t *out_first_slot){
    unsigned int count = (size + 0x7FFFF) / 0x80000;
    void **comp = calloc(count, sizeof *comp);
    size_t *comp_size = calloc(count, sizeof *comp_size);
    unsigned char *out = NULL;
    size_t total = 0, pos = 0;
    CHNKHeader h;

    if(!comp || !comp_size)
        goto cleanup;

    for(unsigned int i = 0; i < count; i++){
        size_t piece = size - (size_t)i * 0x80000;
        if(piece > 0x80000)
            piece = 0x80000;
        comp[i] = tdefl_compress_mem_to_heap(data + (size_t)i * 0x80000, piece, &comp_size[i], TDEFL_DEFAULT_MAX_PROBES);
        if(!comp[i])
            goto cleanup;
        total += slot_of(comp_size[i]);
    }

    out = calloc(total, 1);
    if(!out)
        goto cleanup;

    for(unsigned int i = 0; i < count; i++){
        size_t piece = size - (size_t)i * 0x80000;
        if(piece > 0x80000)
            piece = 0x80000;

        memset(&h, 0, sizeof h);
        memcpy(h.signature, "CHNK", 4);
        h.header_size       = 0x80;
        h.compressed_size   = comp_size[i];
        h.decompressed_size = piece;
        h.output_offset     = i * 0x80000;
        h.next_chunk_dist   = (i == count - 1) ? 0xFFFFFFFF : slot_of(comp_size[i]);
        h.next_slot_size    = (i == count - 1) ? 0 : slot_of(comp_size[i + 1]);
        header_from_file(&h);           // a swap works both ways: to file and from file

        memcpy(out + pos, &h, sizeof h);
        memcpy(out + pos + 0x80, comp[i], comp_size[i]);
        pos += slot_of(comp_size[i]);
    }
    *out_size = total;
    *out_chunks = count;
    *out_first_slot = slot_of(comp_size[0]);

cleanup:
    if(comp)
        for(unsigned int i = 0; i < count; i++)
            mz_free(comp[i]);
    free(comp);
    free(comp_size);
    return out;
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

    unsigned char *blob = chnk_compress_mem(data, size, &blob_size, &chunks, &first);
    free(data);
    if(!blob){
        fprintf(stderr, "Compression failed\n");
        return -1;
    }

    FILE *out = fopen(output_path, "wb");
    int ok = out && fwrite(blob, 1, blob_size, out) == blob_size;
    if(out)
        fclose(out);
    free(blob);
    if(!ok)
        fprintf(stderr, "Failed to write %s\n", output_path);
    return ok ? 0 : -1;
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
        fprintf(stderr, "use:\n");
        usage(prog, 'd');
        usage(prog, 'c');
        usage(prog, 'l');
        usage(prog, 'x');
        usage(prog, 'r');
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

static const unsigned char *find_entry(const unsigned char *idx, long size, uint32_t crc){
    for(long off = 0; off + 32 <= size; off += 32){
        const unsigned char *e = idx + off;
        if(be32(e) == 0x2CB3EF3B){
            break;
        }
        if(be32(e + 16) == crc){
            return e;
        }
    }
    return NULL;
}

static int resolve_crc(const char *arg, uint32_t *crc){
    char *end;
    unsigned long v = strtoul(arg, &end, 16);
    if(*end == '\0' && strlen(arg) == 8){
        *crc = (uint32_t)v;
        return 0;
    }

    size_t matches = 0;
    for(size_t i = 0; i < g_keys_count; i++){
        if(strstr(g_keys[i].name, arg)){
            if(matches == 0)
                *crc = g_keys[i].crc;
            fprintf(stderr, "  %08X %s\n", g_keys[i].crc, g_keys[i].name);
            matches++;
        }
    }
    if(matches == 1)
        return 0;
    if(matches > 1)
        fprintf(stderr, "'%s' matches %zu names, be more specific\n", arg, matches);
    return -1;
}


static int chnk_decompress_mem(const unsigned char *src, size_t src_size,
                               unsigned char *dst, size_t dst_size){
    size_t pos = 0;
    CHNKHeader h;

    while(1){
        if(sizeof h > src_size - pos){
            fprintf(stderr, "Header past the end at 0x%zX\n", pos);
            return -1;
        }
        memcpy(&h, src + pos, sizeof h);
        header_from_file(&h);

        if(memcmp(h.signature, "CHNK", 4) != 0){
            fprintf(stderr, "Invalid signature at 0x%zX\n", pos);
            return -1;
        }
        if(h.header_size > src_size - pos ||
           h.compressed_size > src_size - pos - h.header_size){
            fprintf(stderr, "Chunk data past the end at 0x%zX\n", pos);
            return -1;
        }
        if(h.output_offset > dst_size ||
           h.decompressed_size > dst_size - h.output_offset){
            fprintf(stderr, "Chunk output past the end at 0x%zX\n", pos);
            return -1;
        }

        size_t n = tinfl_decompress_mem_to_mem(dst + h.output_offset, h.decompressed_size,src + pos + h.header_size, h.compressed_size, 0);
        if(n == TINFL_DECOMPRESS_MEM_TO_MEM_FAILED || n != h.decompressed_size){
            fprintf(stderr, "Failed to decompress chunk at 0x%zX\n", pos);
            return -1;
        }

        if(h.next_chunk_dist == 0xFFFFFFFF)
            return 0;
        if(h.next_chunk_dist == 0){ 
            fprintf(stderr, "Bad next chunk distance at 0x%zX\n", pos);
            return -1;
        }
        pos += h.next_chunk_dist;
    }
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

    if(chnk_decompress_mem(comp, csize, data, usize) != 0)
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

    blob = chnk_compress_mem(data, data_size, &blob_size, &chunks, &first);
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

    int closed = fclose(pab);           // fclose flushes, so it can fail too
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

int main(int argc, char **argv){
    if(argc < 2 || argv[1][0] == '\0' || argv[1][1] != '\0'){
        usage(argv[0], 0);
        return 1;
    }

    const char *keys = getenv("WOR_KEYS");

    if(keys == NULL)
        keys = "ghwor_keys.txt";
    load_keys(keys);

    char mode = argv[1][0];

    if(mode == 'd' && argc == 4)
        return decompress_chnk(argv[2], argv[3]) != 0;
    else if(mode == 'c' && argc == 4)
        return recompress_chnk(argv[2], argv[3]) != 0;
    else if(mode == 'l' && argc == 3)
        return list_index(argv[2]) != 0;
    else if(mode == 'x' && argc == 6)
        return extract_file(argv[2], argv[3], argv[4], argv[5]) != 0;
    else if(mode == 'r' && argc == 6)
        return replace_file(argv[2], argv[3], argv[4], argv[5]) != 0;

    usage(argv[0], mode);
    return 1;
}
