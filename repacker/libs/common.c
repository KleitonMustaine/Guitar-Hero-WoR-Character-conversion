#include "common.h"


unsigned char *load_file(const char *path, long *size)
{
    FILE *f = fopen(path, "rb");
    if (!f) return NULL;

    fseek(f, 0, SEEK_END);
    *size = ftell(f);
    fseek(f, 0, SEEK_SET);

    if (*size < 0) { 
        fclose(f); 
        return NULL; 
    } 
    size_t alloc_size;
    if(*size == 0){
        alloc_size =1;
    }else{
        alloc_size = (size_t)*size;
    }
        
    unsigned char *buf = malloc(alloc_size);

    if(buf){
        if(fread(buf,1, *size, f) != (size_t)*size){
            free(buf);
            buf = NULL;
        }
    }
    fclose(f);
    return buf;
}


//reads 4 bytes at p as a big endian number
uint32_t be32(const unsigned char *p){
    return (uint32_t)p[0] << 24 |
           (uint32_t)p[1] << 16 |
           (uint32_t)p[2] << 8  |
           (uint32_t)p[3];
}


void put_be32(unsigned char *p, uint32_t v){
    p[0] = v >> 24;
    p[1] = v >> 16;
    p[2] = v >> 8;
    p[3] = v;
}

uint16_t be16(const unsigned char *p){
    return (uint16_t)p[0] << 8 |
           (uint16_t)p[1];
}


float be_float_local(const unsigned char *buf) {
    uint32_t bits = be32(buf);      // be32 already puts the bytes in the right order
    float f;
    memcpy(&f, &bits, sizeof f);    // reinterpret the bits as a float
    return f;
}
void unpack_normal_func(uint32_t p, float *nx, float *ny, float *nz) {
    uint32_t x = p & 0x7FF;
    uint32_t y = (p >> 11) & 0x7FF;
    uint32_t z = (p >> 22) & 0x3FF;

    *nx = (x & 0x400 ? (int32_t)x - 0x800 : (int32_t)x) / 1023.0f;
    *ny = (y & 0x400 ? (int32_t)y - 0x800 : (int32_t)y) / 1023.0f;
    *nz = (z & 0x200 ? (int32_t)z - 0x400 : (int32_t)z) / 511.0f;
}