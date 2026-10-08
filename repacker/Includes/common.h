#pragma once
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include "miniz.h"

typedef uint8_t u8;
typedef uint32_t u32;

//converts little endian to big endian
#define swapEndian32(x) __builtin_bswap32(x)

uint32_t be32(const unsigned char *p);
void put_be32(unsigned char *p, uint32_t v);
unsigned char *load_file(const char *path, long *size);