#include "common.h"
#include "miniz.h"
#include "chnk.h"

#define CHUNK_MAX_SIZE         0x80000     // 512 KB
#define CHUNK_HEADER_SIZE      0x80        // 128 bytes
#define NO_NEXT_CHUNK          0xFFFFFFFF


//converts all of these to big endian
void header_from_file(CHNKHeader *h){
    h->header_size = swapEndian32(h->header_size);
    h->compressed_size = swapEndian32(h->compressed_size);
    h->next_chunk_dist = swapEndian32(h->next_chunk_dist);
    h->next_slot_size = swapEndian32(h->next_slot_size);
    h->decompressed_size = swapEndian32(h->decompressed_size);
    h->output_offset = swapEndian32(h->output_offset);
}

static uint32_t slot_of(size_t csize){
    return (uint32_t)((0x80 + csize + 0x7FF) & ~(size_t)0x7FF);
}

//compress the data in the chnk format
unsigned char *chnk_comp(const unsigned char *data, size_t size, size_t *out_size, uint32_t *out_chunks, uint32_t *out_first_slot) {
    unsigned int count = (size + CHUNK_MAX_SIZE - 1) / CHUNK_MAX_SIZE;
    
    void **comp = calloc(count, sizeof *comp);
    size_t *comp_size = calloc(count, sizeof *comp_size);
    unsigned char *out = NULL;
    
    size_t total = 0;
    size_t pos = 0;
    CHNKHeader h;

    if (!comp || !comp_size) {
        goto cleanup;
    }

    for (unsigned int i = 0; i < count; i++) {
        size_t src_offset = (size_t)i * CHUNK_MAX_SIZE;
        size_t piece = size - src_offset;
        
        if (piece > CHUNK_MAX_SIZE) {
            piece = CHUNK_MAX_SIZE;
        }

        comp[i] = tdefl_compress_mem_to_heap(
            data + src_offset, 
            piece, 
            &comp_size[i], 
            TDEFL_DEFAULT_MAX_PROBES
        );

        if (!comp[i]) {
            goto cleanup;
        }

        total += slot_of(comp_size[i]);
    }

    out = calloc(total, 1);
    if (!out) {
        goto cleanup;
    }

    for (unsigned int i = 0; i < count; i++) {
        size_t src_offset = (size_t)i * CHUNK_MAX_SIZE;
        size_t piece = size - src_offset;
        
        if (piece > CHUNK_MAX_SIZE) {
            piece = CHUNK_MAX_SIZE;
        }

        memset(&h, 0, sizeof h);
        memcpy(h.signature, "CHNK", 4);
        
        h.header_size       = CHUNK_HEADER_SIZE;
        h.compressed_size   = comp_size[i];
        h.decompressed_size = piece;
        h.output_offset     = src_offset;

        if (i == count - 1) {
            h.next_chunk_dist = NO_NEXT_CHUNK;
            h.next_slot_size  = 0;
        } else {
            h.next_chunk_dist = slot_of(comp_size[i]);
            h.next_slot_size  = slot_of(comp_size[i + 1]);
        }

        header_from_file(&h);

        memcpy(out + pos, &h, sizeof h);
        memcpy(out + pos + CHUNK_HEADER_SIZE, comp[i], comp_size[i]);

        pos += slot_of(comp_size[i]);
    }

    *out_size = total;
    *out_chunks = count;
    *out_first_slot = slot_of(comp_size[0]);

cleanup:
    if (comp) {
        for (unsigned int i = 0; i < count; i++) {
            mz_free(comp[i]);
        }
    }
    free(comp);
    free(comp_size);
    
    return out;
}

//decompress the data in the chnk format
int chnk_decomp(const unsigned char *src, size_t src_size, unsigned char *dst, size_t dst_size) {
    size_t pos = 0;
    CHNKHeader h;

    while (1) {
        if (sizeof h > src_size - pos) {
            fprintf(stderr, "Header past the end at 0x%zX\n", pos);
            return -1;
        }

        memcpy(&h, src + pos, sizeof h);
        header_from_file(&h);

        if (memcmp(h.signature, "CHNK", 4) != 0) {
            fprintf(stderr, "Invalid signature at 0x%zX\n", pos);
            return -1;
        }
        if (h.header_size > src_size - pos || h.compressed_size > src_size - pos - h.header_size) {
            fprintf(stderr, "Chunk data past the end at 0x%zX\n", pos);
            return -1;
        }
        if (h.output_offset > dst_size || h.decompressed_size > dst_size - h.output_offset) {
            fprintf(stderr, "Chunk output past the end at 0x%zX\n", pos);
            return -1;
        }
        size_t decomp_bytes = tinfl_decompress_mem_to_mem(dst + h.output_offset, h.decompressed_size,src + pos + h.header_size, h.compressed_size, 0);

        if (decomp_bytes == TINFL_DECOMPRESS_MEM_TO_MEM_FAILED || decomp_bytes != h.decompressed_size) {
            fprintf(stderr, "Failed to decompress chunk at 0x%zX\n", pos);
            return -1;
        }
        if (h.next_chunk_dist == NO_NEXT_CHUNK) {
            return 0; // Sucesso
        }
        if (h.next_chunk_dist == 0) {
            fprintf(stderr, "Bad next chunk distance at 0x%zX\n", pos);
            return -1;
        }
        pos += h.next_chunk_dist;
    }
}