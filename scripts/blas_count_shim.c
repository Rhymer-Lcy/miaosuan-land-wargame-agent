/*
 * Count calls to the BLAS and LAPACK entry points NumPy imports from its bundled OpenBLAS.
 *
 * Diagnostic only, loaded with LD_PRELOAD into a game process. Each exported symbol is an assembly
 * trampoline that atomically increments its counter and jumps to the real OpenBLAS function, leaving
 * every argument register and the stack untouched, so it is independent of the function's signature
 * and changes no result. The real addresses come from an explicit dlopen of the library named by
 * BLAS_COUNT_LIBRARY in a constructor; the counts are written as JSON to BLAS_COUNT_OUTPUT at exit.
 *
 * Build: gcc -shared -fPIC -O2 -o blas_count.so blas_count_shim.c -ldl   (x86-64 Linux)
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define SYMBOLS \
    X(cblas_caxpy64_) X(cblas_cdotc_sub64_) X(cblas_cdotu_sub64_) X(cblas_cgemm64_) X(cblas_cgemv64_) \
    X(cblas_csyrk64_) X(cblas_daxpy64_) X(cblas_ddot64_) X(cblas_dgemm64_) X(cblas_dgemv64_) \
    X(cblas_dsyrk64_) X(cblas_saxpy64_) X(cblas_sdot64_) X(cblas_sgemm64_) X(cblas_sgemv64_) \
    X(cblas_ssyrk64_) X(cblas_zaxpy64_) X(cblas_zdotc_sub64_) X(cblas_zdotu_sub64_) X(cblas_zgemm64_) \
    X(cblas_zgemv64_) X(cblas_zsyrk64_) \
    X(ccopy_64_) X(cgelsd_64_) X(cgesdd_64_) X(cgesv_64_) X(cgetrf_64_) X(cheevd_64_) X(cpotrf_64_) \
    X(dcopy_64_) X(dgeev_64_) X(dgelsd_64_) X(dgeqrf_64_) X(dgesdd_64_) X(dgesv_64_) X(dgetrf_64_) \
    X(dorgqr_64_) X(dpotrf_64_) X(dsyevd_64_) X(scopy_64_) X(sgeev_64_) X(sgelsd_64_) X(sgesdd_64_) \
    X(sgesv_64_) X(sgetrf_64_) X(spotrf_64_) X(ssyevd_64_) X(zcopy_64_) X(zgeev_64_) X(zgelsd_64_) \
    X(zgeqrf_64_) X(zgesdd_64_) X(zgesv_64_) X(zgetrf_64_) X(zheevd_64_) X(zpotrf_64_) X(zungqr_64_)

#define X(name) \
    __attribute__((visibility("hidden"), used)) void *real_##name; \
    __attribute__((visibility("hidden"), used)) unsigned long count_##name;
SYMBOLS
#undef X

#define X(name) \
    __asm__(".text\n.globl " #name "\n.type " #name ",@function\n" #name ":\n" \
            "    lock incq count_" #name "(%rip)\n" \
            "    jmp *real_" #name "(%rip)\n" \
            ".size " #name ",.-" #name "\n");
SYMBOLS
#undef X

static int resolved = 0;

__attribute__((constructor)) static void blas_count_init(void) {
    /* The library's own dependencies (NumPy's bundled libquadmath and libgfortran) are found through NumPy's
       RPATH when NumPy loads it; opened directly they are listed, in order, in BLAS_COUNT_DEPS. */
    const char *deps = getenv("BLAS_COUNT_DEPS");
    if (deps != NULL) {
        char buffer[4096];
        snprintf(buffer, sizeof buffer, "%s", deps);
        for (char *item = strtok(buffer, ":"); item != NULL; item = strtok(NULL, ":")) {
            if (dlopen(item, RTLD_NOW | RTLD_GLOBAL) == NULL) {
                fprintf(stderr, "blas_count: cannot open %s: %s\n", item, dlerror());
                abort();
            }
        }
    }
    const char *path = getenv("BLAS_COUNT_LIBRARY");
    void *handle = path ? dlopen(path, RTLD_NOW | RTLD_GLOBAL) : NULL;
    if (handle == NULL) {
        fprintf(stderr, "blas_count: cannot open BLAS_COUNT_LIBRARY (%s): %s\n", path ? path : "unset",
                path ? dlerror() : "");
        abort();
    }
#define X(name) \
    real_##name = dlsym(handle, #name); \
    if (real_##name == NULL) { fprintf(stderr, "blas_count: %s not found\n", #name); abort(); }
    SYMBOLS
#undef X
    resolved = 1;
}

__attribute__((destructor)) static void blas_count_fini(void) {
    const char *out = getenv("BLAS_COUNT_OUTPUT");
    if (out == NULL || !resolved) return;
    FILE *file = fopen(out, "w");
    if (file == NULL) return;
    const char *sep = "";
    fprintf(file, "{");
#define X(name) fprintf(file, "%s\"%s\": %lu", sep, #name, count_##name); sep = ", ";
    SYMBOLS
#undef X
    fprintf(file, "}\n");
    fclose(file);
}
